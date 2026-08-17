from __future__ import annotations

from typing import Any

from neuro_digest.db import SupabaseDataAPI
from neuro_digest.embeddings import vector_literal


class RankingRepository:
    def __init__(self, api: SupabaseDataAPI | None = None):
        self.api = api or SupabaseDataAPI()

    def papers_missing_embeddings(self, *, limit: int = 256) -> list[dict[str, Any]]:
        return self.api._request("GET", "papers", params={"select": "id,title,abstract,journal,embedding_model,embedding_input_hash", "embedding": "is.null", "or": "(title.not.is.null,abstract.not.is.null)", "order": "updated_at.asc", "limit": limit}) or []

    def save_paper_embeddings(self, rows: list[dict[str, Any]]) -> None:
        if rows:
            self.api._request("POST", "papers", params={"on_conflict": "id"}, json=rows, prefer="resolution=merge-duplicates,return=minimal")

    def profiles_with_research_descriptions(self) -> list[dict[str, Any]]:
        return self.api._request("GET", "profiles", params={"select": "user_id,research_description,updated_at,discovery_balance", "research_description": "not.is.null", "order": "created_at.asc"}) or []

    def get_user_embedding(self, user_id: str) -> dict[str, Any] | None:
        return self.api.select_one("user_embeddings", "user_id", user_id)

    def save_declared_user_embedding(self, user_id: str, *, embedding: list[float], model: str, input_hash: str) -> None:
        self.api.upsert("user_embeddings", {"user_id": user_id, "declared_embedding": vector_literal(embedding), "embedding_model": model, "declared_input_hash": input_hash}, on_conflict="user_id")

    def replace_inferred_features(self, user_id: str, features: list[dict[str, Any]]) -> None:
        self.api._request("DELETE", "user_preference_features", params={"user_id": f"eq.{user_id}", "source": "eq.INFERRED"}, prefer="return=minimal")
        if not features:
            return
        rows = [{"user_id": user_id, "feature_type": feature["feature_type"], "feature_value": feature["feature_value"], "weight": feature.get("weight", 1.0), "source": "INFERRED"} for feature in features]
        self.api._request("POST", "user_preference_features", params={"on_conflict": "user_id,feature_type,feature_value,source"}, json=rows, prefer="resolution=merge-duplicates,return=minimal")

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        return self.api.select_one("profiles", "user_id", user_id)

    def get_user_features(self, user_id: str) -> list[dict[str, Any]]:
        return self.api._request("GET", "user_preference_features", params={"select": "feature_type,feature_value,weight,source", "user_id": f"eq.{user_id}"}) or []

    def match_papers(self, embedding: list[float], published_after: str, *, limit: int = 300) -> list[dict[str, Any]]:
        return self.api.rpc("match_papers", {"p_query_embedding": vector_literal(embedding), "p_published_after": published_after, "p_match_count": limit}) or []

    def score_papers(self, paper_ids: list[str], embedding: list[float] | None) -> dict[str, float]:
        if not paper_ids or not embedding:
            return {}
        rows = self.api.rpc("score_papers", {"p_paper_ids": paper_ids, "p_query_embedding": vector_literal(embedding)}) or []
        return {row["paper_id"]: float(row["similarity"]) for row in rows}

    def network_candidates(self, user_id: str, published_after: str) -> list[dict[str, Any]]:
        return self.api.rpc("get_user_network_candidates", {"p_user_id": user_id, "p_published_after": published_after}) or []

    def broad_candidates(self, published_after: str, venues: list[str], *, limit: int = 200) -> list[dict[str, Any]]:
        return self.api.rpc("get_broad_candidates", {"p_published_after": published_after, "p_priority_venues": [venue.casefold() for venue in venues], "p_limit": limit}) or []

    def seen_paper_ids(self, user_id: str) -> set[str]:
        rows = self.api.rpc("get_user_seen_papers", {"p_user_id": user_id}) or []
        return {row["paper_id"] for row in rows}

    def get_papers(self, paper_ids: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for offset in range(0, len(paper_ids), 100):
            chunk = paper_ids[offset:offset + 100]
            if not chunk:
                continue
            rows = self.api._request("GET", "papers", params={"select": "id,title,abstract,journal,publication_date,first_online_date,cited_by_count,created_at,metadata", "id": "in.(" + ",".join(chunk) + ")"}) or []
            out.update({row["id"]: row for row in rows})
        return out
