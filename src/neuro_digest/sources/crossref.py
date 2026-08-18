from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from neuro_digest.http import get_json, session
from neuro_digest.models import AuthorRef, Candidate, SourceRecord
from neuro_digest.util import canonical_doi, canonical_orcid

BASE = "https://api.crossref.org"


def _date(message: dict[str, Any]) -> str | None:
    for key in ("published-online", "published-print", "published", "issued", "created"):
        raw = message.get(key) or {}; parts = raw.get("date-parts") or []
        if parts and parts[0]:
            values = parts[0]; year = int(values[0]); month = int(values[1]) if len(values) > 1 else 1; day = int(values[2]) if len(values) > 2 else 1
            return f"{year:04d}-{month:02d}-{day:02d}"
        if raw.get("date-time"): return str(raw["date-time"])[:10]
    return None


def _authors(message: dict[str, Any]) -> list[AuthorRef]:
    out: list[AuthorRef] = []
    for position, raw in enumerate(message.get("author") or []):
        name = " ".join(x for x in (raw.get("given"), raw.get("family")) if x).strip() or raw.get("name")
        if name:
            out.append(AuthorRef(name=name, orcid=canonical_orcid(raw.get("ORCID")), affiliations=[{"name": x.get("name")} for x in (raw.get("affiliation") or []) if x.get("name")], position=position))
    return out


def candidate_from_message(message: dict[str, Any]) -> Candidate:
    doi = canonical_doi(message.get("DOI")); titles = message.get("title") or []; containers = message.get("container-title") or []
    abstract = message.get("abstract")
    if abstract: abstract = BeautifulSoup(abstract, "html.parser").get_text(" ", strip=True)
    publication_date = _date(message); url = message.get("URL") or (f"https://doi.org/{doi}" if doi else None); external_id = doi or str(message.get("member") or (titles[0] if titles else None) or "unknown")
    meta = {"publisher": message.get("publisher"), "type": message.get("type"), "issn": message.get("ISSN"), "license": message.get("license"), "relation": message.get("relation"), "is_referenced_by_count": message.get("is-referenced-by-count")}
    return Candidate(title=titles[0] if titles else None, doi=doi, authors=_authors(message), journal=containers[0] if containers else None, publication_date=publication_date, first_available_date=publication_date, abstract=abstract, url=url, cited_by_count=message.get("is-referenced-by-count"), sources=[SourceRecord("crossref", external_id, f"{BASE}/works/{quote(doi, safe='')}" if doi else url, meta)], metadata={"crossref_publisher": message.get("publisher")})


class CrossrefClient:
    def __init__(self, mailto: str | None = None):
        self.mailto = mailto or os.getenv("CROSSREF_MAILTO"); self.s = session(); self.s.headers.update({"User-Agent": "Neurofeed/0.2 (scientific literature discovery)"})

    def lookup_doi(self, doi: str) -> Candidate | None:
        doi = canonical_doi(doi)
        if not doi: return None
        try: data = get_json(self.s, f"{BASE}/works/{quote(doi, safe='')}", params={"mailto": self.mailto} if self.mailto else None)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404: return None
            raise
        message = data.get("message") or {}
        return candidate_from_message(message) if message else None
