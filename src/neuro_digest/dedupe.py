from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from rapidfuzz.fuzz import ratio

from neuro_digest.models import AuthorRef, Candidate, SourceRecord, _merge_metadata
from neuro_digest.util import author_key, canonical_doi, normalized_title


def _author_overlap(a: Candidate, b: Candidate) -> float:
    aa = {author_key(x.name) for x in a.authors if author_key(x.name)}
    bb = {author_key(x.name) for x in b.authors if author_key(x.name)}
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def _same(a: Candidate, b: Candidate) -> bool:
    adois = {canonical_doi(x) for x in (a.doi, a.preprint_doi, a.published_doi) if canonical_doi(x)}
    bdois = {canonical_doi(x) for x in (b.doi, b.preprint_doi, b.published_doi) if canonical_doi(x)}
    if adois & bdois:
        return True
    if a.openalex_id and b.openalex_id and a.openalex_id == b.openalex_id:
        return True
    if a.pmid and b.pmid and a.pmid == b.pmid:
        return True
    ta, tb = normalized_title(a.title), normalized_title(b.title)
    if ta and ta == tb:
        return True
    return len(ta) >= 25 and len(tb) >= 25 and ratio(ta, tb) >= 96 and _author_overlap(a, b) >= 0.35


def _merge_authors(a: list[AuthorRef], b: list[AuthorRef]) -> list[AuthorRef]:
    out: list[AuthorRef] = []
    for author in [*a, *b]:
        current = next((x for x in out if (
            (x.openalex_id and author.openalex_id and x.openalex_id == author.openalex_id)
            or (x.orcid and author.orcid and x.orcid.casefold() == author.orcid.casefold())
            or (normalized_title(x.name) and normalized_title(x.name) == normalized_title(author.name))
        )), None)
        if current is None:
            out.append(replace(author, affiliations=list(author.affiliations)))
            continue
        current.openalex_id = current.openalex_id or author.openalex_id
        current.orcid = current.orcid or author.orcid
        current.position = current.position if current.position is not None else author.position
        seen = {repr(x) for x in current.affiliations}
        current.affiliations.extend(x for x in author.affiliations if repr(x) not in seen)
    return sorted(out, key=lambda x: x.position if x.position is not None else 10**9)


def _merge_sources(a: list[SourceRecord], b: list[SourceRecord]) -> list[SourceRecord]:
    out: dict[tuple[str, str], SourceRecord] = {}
    for source in [*a, *b]:
        key = (source.source_type, source.external_id)
        current = out.get(key)
        if current is None:
            out[key] = replace(source, metadata=dict(source.metadata))
        else:
            current.source_url = current.source_url or source.source_url
            current.metadata = _merge_metadata(current.metadata, source.metadata)
    return list(out.values())


def merge(a: Candidate, b: Candidate) -> Candidate:
    prefer_b = bool(b.published_doi) or ("openalex" in b.source_types and "openalex" not in a.source_types)
    primary, secondary = (b, a) if prefer_b else (a, b)
    out = replace(primary)
    out.title = primary.title or secondary.title
    out.doi = canonical_doi(primary.published_doi or secondary.published_doi or primary.doi or secondary.doi or primary.preprint_doi or secondary.preprint_doi)
    out.preprint_doi = canonical_doi(primary.preprint_doi or secondary.preprint_doi)
    out.published_doi = canonical_doi(primary.published_doi or secondary.published_doi)
    out.authors = _merge_authors(primary.authors, secondary.authors)
    out.journal = primary.journal or secondary.journal
    out.publication_date = primary.publication_date or secondary.publication_date
    out.preprint_date = primary.preprint_date or secondary.preprint_date
    dates = [x for x in (primary.first_available_date, secondary.first_available_date, out.preprint_date, out.publication_date) if x]
    out.first_available_date = min(dates) if dates else None
    out.abstract = primary.abstract or secondary.abstract
    out.url = primary.url or secondary.url
    out.openalex_id = primary.openalex_id or secondary.openalex_id
    out.pmid = primary.pmid or secondary.pmid
    out.category = primary.category or secondary.category
    out.species = primary.species or secondary.species
    out.cited_by_count = max([x for x in (primary.cited_by_count, secondary.cited_by_count) if x is not None], default=None)
    out.sources = _merge_sources(primary.sources, secondary.sources)
    out.query_hits = list(dict.fromkeys([*primary.query_hits, *secondary.query_hits]))
    out.metadata = _merge_metadata(primary.metadata, secondary.metadata)
    signal_keys: set[tuple[str, str, str | None]] = set()
    signals = []
    for signal in [*primary.bluesky_signals, *secondary.bluesky_signals]:
        key = (signal.followed_actor, signal.action, signal.post_url)
        if key not in signal_keys:
            signal_keys.add(key)
            signals.append(signal)
    out.bluesky_signals = signals
    return out


def deduplicate(items: Iterable[Candidate]) -> list[Candidate]:
    groups: list[Candidate] = []
    for item in items:
        idx = next((i for i, existing in enumerate(groups) if _same(existing, item)), None)
        if idx is None:
            groups.append(item)
        else:
            groups[idx] = merge(groups[idx], item)
    return groups
