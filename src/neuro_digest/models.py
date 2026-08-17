from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class BlueskySignal:
    followed_actor: str
    followed_actor_did: str | None = None
    action: str = "post"  # post | repost | quote
    post_url: str | None = None
    created_at: str | None = None
    original_author: str | None = None
    text: str | None = None


@dataclass
class Candidate:
    title: str | None = None
    doi: str | None = None
    authors: list[str] = field(default_factory=list)
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
    source_types: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    query_hits: list[str] = field(default_factory=list)
    bluesky_signals: list[BlueskySignal] = field(default_factory=list)
    metadata_confidence: str = "high"
    first_seen: str | None = None
    last_seen: str | None = None
    seen_weeks: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
