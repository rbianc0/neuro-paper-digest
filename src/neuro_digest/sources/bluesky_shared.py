from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from dateutil.parser import isoparse

from neuro_digest.http import get_json, session
from neuro_digest.util import canonical_doi, extract_dois, extract_pmid, extract_urls, scholarly_url

BASE = "https://public.api.bsky.app/xrpc"


def _walk_strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _walk_strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_strings(value)


def get_profile(actor: str) -> dict[str, Any]:
    return get_json(session(), f"{BASE}/app.bsky.actor.getProfile", params={"actor": actor})


def get_follows(actor: str) -> list[dict[str, Any]]:
    s = session(); cursor: str | None = None; follows: list[dict[str, Any]] = []
    while True:
        params: dict[str, Any] = {"actor": actor, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        data = get_json(s, f"{BASE}/app.bsky.graph.getFollows", params=params)
        follows.extend(data.get("follows") or [])
        cursor = data.get("cursor")
        if not cursor:
            return follows


def _event_time(item: dict[str, Any]) -> str | None:
    reason = item.get("reason") or {}; post = item.get("post") or {}; record = post.get("record") or {}
    return reason.get("indexedAt") or record.get("createdAt") or post.get("indexedAt")


def _signal_type(item: dict[str, Any]) -> str:
    reason_type = ((item.get("reason") or {}).get("$type") or "")
    if reason_type.endswith("#reasonRepost"):
        return "REPOST"
    record = ((item.get("post") or {}).get("record") or {})
    embed_type = ((record.get("embed") or {}).get("$type") or "") if isinstance(record.get("embed"), dict) else ""
    return "QUOTE" if "embed.record" in embed_type or "recordWithMedia" in embed_type else "POST"


def _quote_uri(item: dict[str, Any]) -> str | None:
    post = item.get("post") or {}; view_embed = post.get("embed") or {}
    if not isinstance(view_embed, dict):
        return None
    record = view_embed.get("record")
    if isinstance(record, dict):
        if isinstance(record.get("record"), dict):
            return record["record"].get("uri")
        return record.get("uri")
    return None


def _scholarly_links(item: dict[str, Any]) -> list[dict[str, str | None]]:
    post = item.get("post") or {}; record = post.get("record") or {}; text = record.get("text") or ""
    urls = {u for u in extract_urls(text) if scholarly_url(u)}
    dois = {canonical_doi(d) for d in extract_dois(text)}; dois.discard(None)
    pmids: set[str] = set()
    for raw in _walk_strings({"facets": record.get("facets"), "record_embed": record.get("embed"), "view_embed": post.get("embed")}):
        if raw.startswith("http://") or raw.startswith("https://"):
            if scholarly_url(raw):
                urls.add(raw)
            dois.update(d for d in (canonical_doi(x) for x in extract_dois(raw)) if d)
            pmid = extract_pmid(raw)
            if pmid:
                pmids.add(str(pmid))
    for url in list(urls):
        dois.update(d for d in (canonical_doi(x) for x in extract_dois(url)) if d)
        pmid = extract_pmid(url)
        if pmid:
            pmids.add(str(pmid))

    links: dict[str, dict[str, str | None]] = {}
    for doi in sorted(dois):
        links[f"doi:{doi}"] = {"link_key": f"doi:{doi}", "doi": doi, "pmid": None, "url": f"https://doi.org/{doi}"}
    for pmid in sorted(pmids):
        links[f"pmid:{pmid}"] = {"link_key": f"pmid:{pmid}", "doi": None, "pmid": pmid, "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"}
    for url in sorted(urls):
        key = f"url:{url}"
        links.setdefault(key, {"link_key": key, "doi": None, "pmid": None, "url": url})
    return list(links.values())


def normalize_feed_item(followed_did: str, item: dict[str, Any]) -> dict[str, Any] | None:
    post = item.get("post") or {}; author = post.get("author") or {}; uri = post.get("uri")
    if not uri or not author.get("did"):
        return None
    signal_type = _signal_type(item); timestamp = _event_time(item) or post.get("indexedAt")
    if not timestamp:
        return None
    links = _scholarly_links(item)
    if not links:
        return None
    reason = item.get("reason") or {}; event_uri = reason.get("uri")
    event_key = event_uri or f"{followed_did}|{signal_type}|{uri}|{timestamp}"
    record = post.get("record") or {}
    return {
        "event_key": event_key,
        "actor_did": followed_did,
        "signal_type": signal_type,
        "signal_timestamp": timestamp,
        "event_uri": event_uri,
        "raw_event": {"reason": reason},
        "links": links,
        "post": {
            "uri": uri,
            "cid": post.get("cid"),
            "author": author,
            "text": record.get("text") or "",
            "created_at": record.get("createdAt"),
            "indexed_at": post.get("indexedAt"),
            "referenced_uri": _quote_uri(item),
            "urls": [link["url"] for link in links if link.get("url")],
            "raw_record": record,
        },
    }


def fetch_author_feed_events(actor: str, *, since: datetime, max_pages: int = 10) -> list[dict[str, Any]]:
    s = session(); cursor: str | None = None; events: list[dict[str, Any]] = []
    since = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    for _ in range(max_pages):
        params: dict[str, Any] = {"actor": actor, "limit": 100, "filter": "posts_with_replies"}
        if cursor:
            params["cursor"] = cursor
        data = get_json(s, f"{BASE}/app.bsky.feed.getAuthorFeed", params=params)
        feed = data.get("feed") or []
        if not feed:
            break
        oldest: datetime | None = None
        for item in feed:
            timestamp = _event_time(item)
            if timestamp:
                try:
                    dt = isoparse(timestamp); dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                    oldest = dt if oldest is None or dt < oldest else oldest
                    if dt < since:
                        continue
                except ValueError:
                    pass
            normalized = normalize_feed_item(actor, item)
            if normalized:
                events.append(normalized)
        if oldest and oldest < since:
            break
        cursor = data.get("cursor")
        if not cursor:
            break
    return events
