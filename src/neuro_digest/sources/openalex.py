from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from typing import Any

import requests

from neuro_digest.http import get_json, session
from neuro_digest.models import AuthorRef, Candidate, SourceRecord
from neuro_digest.util import canonical_doi, canonical_openalex_id, canonical_orcid, iso_date

LOG = logging.getLogger(__name__)
BASE = "https://api.openalex.org"


def _abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    positions: list[tuple[int, str]] = []
    for word, slots in index.items():
        positions.extend((slot, word) for slot in slots)
    return " ".join(word for _, word in sorted(positions)) if positions else None


def _authors(work: dict[str, Any]) -> list[AuthorRef]:
    out: list[AuthorRef] = []
    for position, authorship in enumerate(work.get("authorships") or []):
        author = authorship.get("author") or {}
        name = author.get("display_name")
        if not name:
            continue
        affiliations = [{"openalex_id": canonical_openalex_id(x.get("id")), "name": x.get("display_name"), "country_code": x.get("country_code"), "type": x.get("type")} for x in authorship.get("institutions") or []]
        out.append(AuthorRef(name=name, openalex_id=canonical_openalex_id(author.get("id")), orcid=canonical_orcid(author.get("orcid")), affiliations=affiliations, position=position))
    return out


def _journal(work: dict[str, Any]) -> str | None:
    return (((work.get("primary_location") or {}).get("source") or {}).get("display_name"))


def _pmid(work: dict[str, Any]) -> str | None:
    pmid = (work.get("ids") or {}).get("pmid")
    return str(pmid).rstrip("/").split("/")[-1] if pmid else None


def candidate_from_work(work: dict[str, Any], *, source_type: str = "openalex", query: str | None = None) -> Candidate:
    doi = canonical_doi(work.get("doi") or (work.get("ids") or {}).get("doi"))
    publication_date = iso_date(work.get("publication_date"))
    landing = ((work.get("primary_location") or {}).get("landing_page_url"))
    openalex_id = canonical_openalex_id(work.get("id"))
    source_url = work.get("id")
    metadata = {"type": work.get("type"), "query_hits": [query] if query else [], "primary_location": work.get("primary_location")}
    return Candidate(title=work.get("display_name") or work.get("title"), doi=doi, authors=_authors(work), journal=_journal(work), publication_date=publication_date, first_available_date=publication_date, abstract=_abstract_from_inverted_index(work.get("abstract_inverted_index")), url=landing or (f"https://doi.org/{doi}" if doi else source_url), openalex_id=openalex_id, pmid=_pmid(work), cited_by_count=work.get("cited_by_count"), sources=[SourceRecord(source_type=source_type, external_id=openalex_id or source_url or doi or "unknown", source_url=source_url, metadata=metadata)], query_hits=[query] if query else [], metadata={"openalex_type": work.get("type")})


class OpenAlexClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("OPENALEX_API_KEY")
        self.s = session()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _params(self, **kwargs: Any) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("OPENALEX_API_KEY is required for OpenAlex API calls")
        return {"api_key": self.api_key, **kwargs}

    def list_recent_field_works(self, start: str, end: str, *, field_ids: Iterable[int | str] = (28, 32), max_records: int = 5000) -> list[Candidate]:
        fields = [str(x).strip() for x in field_ids if str(x).strip()]
        filters = [f"from_publication_date:{start}", f"to_publication_date:{end}", "type:article|preprint"]
        if fields:
            filters.append("topics.field.id:" + "|".join(fields[:100]))
        cursor = "*"
        out: list[Candidate] = []
        select = "id,doi,display_name,publication_date,type,cited_by_count,authorships,primary_location,ids,abstract_inverted_index"
        while cursor and len(out) < max_records:
            per_page = min(100, max_records - len(out))
            data = get_json(self.s, f"{BASE}/works", params=self._params(filter=",".join(filters), sort="publication_date:desc", per_page=per_page, cursor=cursor, select=select))
            rows = data.get("results") or []
            out.extend(candidate_from_work(row, source_type="openalex") for row in rows)
            if not rows:
                break
            cursor = (data.get("meta") or {}).get("next_cursor")
        return out

    def search_works(self, query: str, start: str, end: str, *, per_page: int = 50, source_ids: Iterable[str] | None = None) -> list[Candidate]:
        filt = [f"from_publication_date:{start}", f"to_publication_date:{end}", "type:article|preprint"]
        ids = [x for x in (source_ids or []) if x]
        if ids:
            filt.append("primary_location.source.id:" + "|".join(ids[:100]))
        params = self._params(search=query, filter=",".join(filt), sort="relevance_score:desc", per_page=min(per_page, 100), select="id,doi,display_name,publication_date,type,cited_by_count,authorships,primary_location,ids,abstract_inverted_index")
        data = get_json(self.s, f"{BASE}/works", params=params)
        return [candidate_from_work(w, query=query) for w in data.get("results", [])]

    def lookup_doi(self, doi: str) -> Candidate | None:
        doi = canonical_doi(doi)
        if not doi:
            return None
        try:
            data = get_json(self.s, f"{BASE}/works/doi:{doi}", params=self._params())
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise
        return candidate_from_work(data, source_type="openalex_enrichment")

    def lookup_pmid(self, pmid: str) -> Candidate | None:
        try:
            data = get_json(self.s, f"{BASE}/works/pmid:{pmid}", params=self._params())
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise
        return candidate_from_work(data, source_type="openalex_enrichment")

    def resolve_source_ids(self, journal_names: Iterable[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for name in journal_names:
            data = get_json(self.s, f"{BASE}/sources", params=self._params(search=name, per_page=5, select="id,display_name"))
            candidates = data.get("results", [])
            exact = next((x for x in candidates if (x.get("display_name") or "").casefold() == name.casefold()), None)
            chosen = exact or (candidates[0] if candidates else None)
            if chosen and chosen.get("id"):
                out[name] = canonical_openalex_id(chosen["id"]) or chosen["id"]
            else:
                LOG.warning("Could not resolve OpenAlex source for journal %s", name)
        return out
