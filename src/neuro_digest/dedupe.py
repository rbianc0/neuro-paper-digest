from __future__ import annotations

from dataclasses import replace
from typing import Iterable
from rapidfuzz.fuzz import ratio
from neuro_digest.models import Candidate
from neuro_digest.util import author_key, canonical_doi, normalized_title


def _unique(seq):
    out=[]; seen=set()
    for x in seq:
        if x is None: continue
        key=str(x)
        if key not in seen:
            seen.add(key); out.append(x)
    return out


def _author_overlap(a: Candidate, b: Candidate) -> float:
    aa={author_key(x) for x in a.authors if author_key(x)}; bb={author_key(x) for x in b.authors if author_key(x)}
    if not aa or not bb: return 0.0
    return len(aa & bb)/len(aa | bb)


def _same(a: Candidate, b: Candidate) -> bool:
    adois={canonical_doi(x) for x in (a.doi,a.preprint_doi,a.published_doi) if canonical_doi(x)}
    bdois={canonical_doi(x) for x in (b.doi,b.preprint_doi,b.published_doi) if canonical_doi(x)}
    if adois & bdois: return True
    if a.openalex_id and b.openalex_id and a.openalex_id==b.openalex_id: return True
    if a.pmid and b.pmid and a.pmid==b.pmid: return True
    ta,tb=normalized_title(a.title),normalized_title(b.title)
    if ta and ta==tb: return True
    return len(ta)>=25 and len(tb)>=25 and ratio(ta,tb)>=96 and _author_overlap(a,b)>=0.35


def merge(a: Candidate, b: Candidate) -> Candidate:
    prefer_b=bool(b.published_doi) or ("openalex" in b.source_types and "openalex" not in a.source_types)
    primary,secondary=(b,a) if prefer_b else (a,b)
    out=replace(primary)
    out.title=primary.title or secondary.title
    out.doi=canonical_doi(primary.published_doi or secondary.published_doi or primary.doi or secondary.doi or primary.preprint_doi or secondary.preprint_doi)
    out.preprint_doi=canonical_doi(primary.preprint_doi or secondary.preprint_doi)
    out.published_doi=canonical_doi(primary.published_doi or secondary.published_doi)
    out.authors=_unique(primary.authors+secondary.authors)
    out.journal=primary.journal or secondary.journal
    out.publication_date=primary.publication_date or secondary.publication_date
    out.preprint_date=primary.preprint_date or secondary.preprint_date
    dates=[x for x in (primary.first_available_date,secondary.first_available_date,out.preprint_date,out.publication_date) if x]
    out.first_available_date=min(dates) if dates else None
    out.abstract=primary.abstract or secondary.abstract; out.url=primary.url or secondary.url
    out.openalex_id=primary.openalex_id or secondary.openalex_id; out.pmid=primary.pmid or secondary.pmid
    out.category=primary.category or secondary.category
    out.cited_by_count=max([x for x in (primary.cited_by_count,secondary.cited_by_count) if x is not None], default=None)
    out.source_types=_unique(primary.source_types+secondary.source_types); out.source_urls=_unique(primary.source_urls+secondary.source_urls); out.query_hits=_unique(primary.query_hits+secondary.query_hits)
    signal_keys=set(); signals=[]
    for s in primary.bluesky_signals+secondary.bluesky_signals:
        key=(s.followed_actor,s.action,s.post_url)
        if key not in signal_keys: signal_keys.add(key); signals.append(s)
    out.bluesky_signals=signals
    return out


def deduplicate(items: Iterable[Candidate]) -> list[Candidate]:
    groups=[]
    for item in items:
        idx=next((i for i,existing in enumerate(groups) if _same(existing,item)),None)
        if idx is None: groups.append(item)
        else: groups[idx]=merge(groups[idx],item)
    return groups
