from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from neuro_digest.db import SupabaseDataAPI
from neuro_digest.sources.bluesky import BlueskyAccountRef, FeedEvent


class SocialRepository:
    def __init__(self, api: SupabaseDataAPI | None = None): self.api = api or SupabaseDataAPI()

    def profiles_with_bluesky(self) -> list[dict[str, Any]]:
        return self.api._request("GET", "profiles", params={"select": "user_id,bluesky_handle,bluesky_did,last_bluesky_sync_at", "bluesky_handle": "not.is.null", "order": "created_at.asc"}) or []

    def upsert_account(self, account: BlueskyAccountRef, *, profile_fetched: bool = False) -> dict[str, Any]:
        row: dict[str, Any] = {"did": account.did, "handle": account.handle, "display_name": account.display_name}
        if profile_fetched: row.update({"description": account.description, "profile_metadata": account.metadata or {}, "last_profile_fetched_at": datetime.now(timezone.utc).isoformat()})
        return self.api.upsert("bluesky_accounts", row, on_conflict="did")

    def upsert_accounts(self, accounts: list[BlueskyAccountRef], *, profile_fetched: bool = False) -> None:
        unique = {account.did: account for account in accounts if account.did}
        if not unique: return
        fetched_at = datetime.now(timezone.utc).isoformat() if profile_fetched else None; rows: list[dict[str, Any]] = []
        for account in unique.values():
            row: dict[str, Any] = {"did": account.did, "handle": account.handle, "display_name": account.display_name}
            if profile_fetched: row.update({"description": account.description, "profile_metadata": account.metadata or {}, "last_profile_fetched_at": fetched_at})
            rows.append(row)
        self.api._request("POST", "bluesky_accounts", params={"on_conflict": "did"}, json=rows, prefer="resolution=merge-duplicates,return=minimal")

    def replace_follow_graph(self, user_id: str, *, bluesky_did: str, bluesky_handle: str, follows: list[BlueskyAccountRef]) -> int:
        self.upsert_accounts(follows, profile_fetched=True)
        result = self.api.rpc("replace_user_bluesky_follows", {"p_user_id": user_id, "p_bluesky_did": bluesky_did, "p_bluesky_handle": bluesky_handle, "p_followed_dids": [account.did for account in follows]})
        if isinstance(result, int): return result
        if isinstance(result, list) and result: return int(result[0])
        return len(follows)

    def mark_profile_sync_error(self, user_id: str, error: str) -> None:
        self.api._request("PATCH", "profiles", params={"user_id": f"eq.{user_id}"}, json={"last_bluesky_sync_error": error[:1000]}, prefer="return=minimal")

    def stale_accounts(self, stale_before: datetime, *, limit: int = 1000) -> list[dict[str, Any]]:
        return self.api.rpc("get_stale_bluesky_accounts", {"p_stale_before": stale_before.isoformat(), "p_limit": limit}) or []

    def persist_events(self, events: list[FeedEvent]) -> None:
        if not events: return
        self.upsert_accounts([event.post_author for event in events])
        posts: dict[str, dict[str, Any]] = {}; raw_events: dict[str, dict[str, Any]] = {}; links: dict[tuple[str, str], dict[str, Any]] = {}
        for event in events:
            posts[event.post_uri] = {"uri": event.post_uri, "cid": event.cid, "author_did": event.post_author.did, "text": event.text, "created_at": event.created_at, "indexed_at": event.indexed_at, "post_type": event.post_type, "referenced_uri": event.referenced_uri, "extracted_urls": sorted({link.url for link in event.links if link.url}), "raw_record": event.raw_record}
            raw_events[event.event_key] = {"event_key": event.event_key, "post_uri": event.post_uri, "actor_did": event.signal_actor_did, "signal_type": event.signal_type, "signal_timestamp": event.signal_timestamp, "event_uri": event.event_uri, "raw_event": event.raw_event}
            for link in event.links: links[(event.post_uri, link.link_key)] = {"post_uri": event.post_uri, "link_key": link.link_key, "url": link.url, "doi": link.doi, "pmid": link.pmid}
        self.api._request("POST", "bluesky_posts", params={"on_conflict": "uri"}, json=list(posts.values()), prefer="resolution=merge-duplicates,return=minimal")
        self.api._request("POST", "bluesky_post_events", params={"on_conflict": "event_key"}, json=list(raw_events.values()), prefer="resolution=merge-duplicates,return=minimal")
        if links: self.api._request("POST", "bluesky_scholarly_links", params={"on_conflict": "post_uri,link_key"}, json=list(links.values()), prefer="resolution=ignore-duplicates,return=minimal")

    def mark_account_success(self, did: str) -> None:
        self.api._request("PATCH", "bluesky_accounts", params={"did": f"eq.{did}"}, json={"last_feed_fetched_at": datetime.now(timezone.utc).isoformat(), "fetch_state": "OK", "error_count": 0, "next_fetch_after": None, "last_error": None}, prefer="return=minimal")

    def mark_account_error(self, did: str, error: str) -> None:
        current = self.api.select_one("bluesky_accounts", "did", did) or {}; count = int(current.get("error_count") or 0) + 1; backoff_hours = min(24, 2 ** min(count, 4))
        self.api._request("PATCH", "bluesky_accounts", params={"did": f"eq.{did}"}, json={"fetch_state": "ERROR", "error_count": count, "next_fetch_after": (datetime.now(timezone.utc) + timedelta(hours=backoff_hours)).isoformat(), "last_error": error[:1000]}, prefer="return=minimal")

    def pending_links(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        return self.api._request("GET", "bluesky_scholarly_links", params={"select": "*", "resolution_status": "in.(PENDING,UNRESOLVED,ERROR)", "order": "last_attempted_at.asc.nullsfirst,created_at.asc", "limit": limit}) or []

    def events_for_post(self, post_uri: str) -> list[dict[str, Any]]:
        return self.api._request("GET", "bluesky_post_events", params={"select": "post_uri,actor_did,signal_type,signal_timestamp", "post_uri": f"eq.{post_uri}"}) or []

    def paper_for_identifier(self, identifier_type: str, identifier_value: str) -> str | None:
        row = self.api.select_one_where("paper_identifiers", {"identifier_type": identifier_type, "identifier_value": identifier_value}); return row.get("paper_id") if row else None

    def paper_for_title_key(self, title_key: str) -> str | None:
        row = self.api.select_one("papers", "title_key", title_key); return row.get("id") if row else None

    def mark_link_resolved(self, link_id: str, paper_id: str, *, doi: str | None = None, pmid: str | None = None) -> None:
        payload: dict[str, Any] = {"resolved_paper_id": paper_id, "resolution_status": "RESOLVED", "last_attempted_at": datetime.now(timezone.utc).isoformat(), "last_error": None}
        if doi: payload["doi"] = doi
        if pmid: payload["pmid"] = pmid
        self.api._request("PATCH", "bluesky_scholarly_links", params={"id": f"eq.{link_id}"}, json=payload, prefer="return=minimal")

    def mark_link_unresolved(self, link_id: str, *, error: str | None = None) -> None:
        self.api._request("PATCH", "bluesky_scholarly_links", params={"id": f"eq.{link_id}"}, json={"resolution_status": "ERROR" if error else "UNRESOLVED", "last_attempted_at": datetime.now(timezone.utc).isoformat(), "last_error": error[:1000] if error else None}, prefer="return=minimal")

    def create_paper_signal(self, paper_id: str, event: dict[str, Any]) -> None:
        self.api.upsert("paper_social_signals", {"paper_id": paper_id, "post_uri": event["post_uri"], "actor_did": event["actor_did"], "signal_type": event["signal_type"], "signal_timestamp": event["signal_timestamp"]}, on_conflict="paper_id,post_uri,actor_did,signal_type")
