from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from neuro_digest.config import load_config
from neuro_digest.embeddings import parse_vector, vector_literal
from neuro_digest.features import extract_paper_features, load_taxonomy
from neuro_digest.ranking_db import RankingRepository


def _normalize(vector: list[float]) -> list[float] | None:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 1e-12:
        return None
    return [value / norm for value in vector]


def weighted_centroid(rows: list[dict[str, Any]], *, positive: bool) -> list[float] | None:
    selected: list[tuple[float, list[float]]] = []
    for row in rows:
        weight = float(row.get("effective_weight") or 0.0)
        if (positive and weight <= 0) or (not positive and weight >= 0):
            continue
        vector = parse_vector(row.get("embedding"))
        if vector:
            selected.append((abs(weight), vector))
    if not selected:
        return None
    dimensions = len(selected[0][1])
    if any(len(vector) != dimensions for _, vector in selected):
        raise ValueError("Feedback embeddings have inconsistent dimensions")
    total = sum(weight for weight, _ in selected)
    centroid = [sum(weight * vector[index] for weight, vector in selected) / total for index in range(dimensions)]
    return _normalize(centroid)


class FeedbackRepository:
    def __init__(self, ranking_repository: RankingRepository | None = None):
        self.ranking = ranking_repository or RankingRepository()
        self.api = self.ranking.api

    def user_ids(self) -> list[str]:
        rows = self.api._request("GET", "profiles", params={"select": "user_id", "order": "created_at.asc"}) or []
        return [row["user_id"] for row in rows]

    def effective_feedback(self, user_id: str, config: dict[str, Any]) -> list[dict[str, Any]]:
        weights = config.get("weights", {})
        return self.api.rpc("get_effective_paper_feedback", {"p_user_id": user_id, "p_click_weight": float(weights.get("click", 0.25)), "p_save_weight": float(weights.get("save", 1.0)), "p_more_weight": float(weights.get("more_like_this", 1.5)), "p_less_weight": float(weights.get("less_like_this", 1.5)), "p_neutral_less_reasons": config.get("neutral_less_reasons", ["already_knew_it"])}) or []

    def save_learned_embeddings(self, user_id: str, *, positive: list[float] | None, negative: list[float] | None, feedback_count: int) -> None:
        self.api.upsert("user_embeddings", {"user_id": user_id, "learned_positive_embedding": vector_literal(positive) if positive else None, "learned_negative_embedding": vector_literal(negative) if negative else None, "feedback_count": feedback_count}, on_conflict="user_id")

    def replace_learned_features(self, user_id: str, features: list[dict[str, Any]]) -> None:
        self.api._request("DELETE", "user_preference_features", params={"user_id": f"eq.{user_id}", "source": "eq.LEARNED"}, prefer="return=minimal")
        if features:
            self.api._request("POST", "user_preference_features", params={"on_conflict": "user_id,feature_type,feature_value,source"}, json=[{**feature, "user_id": user_id, "source": "LEARNED"} for feature in features], prefer="resolution=merge-duplicates,return=minimal")


def learned_features(rows: list[dict[str, Any]], papers: dict[str, dict[str, Any]], taxonomy: dict[str, dict[str, list[str]]], *, min_absolute_signal: float = 1.0, saturation_signal: float = 3.0) -> list[dict[str, Any]]:
    signals: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        paper = papers.get(row["paper_id"])
        if not paper:
            continue
        weight = float(row.get("effective_weight") or 0.0)
        for feature in extract_paper_features(paper, taxonomy):
            signals[feature] += weight
    out = []
    for (feature_type, feature_value), signal in sorted(signals.items()):
        if abs(signal) < min_absolute_signal:
            continue
        weight = max(-1.0, min(1.0, signal / max(1e-9, saturation_signal)))
        out.append({"feature_type": feature_type, "feature_value": feature_value, "weight": weight})
    return out


def refresh_feedback_models(*, repository: FeedbackRepository | None = None, config_path: str = "config/feedback.yaml", taxonomy_path: str = "config/feature_taxonomy.yaml") -> tuple[int, int]:
    repo = repository or FeedbackRepository()
    config = load_config(config_path)
    taxonomy = load_taxonomy(taxonomy_path)
    users_refreshed = feedback_papers = 0
    feature_cfg = config.get("learned_features", {})
    for user_id in repo.user_ids():
        rows = repo.effective_feedback(user_id, config)
        positive = weighted_centroid(rows, positive=True)
        negative = weighted_centroid(rows, positive=False)
        repo.save_learned_embeddings(user_id, positive=positive, negative=negative, feedback_count=len(rows))
        paper_ids = [row["paper_id"] for row in rows]
        papers = repo.ranking.get_papers(paper_ids) if paper_ids else {}
        repo.replace_learned_features(user_id, learned_features(rows, papers, taxonomy, min_absolute_signal=float(feature_cfg.get("min_absolute_signal", 1.0)), saturation_signal=float(feature_cfg.get("saturation_signal", 3.0))))
        users_refreshed += 1
        feedback_papers += len(rows)
    return users_refreshed, feedback_papers
