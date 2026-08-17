from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from neuro_digest.db import SupabaseDataAPI


def token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@dataclass
class InteractionLink:
    raw_token: str
    url: str
    db_row: dict[str, Any]


def build_interaction_link(*, base_url: str, user_id: str, paper_id: str, digest_id: str, action_type: str, expiry_days: int, redirect_url: str | None = None, single_use: bool = True, metadata: dict[str, Any] | None = None) -> InteractionLink:
    raw = secrets.token_urlsafe(32)
    path = "r" if action_type == "CLICK" else "a"
    url = f"{base_url.rstrip('/')}/{path}/{raw}"
    row = {
        "token_hash": token_hash(raw),
        "user_id": user_id,
        "paper_id": paper_id,
        "digest_id": digest_id,
        "action_type": action_type,
        "redirect_url": redirect_url,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=expiry_days)).isoformat(),
        "single_use": single_use,
        "metadata": metadata or {},
    }
    return InteractionLink(raw, url, row)


class InteractionRepository:
    def __init__(self, api: SupabaseDataAPI | None = None):
        self.api = api or SupabaseDataAPI()

    def inspect(self, raw_token: str) -> dict[str, Any] | None:
        rows = self.api.rpc("get_interaction_token", {"p_token_hash": token_hash(raw_token)}) or []
        return rows[0] if rows else None

    def consume(self, raw_token: str, expected_action: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        rows = self.api.rpc("consume_interaction_token", {"p_token_hash": token_hash(raw_token), "p_expected_action": expected_action, "p_metadata": metadata or {}}) or []
        if not rows:
            raise RuntimeError("Interaction token could not be redeemed")
        return rows[0]
