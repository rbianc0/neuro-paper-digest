from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from neuro_digest.db import SupabaseDataAPI


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BlueskyRepository:
    """Service-role persistence boundary for shared Bluesky ingestion."""

    def __init__(self, api: SupabaseDataAPI | None = None):
        self.api = api or SupabaseDataAPI()

    def list_profiles_for_sync(self, *, limit: int = 500) -> list[dict[str, Any]]:
        params = {
            "select": "user_id,bluesky_handle,bluesky_did,last_bluesky_sync_at,bluesky_sync_requested_at",
            "bluesky_handle": "not.is.null",
            "order": "bluesky_sync_requested_at.desc.nullslast,last_bluesky_sync_at.asc.nullsfirst",
            "limit": max(1, min(limit, 5000)),
        }
        return self.api._request("GET", "profiles", params=params) or []

    def record_follow_sync_error(self, user_id: str, error: str) -> None:
        self.api._request(
            "PATCH",
            "profiles",
            params={"user_id": f"eq.{user_id}"},
            json={"last_bluesky_sync_error": error[:1000]},
            prefer="return=minimal",
        )

    def upsert_account(self, profile: dict[str, Any]) -> None:
        did = profile.get("did")
        if not did:
            return
        row = {
            "did": did,
            "handle": profile.get("handle"),
            "display_name": profile.get("displayName"),
            "description": profile.get("description"),
            "profile_metadata": {
                "avatar": profile.get("avatar"),
                "labels": profile.get("labels") or [],
            },
            "last_profile_fetched_at": _utc_now(),
        }
        self.api.upsert("bluesky_accounts", row, on_conflict="did")

    def replace_user_follows(self, *, user_id: str, user_did: str, user_handle: str, followed_dids: list[str]) -> int:
        result = self.api.rpc(
            "replace_user_bluesky_follows",
            {
                "p_user_id": user_id,
                "p_bluesky_did": user_did,
                "p_bluesky_handle": user_handle,
                "p_followed_dids": followed_dids,
            },
        )
        return int(result or 0)

    def get_stale_accounts(self, *, stale_before: str, limit: int = 1000) -> list[dict[str, Any]]:
        return self.api.rpc(
            "get_stale_bluesky_accounts",
            {"p_stale_before": stale_before, "p_limit": max(1, min(limit, 5000))},
        ) or []

    def mark_account_fetch_success(self, did: str, *, handle: str | None = None) -> None:
        changes: dict[str, Any] = {
            "last_feed_fetched_at": _utc_now(),
            "fetch_state": "OK",
            "error_count": 0,
            "next_fetch_after": None,
            "last_error": None,
        }
        if handle:
            changes["handle"] = handle
        self.api._request("PATCH", "bluesky_accounts", params={"did": f"eq.{did}"}, json=changes, prefer="return=minimal")

    def mark_account_fetch_error(self, did: str, error_count: int, error: str, next_fetch_after: str) -> None:
        self.api._request(
            "PATCH",
            "bluesky_accounts",
            params={"did": f"eq.{did}"},
            json={
                "fetch_state": "ERROR",
                "error_count": error_count,
                "next_fetch_after": next_fetch_after,
                "last_error": error[:1000],
            },
            prefer="return=minimal",
        )

    def persist_feed_event(self, event: dict[str, Any]) -> None:
        post = event["post"]
        author = post.get("author") or {}
        if not author.get("did"):
            raise ValueError("Bluesky post is missing author DID")
        self.upsert_account(author)

        # A repost is an attention event by the followed actor, not a different
        # type of the underlying original post. Keep those concepts separate.
        post_type = "QUOTE" if event["signal_type"] == "QUOTE" else "POST"
        post_row = {
            "uri": post["uri"],
            "cid": post.get("cid"),
            "author_did": author["did"],
            "text": post.get("text"),
            "created_at": post.get("created_at"),
            "indexed_at": post.get("indexed_at"),
            "post_type": post_type,
            "referenced_uri": post.get("referenced_uri"),
            "extracted_urls": post.get("urls") or [],
            "raw_record": post.get("raw_record") or {},
        }
        self.api.upsert("bluesky_posts", post_row, on_conflict="uri")
        self.api.upsert(
            "bluesky_post_events",
            {
                "event_key": event["event_key"],
                "post_uri": post["uri"],
                "actor_did": event["actor_did"],
                "signal_type": event["signal_type"],
                "signal_timestamp": event["signal_timestamp"],
                "event_uri": event.get("event_uri"),
                "raw_event": event.get("raw_event") or {},
            },
            on_conflict="event_key",
        )
        for link in event.get("links") or []:
            self.api.upsert(
                "bluesky_scholarly_links",
                {
                    "post_uri": post["uri"],
                    "link_key": link["link_key"],
                    "url": link.get("url"),
                    "doi": link.get("doi"),
                    "pmid": link.get("pmid"),
                },
                on_conflict="post_uri,link_key",
            )

    def pending_links(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        return self.api._request(
            "GET",
            "bluesky_scholarly_links",
            params={
                "select": "id,post_uri,link_key,url,doi,pmid,resolution_status",
                "resolution_status": "in.(PENDING,UNRESOLVED)",
                "order": "last_attempted_at.asc.nullsfirst,created_at.asc",
                "limit": max(1, min(limit, 5000)),
            },
        ) or []

    def find_paper_by_identifier(self, identifier_type: str, identifier_value: str) -> str | None:
        row = self.api.select_one_where(
            "paper_identifiers",
            {"identifier_type": identifier_type, "identifier_value": identifier_value},
        )
        return row.get("paper_id") if row else None

    def resolve_link(self, link_id: str, paper_id: str) -> None:
        self.api._request(
            "PATCH",
            "bluesky_scholarly_links",
            params={"id": f"eq.{link_id}"},
            json={
                "resolved_paper_id": paper_id,
                "resolution_status": "RESOLVED",
                "last_attempted_at": _utc_now(),
                "last_error": None,
            },
            prefer="return=minimal",
        )

    def mark_link_unresolved(self, link_id: str, *, error: str | None = None) -> None:
        self.api._request(
            "PATCH",
            "bluesky_scholarly_links",
            params={"id": f"eq.{link_id}"},
            json={
                "resolution_status": "ERROR" if error else "UNRESOLVED",
                "last_attempted_at": _utc_now(),
                "last_error": error[:1000] if error else None,
            },
            prefer="return=minimal",
        )

    def materialize_social_signals(self, *, post_uri: str, paper_id: str) -> int:
        events = self.api._request(
            "GET",
            "bluesky_post_events",
            params={
                "select": "actor_did,signal_type,signal_timestamp",
                "post_uri": f"eq.{post_uri}",
            },
        ) or []
        count = 0
        for event in events:
            self.api.upsert(
                "paper_social_signals",
                {
                    "paper_id": paper_id,
                    "post_uri": post_uri,
                    "actor_did": event["actor_did"],
                    "signal_type": event["signal_type"],
                    "signal_timestamp": event["signal_timestamp"],
                },
                on_conflict="paper_id,post_uri,actor_did,signal_type",
            )
            count += 1
        return count
