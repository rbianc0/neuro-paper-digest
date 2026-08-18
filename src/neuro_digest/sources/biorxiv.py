from __future__ import annotations

from neuro_digest.http import get_json, session
from neuro_digest.models import AuthorRef, Candidate, SourceRecord
from neuro_digest.util import canonical_doi, iso_date

BASE = "https://api.biorxiv.org"


def _authors(value: str | None) -> list[AuthorRef]:
    return [AuthorRef(name=x.strip(), position=i) for i, x in enumerate((value or "").split(";")) if x.strip()]


def collect_preprints(start: str, end: str, *, category: str = "neuroscience", server: str = "biorxiv") -> list[Candidate]:
    s = session(); cursor = 0; out: list[Candidate] = []
    while True:
        data = get_json(s, f"{BASE}/details/{server}/{start}/{end}/{cursor}", params={"category": category}); rows = data.get("collection") or []
        for row in rows:
            doi = canonical_doi(row.get("doi")); published = canonical_doi(row.get("published")); date = iso_date(row.get("date")); external_id = doi or f"{server}:{row.get('title') or cursor}"
            out.append(Candidate(title=row.get("title"), doi=published or doi, preprint_doi=doi, published_doi=published, authors=_authors(row.get("authors")), journal="bioRxiv" if server.lower() == "biorxiv" else "medRxiv", preprint_date=date, first_available_date=date, abstract=row.get("abstract"), url=f"https://doi.org/{doi}" if doi else None, category=row.get("category"), sources=[SourceRecord(source_type=server.lower(), external_id=external_id, source_url=f"https://api.biorxiv.org/details/{server}/{doi}" if doi else None, metadata={"version": row.get("version"), "category": row.get("category"), "server": server.lower()})]))
        messages = data.get("messages") or []; total = None
        if messages:
            total = messages[0].get("total") or messages[0].get("count")
            try: total = int(total) if total is not None else None
            except (TypeError, ValueError): total = None
        cursor += len(rows)
        if not rows or len(rows) < 30 or (total is not None and cursor >= total): break
    return out


def collect_recent_publications(start: str, end: str, *, server: str = "biorxiv") -> list[Candidate]:
    s = session(); cursor = 0; out: list[Candidate] = []
    while True:
        data = get_json(s, f"{BASE}/pubs/{server}/{start}/{end}/{cursor}"); rows = data.get("collection") or []
        for row in rows:
            pre = canonical_doi(row.get("biorxiv_doi")); pub = canonical_doi(row.get("published_doi")); pubdate = iso_date(row.get("published_date")); predate = iso_date(row.get("preprint_date")); external_id = f"{pre or 'unknown'}->{pub or 'unknown'}"
            out.append(Candidate(title=row.get("preprint_title"), doi=pub or pre, preprint_doi=pre, published_doi=pub, authors=_authors(row.get("preprint_authors")), journal=row.get("published_journal"), publication_date=pubdate, preprint_date=predate, first_available_date=predate or pubdate, abstract=row.get("preprint_abstract"), url=f"https://doi.org/{pub or pre}" if (pub or pre) else None, category=row.get("preprint_category"), sources=[SourceRecord(source_type=f"{server.lower()}_published_mapping", external_id=external_id, source_url=f"https://api.biorxiv.org/pubs/{server}/{pre}" if pre else None, metadata={"preprint_doi": pre, "published_doi": pub})]))
        cursor += len(rows)
        if not rows or len(rows) < 100: break
    return out
