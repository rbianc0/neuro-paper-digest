from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from neuro_digest.models import AuthorRef, Candidate
from neuro_digest.util import canonical_doi, canonical_openalex_id, canonical_orcid, normalized_title


class DataAPIError(RuntimeError):
    pass


class SupabaseDataAPI:
    """Minimal server-side client for the Supabase Data API."""

    def __init__(self, url: str | None = None, key: str | None = None, *, session: requests.Session | None = None):
        self.url = (url or os.getenv("SUPABASE_URL") or "").rstrip("/")
        self.key = key or os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        if not self.url:
            raise RuntimeError("SUPABASE_URL is required")
        if not self.key:
            raise RuntimeError("SUPABASE_SECRET_KEY is required for global ingestion")
        self.s = session or requests.Session()
        self.s.headers.update({"apikey": self.key, "Content-Type": "application/json", "User-Agent": "Neurofeed/0.2"})
        if self.key.startswith("eyJ"):
            self.s.headers.update({"Authorization": f"Bearer {self.key}"})

    def _request(self, method: str, resource: str, *, params: dict[str, Any] | None = None, json: Any = None, prefer: str | None = None) -> Any:
        headers = {"Prefer": prefer} if prefer else None
        response = self.s.request(method, f"{self.url}/rest/v1/{resource}", params=params, json=json, headers=headers, timeout=30)
        if response.status_code >= 400:
            raise DataAPIError(f"Supabase Data API {method} {resource} failed ({response.status_code}): {response.text[:500]}")
        if not response.content:
            return None
        return response.json()

    def select_one(self, table: str, column: str, value: Any) -> dict[str, Any] | None:
        return self.select_one_where(table, {column: value})

    def select_one_where(self, table: str, filters: dict[str, Any]) -> dict[str, Any] | None:
        params: dict[str, Any] = {"select": "*", "limit": 1}
        params.update({column: f"eq.{value}" for column, value in filters.items()})
        rows = self._request("GET", table, params=params) or []
        return rows[0] if rows else None

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        rows = self._request("POST", table, json=row, prefer="return=representation") or []
        if not rows:
            raise DataAPIError(f"Insert into {table} returned no row")
        return rows[0]

    def update(self, table: str, row_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        rows = self._request("PATCH", table, params={"id": f"eq.{row_id}"}, json=changes, prefer="return=representation") or []
        if not rows:
            raise DataAPIError(f"Update of {table}.{row_id} returned no row")
        return rows[0]

    def upsert(self, table: str, row: dict[str, Any], *, on_conflict: str) -> dict[str, Any]:
        rows = self._request("POST", table, params={"on_conflict": on_conflict}, json=row, prefer="resolution=merge-duplicates,return=representation") or []
        if not rows:
            raise DataAPIError(f"Upsert into {table} returned no row")
        return rows[0]

    def rpc(self, function: str, args: dict[str, Any]) -> Any:
        return self._request("POST", f"rpc/{function}", json=args, prefer="return=representation")


@dataclass
class PersistStats:
    papers: int = 0
    sources: int = 0
    authors: int = 0
    paper_authors: int = 0
    merged_papers: int = 0


class LiteratureRepository:
    """Persistence boundary for the canonical global literature layer."""

    def __init__(self, api: SupabaseDataAPI | None = None):
        self.api = api or SupabaseDataAPI()
        self._merge_count = 0

    def persist_many(self, candidates: list[Candidate]) -> PersistStats:
        stats = PersistStats()
        for candidate in candidates:
            before_merges = self._merge_count
            paper_id, source_count, author_count, paper_author_count = self.persist(candidate)
            if paper_id:
                stats.papers += 1
            stats.sources += source_count
            stats.authors += author_count
            stats.paper_authors += paper_author_count
            stats.merged_papers += self._merge_count - before_merges
        return stats

    def persist(self, candidate: Candidate) -> tuple[str, int, int, int]:
        existing = self._find_and_merge_paper(candidate)
        payload = self._paper_payload(candidate, existing=existing)
        if existing:
            paper = self.api.update("papers", existing["id"], payload)
        else:
            try:
                paper = self.api.insert("papers", payload)
            except DataAPIError:
                existing = self._find_and_merge_paper(candidate)
                if not existing:
                    raise
                paper = self.api.update("papers", existing["id"], self._paper_payload(candidate, existing=existing))
        paper_id = paper["id"]
        self._register_identifiers(paper_id, candidate)

        source_count = 0
        for source in candidate.sources:
            self.api.upsert("paper_sources", {"paper_id": paper_id, "source_type": source.source_type, "external_id": source.external_id, "source_url": source.source_url, "metadata": source.metadata}, on_conflict="source_type,external_id")
            source_count += 1

        author_count = 0
        paper_author_count = 0
        for position, author in enumerate(candidate.authors):
            author_id, created = self._upsert_author(author, paper_id)
            author_count += int(created)
            self.api.upsert("paper_authors", {"paper_id": paper_id, "author_id": author_id, "author_position": author.position if author.position is not None else position}, on_conflict="paper_id,author_id")
            paper_author_count += 1
        return paper_id, source_count, author_count, paper_author_count

    def _identifier_rows(self, candidate: Candidate) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for raw in (candidate.published_doi, candidate.doi, candidate.preprint_doi):
            doi = canonical_doi(raw)
            if doi:
                rows.append(("DOI", doi))
        openalex_id = canonical_openalex_id(candidate.openalex_id)
        if openalex_id:
            rows.append(("OPENALEX", openalex_id))
        if candidate.pmid:
            rows.append(("PMID", str(candidate.pmid)))
        return list(dict.fromkeys(rows))

    def _find_and_merge_paper(self, candidate: Candidate) -> dict[str, Any] | None:
        paper_ids: list[str] = []
        for identifier_type, identifier_value in self._identifier_rows(candidate):
            row = self.api.select_one_where("paper_identifiers", {"identifier_type": identifier_type, "identifier_value": identifier_value})
            if row and row.get("paper_id") not in paper_ids:
                paper_ids.append(row["paper_id"])
        if paper_ids:
            keep_id = paper_ids[0]
            for remove_id in paper_ids[1:]:
                self.api.rpc("merge_papers", {"keep_id": keep_id, "remove_id": remove_id})
                self._merge_count += 1
            return self.api.select_one("papers", "id", keep_id)
        title_key = normalized_title(candidate.title)
        if title_key:
            return self.api.select_one("papers", "title_key", title_key)
        return None

    def _register_identifiers(self, paper_id: str, candidate: Candidate) -> None:
        for identifier_type, identifier_value in self._identifier_rows(candidate):
            self.api.upsert("paper_identifiers", {"paper_id": paper_id, "identifier_type": identifier_type, "identifier_value": identifier_value}, on_conflict="identifier_type,identifier_value")

    def _paper_payload(self, candidate: Candidate, *, existing: dict[str, Any] | None) -> dict[str, Any]:
        canonical = canonical_doi(candidate.published_doi or candidate.doi or candidate.preprint_doi)
        metadata = dict((existing or {}).get("metadata") or {})
        metadata.update(candidate.metadata)
        if candidate.category:
            metadata["category"] = candidate.category
        if candidate.species:
            metadata["species"] = candidate.species
        if candidate.query_hits:
            metadata["query_hits"] = list(dict.fromkeys([*(metadata.get("query_hits") or []), *candidate.query_hits]))
        values: dict[str, Any] = {"canonical_doi": canonical, "title": candidate.title, "title_key": normalized_title(candidate.title) or None, "abstract": candidate.abstract, "journal": candidate.journal, "publication_date": candidate.publication_date, "first_online_date": candidate.first_available_date or candidate.preprint_date or candidate.publication_date, "openalex_id": canonical_openalex_id(candidate.openalex_id), "pmid": str(candidate.pmid) if candidate.pmid else None, "preprint_doi": canonical_doi(candidate.preprint_doi), "published_doi": canonical_doi(candidate.published_doi), "cited_by_count": candidate.cited_by_count, "metadata": metadata}
        if existing:
            for field in ("canonical_doi", "title", "title_key", "abstract", "journal", "publication_date", "first_online_date", "openalex_id", "pmid", "preprint_doi", "published_doi"):
                if values[field] is None:
                    values[field] = existing.get(field)
            old_citations = existing.get("cited_by_count")
            if old_citations is not None:
                values["cited_by_count"] = max(old_citations, values["cited_by_count"] or 0)
        return {key: value for key, value in values.items() if value is not None}

    def _author_identity_key(self, author: AuthorRef, paper_id: str) -> str:
        orcid = canonical_orcid(author.orcid)
        openalex_id = canonical_openalex_id(author.openalex_id)
        if orcid:
            return f"orcid:{orcid}"
        if openalex_id:
            return f"openalex:{openalex_id}"
        return f"paper:{paper_id}:name:{normalized_title(author.name)}"

    def _upsert_author(self, author: AuthorRef, paper_id: str) -> tuple[str, bool]:
        openalex_id = canonical_openalex_id(author.openalex_id)
        orcid = canonical_orcid(author.orcid)
        identity_key = self._author_identity_key(author, paper_id)
        existing = self.api.select_one("authors", "identity_key", identity_key)
        if existing is None and orcid:
            existing = self.api.select_one("authors", "orcid", orcid)
        if existing is None and openalex_id:
            existing = self.api.select_one("authors", "openalex_id", openalex_id)
        affiliation_metadata = {"affiliations": author.affiliations}
        if existing:
            merged_affiliations = list((existing.get("affiliation_metadata") or {}).get("affiliations") or [])
            seen = {repr(x) for x in merged_affiliations}
            merged_affiliations.extend(x for x in author.affiliations if repr(x) not in seen)
            updated = self.api.update("authors", existing["id"], {"canonical_name": existing.get("canonical_name") or author.name, "openalex_id": existing.get("openalex_id") or openalex_id, "orcid": existing.get("orcid") or orcid, "affiliation_metadata": {"affiliations": merged_affiliations}})
            return updated["id"], False
        row = self.api.insert("authors", {"canonical_name": author.name, "identity_key": identity_key, "openalex_id": openalex_id, "orcid": orcid, "affiliation_metadata": affiliation_metadata})
        return row["id"], True
