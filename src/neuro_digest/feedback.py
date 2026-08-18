from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from neuro_digest.config import load_config
from neuro_digest.db import SupabaseDataAPI
from neuro_digest.embeddings import vector_literal


@dataclass(frozen=True)
class FeedbackWeights:
    click: float = 0.25
    save: float = 1.0
    more_like_this: float = 1.5
    less_like_this: float = 1.5


@dataclass
class LearningState:
    user_id: str
    feedback_count: int
    positive_count: int
    negative_count: int
    learned_positive_embedding: list[float] | None
    learned_negative_embedding: list[float] | None


def parse_vector(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [float(x) for x in value]
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            body = text[1:-1].strip()
            return [float(x) for x in body.split(",")] if body else []
    raise ValueError(f"Unsupported pgvector representation: {type(value).__name__}")


def weighted_centroid(rows: list[dict[str, Any]], *, positive: bool) -> list[float] | None:
    selected: list[tuple[float, list[float]]] = []
    dimensions: int | None = None
    for row in rows:
        weight = float(row.get("effective_weight") or 0.0)
        if (weight > 0) != positive or weight == 0:
            continue
        vector = parse_vector(row.get("embedding"))
        if not vector:
            continue
        if dimensions is None:
            dimensions = len(vector)
        if len(vector) != dimensions:
            raise ValueError("Feedback embeddings have inconsistent dimensions")
        selected.append((abs(weight), vector))
    if not selected or dimensions is None:
        return None
    total_weight = sum(weight for weight, _ in selected)
    centroid = [0.0] * dimensions
    for weight, vector in selected:
        for index, value in enumerate(vector):
            centroid[index] += weight * value
    return [value / total_weight for value in centroid]


def learned_weight(feedback_count: int, *, maximum: float = 0.35, start_after: int = 2, full_after: int = 10) -> float:
    if feedback_count < start_after:
        return 0.0
    if full_after <= start_after:
        return max(0.0, min(1.0, maximum))
    progress = (feedback_count - start_after + 1) / (full_after - start_after + 1)
    return max(0.0, min(maximum, maximum * min(1.0, progress)))


class FeedbackRepository:
    def __init__(self, api: SupabaseDataAPI | None = None):
        self.api = api or SupabaseDataAPI()

    def effective_feedback(self, user_id: str, *, weights: FeedbackWeights, neutral_less_reasons: list[str]) -> list[dict[str, Any]]:
        return self.api.rpc(
            "get_effective_paper_feedback",
            {
                "p_user_id": user_id,
                "p_click_weight": weights.click,
                "p_save_weight": weights.save,
                "p_more_weight": weights.more_like_this,
                "p_less_weight": weights.less_like_this,
                "p_neutral_less_reasons": neutral_less_reasons,
            },
        ) or []

    def save_learning_state(self, state: LearningState) -> None:
        payload: dict[str, Any] = {
            "user_id": state.user_id,
            "feedback_count": state.feedback_count,
            "learned_positive_embedding": vector_literal(state.learned_positive_embedding) if state.learned_positive_embedding else None,
            "learned_negative_embedding": vector_literal(state.learned_negative_embedding) if state.learned_negative_embedding else None,
        }
        self.api.upsert("user_embeddings", payload, on_conflict="user_id")


def refresh_user_learning(user_id: str, *, config_path: str = "config/feedback.yaml", repository: FeedbackRepository | None = None) -> LearningState:
    config = load_config(config_path)
    feedback_cfg = config.get("feedback", {})
    weight_cfg = feedback_cfg.get("weights", {})
    weights = FeedbackWeights(
        click=float(weight_cfg.get("click", 0.25)),
        save=float(weight_cfg.get("save", 1.0)),
        more_like_this=float(weight_cfg.get("more_like_this", 1.5)),
        less_like_this=float(weight_cfg.get("less_like_this", 1.5)),
    )
    repo = repository or FeedbackRepository()
    rows = repo.effective_feedback(
        user_id,
        weights=weights,
        neutral_less_reasons=list(feedback_cfg.get("neutral_less_reasons", ["already_knew_it"])),
    )
    positive = weighted_centroid(rows, positive=True)
    negative = weighted_centroid(rows, positive=False)
    state = LearningState(
        user_id=user_id,
        feedback_count=len(rows),
        positive_count=sum(float(row.get("effective_weight") or 0) > 0 for row in rows),
        negative_count=sum(float(row.get("effective_weight") or 0) < 0 for row in rows),
        learned_positive_embedding=positive,
        learned_negative_embedding=negative,
    )
    repo.save_learning_state(state)
    return state
