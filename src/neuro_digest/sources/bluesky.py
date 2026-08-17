from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urldefrag

from dateutil.parser import isoparse

from neuro_digest.http import get_json, session
from neuro_digest.util import extract_dois, extract_pmid, extract_urls, scholarly_url

APPVIEW = "https://public.api.bsky.app/xrpc"
ENTRYWAY = "https://bsky.social/xrpc"


@dataclass
class BlueskyAccountRef:
    did: str
    handle: str | None = None
    display_name: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScholarlyLink:
    link_key: str
    url: str | None = None
    doi: str | None = None
    pmid: str | None = None


@dataclass
class FeedEvent:
    post_uri: str
    cid: str | None
    post_author: BlueskyAccountRef
    text: str
    created_at: str | None
    indexed_at: str | None
    post_type: str
    referenced_uri: str | None
    signal_actor_did: str
    signal_type: str
    signal_timestamp: str
    event_uri: str | None
    links: list[ScholarlyLink]
    raw_record: dict[str, Any]
    raw_event: dict[str, Any]

    @property
    def event_key(self) -> str:
        return "|".join((self.signal_actor_did, self.signal_type, self.post_uri, self.signal_timestamp))


def _account(view: dict[str, Any]) -> BlueskyAccountRef:
    return BlueskyAccountRef(
        did=view.get("did") or "",
        handle=view.get("handle"),
        display_name=view.get("displayName"),
        description=view.get("description"),
        metadata={"labels": view.get("labels") or [], "created_at": view.get("createdAt")},
    )


def _walk_strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _walk_strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_strings(value)


def _quote_uri(record: dict[str, Any]) -> str | None:
    embed = record.get("embed")
    if not isinstance(embed, dict):
        return None
    etype = embed.get("$type") or ""
    if etype == "app.bsky.embed.record" or etype.endswith("#record"):
        ref = embed.get("record") or {}
        return ref.get("uri") if isinstance(ref, dict) else None
    if etype == "app.bsky.embed.recordWithMedia" or etype.endswith("#recordWithMedia"):
        holder = embed.get("record") or {}
        if isinstance(holder, dict) and holder.get("uri"):
            return holder.get("uri")
        ref = holder.get("record") if isinstance(holder, dict) else None
        return ref.get("uri") if isinstance(ref, dict) else None
    return None


def _normalize_url(url: str) -> str:
    return urldefrag(url.strip().rstrip(".,;:)]}"))[0]


def extract_scholarly_links(record: dict[str, Any], view_embed: Any = None) -> list[ScholarlyLink]:
    strings = [record.get("text") or ""]
    strings.extend(_walk_strings({"facets": record.get("facets"), "record_embed": record.get("embed"), "view_embed": view_embed}))
    urls: set[str] = set(); dois: set[str] = set(); pmids: set[str] = set()
    for raw in strings:
        dois.update(extract_dois(raw))
        pmid = extract_pmid(raw)
        if pmid: pmids.add(pmid)
        if raw.startswith(("http://", "https://")):
            url = _normalize_url(raw)
            if scholarly_url(url): urls.add(url)
        else:
            for found in extract_urls(raw):
                url = _normalize_url(found)
                if scholarly_url(url): urls.add(url)
    links: dict[str, ScholarlyLink] = {}
    for url in urls:
        url_dois = extract_dois(url); url_pmid = extract_pmid(url)
        if url_dois:
            for doi in url_dois:
                links[f"doi:{doi}"] = ScholarlyLink(f"doi:{doi}", url=url, doi=doi); dois.discard(doi)
        elif url_pmid:
            links[f"pmid:{url_pmid}"] = ScholarlyLink(f"pmid:{url_pmid}", url=url, pmid=url_pmid); pmids.discard(url_pmid)
        else:
            links[f"url:{url}"] = ScholarlyLink(f"url:{url}", url=url)
    for doi in sorted(dois): links.setdefault(f"doi:{doi}", ScholarlyLink(f"doi:{doi}", doi=doi))
    for pmid in sorted(pmids): links.setdefault(f"pmid:{pmid}", ScholarlyLink(f"pmid:{pmid}", pmid=pmid))
    return list(links.values())


def parse_feed_item(followed_did: str, item: dict[str, Any]) -> FeedEvent | None:
    post = item.get("post") or {}; record = post.get("record") or {}; post_uri = post.get("uri"); author = _account(post.get("author") or {})
    if not post_uri or not author.did: return None
    reason = item.get("reason") or {}; reason_type = reason.get("$type") or ""; referenced_uri = _quote_uri(record)
    intrinsic_type = "QUOTE" if referenced_uri else "POST"
    signal_type = "REPOST" if reason_type.endswith("#reasonRepost") else intrinsic_type
    signal_timestamp = reason.get("indexedAt") if signal_type == "REPOST" else record.get("createdAt") or post.get("indexedAt")
    if not signal_timestamp: return None
    return FeedEvent(post_uri=post_uri, cid=post.get("cid"), post_author=author, text=record.get("text") or "", created_at=record.get("createdAt"), indexed_at=post.get("indexedAt"), post_type=intrinsic_type, referenced_uri=referenced_uri, signal_actor_did=followed_did, signal_type=signal_type, signal_timestamp=signal_timestamp, event_uri=reason.get("uri"), links=extract_scholarly_links(record, post.get("embed")), raw_record=record, raw_event={"reason": reason, "reply": item.get("reply")})


class BlueskyClient:
    def __init__(self): self.s = session()

    def resolve_handle(self, handle: str) -> str:
        data = get_json(self.s, f"{ENTRYWAY}/com.atproto.identity.resolveHandle", params={"handle": handle}); did = data.get("did")
        if not did: raise RuntimeError(f"Bluesky handle did not resolve: {handle}")
        return did

    def get_profile(self, actor: str) -> BlueskyAccountRef:
        data = get_json(self.s, f"{APPVIEW}/app.bsky.actor.getProfile", params={"actor": actor}); account = _account(data)
        if not account.did: raise RuntimeError(f"Bluesky profile did not resolve: {actor}")
        return account

    def get_follows(self, actor: str) -> list[BlueskyAccountRef]:
        cursor = None; out: list[BlueskyAccountRef] = []
        while True:
            params: dict[str, Any] = {"actor": actor, "limit": 100}
            if cursor: params["cursor"] = cursor
            data = get_json(self.s, f"{APPVIEW}/app.bsky.graph.getFollows", params=params)
            out.extend(_account(view) for view in (data.get("follows") or []) if view.get("did")); cursor = data.get("cursor")
            if not cursor: return out

    def get_author_feed(self, actor_did: str, since: datetime, *, max_pages: int = 10) -> list[FeedEvent]:
        cursor = None; out: list[FeedEvent] = []
        for _ in range(max_pages):
            params: dict[str, Any] = {"actor": actor_did, "limit": 100, "filter": "posts_with_replies"}
            if cursor: params["cursor"] = cursor
            data = get_json(self.s, f"{APPVIEW}/app.bsky.feed.getAuthorFeed", params=params); feed = data.get("feed") or []
            if not feed: break
            oldest: datetime | None = None
            for item in feed:
                event = parse_feed_item(actor_did, item)
                if event is None: continue
                try:
                    dt = isoparse(event.signal_timestamp); dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError): continue
                oldest = dt if oldest is None or dt < oldest else oldest
                if dt >= since and event.links: out.append(event)
            if oldest is not None and oldest < since: break
            cursor = data.get("cursor")
            if not cursor: break
        return out
