from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AuthorRef:
    name: str
    openalex_id: str | None = None
    orcid: str | None = None
    affiliations: list[dict[str, Any]] = field(default_factory=list)
    position: int | None = None


@dataclass
class SourceRecord:
    source_type: str
    external_id: str
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BlueskySignal:
    followed_actor: str
    followed_actor_did: str | None = None
    action: str = "post"
    post_url: str | None = None
    created_at: str | None = None
    original_author: str | None = None
    text: str | None = None


@dataclass
class Candidate:
    title: str | None = None
    doi: str | None = None
    authors: list[AuthorRef] = field(default_factory=list)
    journal: str | None = None
    publication_date: str | None = None
    preprint_date: str | None = None
    first_available_date: str | None = None
    abstract: str | None = None
    url: str | None = None
    openalex_id: str | None = None
    pmid: str | None = None
    preprint_doi: str | None = None
    published_doi: str | None = None
    category: str | None = None
    species: str | None = None
    cited_by_count: int | None = None
    sources: list[SourceRecord] = field(default_factory=list)
    query_hits: list[str] = field(default_factory=list)
    bluesky_signals: list[BlueskySignal] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def source_types(self) -> list[str]:
        return list(dict.fromkeys(s.source_type for s in self.sources))

    @property
    def source_urls(self) -> list[str]:
        return list(dict.fromkeys(s.source_url for s in self.sources if s.source_url))

    def add_source(self, source: SourceRecord) -> None:
        key = (source.source_type, source.external_id)
        for existing in self.sources:
            if (existing.source_type, existing.external_id) == key:
                existing.source_url = existing.source_url or source.source_url
                existing.metadata = _merge_metadata(existing.metadata, source.metadata)
                return
        self.sources.append(source)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _merge_metadata(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for key, value in b.items():
        if key in out and isinstance(out[key], list) and isinstance(value, list):
            out[key] = list(dict.fromkeys([*out[key], *value]))
        elif value is not None:
            out[key] = value
    return out
