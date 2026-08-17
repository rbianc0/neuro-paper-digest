from __future__ import annotations

from typing import Any

from neuro_digest.db import SupabaseDataAPI


class DigestRepository:
    def __init__(self, api: SupabaseDataAPI | None = None):
        self.api = api or SupabaseDataAPI()

    def newsletter_users(self) -> list[dict[str, Any]]:
        return self.api.rpc("get_newsletter_users", {}) or []

    def existing_digest(self, user_id: str, period_start: str, period_end: str, version: str) -> dict[str, Any] | None:
        return self.api.select_one_where("digests", {"user_id": user_id, "period_start": period_start, "period_end": period_end, "version": version})

    def insert_digest(self, row: dict[str, Any]) -> dict[str, Any]:
        return self.api.insert("digests", row)

    def update_digest(self, digest_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return self.api.update("digests", digest_id, changes)

    def insert_items(self, rows: list[dict[str, Any]]) -> None:
        if rows:
            self.api._request("POST", "digest_items", json=rows, prefer="return=minimal")

    def insert_tokens(self, rows: list[dict[str, Any]]) -> None:
        if rows:
            self.api._request("POST", "interaction_tokens", json=rows, prefer="return=minimal")

    def paper_data(self, paper_ids: list[str]) -> dict[str, dict[str, Any]]:
        rows = self.api.rpc("get_digest_paper_data", {"p_paper_ids": paper_ids}) or []
        return {row["paper_id"]: row for row in rows}

    def pending_delivery(self) -> list[dict[str, Any]]:
        return self.api._request("GET", "digests", params={"select": "*", "status": "eq.GENERATED", "sent_at": "is.null", "order": "generated_at.asc"}) or []
