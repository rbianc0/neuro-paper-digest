from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any

from dateutil.parser import isoparse

from neuro_digest.config import load_config
from neuro_digest.db import SupabaseDataAPI
from neuro_digest.feedback import learned_weight

TOKEN_RE = re.compile(r"[a-z][a-z0-9+:/-]{2,}")
STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "using", "use", "study", "studies", "paper",
    "research", "brain", "neural", "neuroscience", "analysis", "data", "based", "effects", "effect",
    "this", "that", "these", "those", "between", "during", "across", "through", "within", "their",
}


@dataclass
class RankedPaper:
    paper_id: str
    final_score: float
    semantic_score: float
    bluesky_score: float
    fit_score: float
    quality_score: float
    broad_discovery_score: float
    novelty_score: float
    recency_score: float
    lane: str
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _saturating_count(value: int | float, scale: float = 2.0) -> float:
    return 1.0 - math.exp(-max(0.0, float(value)) / scale)


def _days_old(value: str | None, today: date) -> int:
    if not value:
        return 999
    try:
        return max(0, (today - date.fromisoformat(value[:10])).days)
    except ValueError:
        return 999


def _signal_days_old(value: str | None) -> float:
    if not value:
        return 999.0
    try:
        dt = isoparse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
    except ValueError:
        return 999.0


def bluesky_subscore(network: dict[str, Any] | None) -> float:
    if not network:
        return 0.0
    independent = _saturating_count(network.get("independent_actors", 0), 2.0)
    direct = _saturating_count(network.get("direct_count", 0), 1.5)
    quote = _saturating_count(network.get("quote_count", 0), 1.5)
    repost = _saturating_count(network.get("repost_count", 0), 2.5)
    recency = math.exp(-_signal_days_old(network.get("latest_signal_at")) / 7.0)
    social = 0.45 * independent + 0.20 * direct + 0.15 * quote + 0.05 * repost + 0.15 * recency
    if network.get("authored_by_followed"):
        social = max(0.72, social)
    return _clamp(social)


def quality_subscore(paper: dict[str, Any], *, priority_venues: set[str]) -> float:
    venue = (paper.get("journal") or "").strip().casefold()
    venue_component = 1.0 if venue in priority_venues else 0.0
    citations = max(0, int(paper.get("cited_by_count") or 0))
    citation_component = min(1.0, math.log1p(citations) / math.log(21.0))
    return _clamp(0.55 * venue_component + 0.45 * citation_component)


def recency_subscore(paper: dict[str, Any], *, today: date) -> float:
    age = _days_old(paper.get("first_online_date") or paper.get("publication_date"), today)
    return _clamp(math.exp(-age / 14.0))


def learned_similarity(positive_similarity: float | None, negative_similarity: float | None) -> float | None:
    if positive_similarity is not None and negative_similarity is not None:
        return _clamp(0.5 + 0.5 * (positive_similarity - negative_similarity))
    if positive_similarity is not None:
        return _clamp(positive_similarity)
    if negative_similarity is not None:
        return _clamp(1.0 - negative_similarity)
    return None


def personal_semantic_similarity(
    declared_similarity: float,
    positive_similarity: float | None,
    negative_similarity: float | None,
    learned_alpha: float,
) -> float:
    learned = learned_similarity(positive_similarity, negative_similarity)
    if learned is None or learned_alpha <= 0:
        return _clamp(declared_similarity)
    alpha = _clamp(learned_alpha)
    return _clamp((1.0 - alpha) * declared_similarity + alpha * learned)


def _tokens(text: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(text.casefold()) if token not in STOPWORDS}


def _detected_features(text: str, feature_config: dict[str, Any]) -> set[str]:
    normalized = " " + " ".join(text.casefold().split()) + " "
    found: set[str] = set()
    for feature_type, groups in feature_config.items():
        for name, aliases in (groups or {}).items():
            if any(f" {alias.casefold()} " in normalized for alias in aliases):
                found.add(f"{feature_type}:{name}")
    return found


def fit_subscore(profile_text: str, paper: dict[str, Any], *, feature_config: dict[str, Any]) -> float:
    paper_text = " ".join(filter(None, [paper.get("title"), paper.get("abstract")]))
    profile_features = _detected_features(profile_text, feature_config)
    paper_features = _detected_features(paper_text, feature_config)
    structured = len(profile_features & paper_features) / max(1, len(profile_features)) if profile_features else 0.0
    profile_tokens = _tokens(profile_text)
    paper_tokens = _tokens(paper_text)
    keyword = len(profile_tokens & paper_tokens) / max(1, min(len(profile_tokens), 20)) if profile_tokens else 0.0
    return _clamp(0.70 * structured + 0.30 * min(1.0, keyword * 3.0))


class RankingRepository:
    def __init__(self, api: SupabaseDataAPI | None = None):
        self.api = api or SupabaseDataAPI()

    def profile(self, user_id: str) -> dict[str, Any]:
        row = self.api.select_one("profiles", "user_id", user_id)
        if not row:
            raise ValueError(f"No Neurofeed profile for user {user_id}")
        return row

    def embeddings(self, user_id: str) -> dict[str, Any]:
        row = self.api.select_one("user_embeddings", "user_id", user_id)
        if not row or not row.get("declared_embedding"):
            raise ValueError("User declared embedding is missing; run neurofeed-embed first")
        return row

    def semantic_candidates(self, vector: str, published_after: str, limit: int) -> list[dict[str, Any]]:
        return self.api.rpc("match_papers", {"p_query_embedding": vector, "p_published_after": published_after, "p_match_count": limit}) or []

    def semantic_scores(self, paper_ids: list[str], vector: str) -> list[dict[str, Any]]:
        if not paper_ids:
            return []
        return self.api.rpc("score_papers", {"p_paper_ids": paper_ids, "p_query_embedding": vector}) or []

    def network_candidates(self, user_id: str, published_after: str) -> list[dict[str, Any]]:
        return self.api.rpc("get_user_network_candidates", {"p_user_id": user_id, "p_published_after": published_after}) or []

    def broad_candidates(self, published_after: str, priority_venues: list[str], limit: int) -> list[dict[str, Any]]:
        return self.api.rpc("get_broad_candidates", {"p_published_after": published_after, "p_priority_venues": priority_venues, "p_limit": limit}) or []

    def seen_papers(self, user_id: str) -> set[str]:
        return {row["paper_id"] for row in (self.api.rpc("get_user_seen_papers", {"p_user_id": user_id}) or [])}

    def papers(self, paper_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not paper_ids:
            return {}
        output: dict[str, dict[str, Any]] = {}
        for offset in range(0, len(paper_ids), 100):
            batch = paper_ids[offset:offset + 100]
            rows = self.api._request(
                "GET", "papers",
                params={
                    "select": "id,title,abstract,journal,publication_date,first_online_date,cited_by_count,canonical_doi,metadata",
                    "id": "in.(" + ",".join(batch) + ")",
                },
            ) or []
            output.update({row["id"]: row for row in rows})
        return output


def _score_missing(repo: RankingRepository, paper_ids: list[str], vector: str | None, existing: dict[str, float]) -> None:
    if not vector:
        return
    missing = [paper_id for paper_id in paper_ids if paper_id not in existing]
    for row in repo.semantic_scores(missing, vector):
        existing[row["paper_id"]] = _clamp(row.get("similarity", 0.0))


def rank_for_user(
    user_id: str,
    *,
    config_path: str = "config/ranking.yaml",
    feedback_config_path: str = "config/feedback.yaml",
    repository: RankingRepository | None = None,
    today: date | None = None,
) -> list[RankedPaper]:
    config = load_config(config_path)
    feedback_config = load_config(feedback_config_path)
    ranking_cfg = config.get("ranking", {})
    feature_cfg = config.get("features", {})
    learning_cfg = feedback_config.get("learning", {})
    repo = repository or RankingRepository()
    today = today or date.today()

    profile = repo.profile(user_id)
    profile_text = profile.get("research_description") or ""
    embedding_state = repo.embeddings(user_id)
    declared_vector = embedding_state["declared_embedding"]
    positive_vector = embedding_state.get("learned_positive_embedding")
    negative_vector = embedding_state.get("learned_negative_embedding")
    feedback_count = int(embedding_state.get("feedback_count") or 0)
    learned_alpha = learned_weight(
        feedback_count,
        maximum=float(learning_cfg.get("learned_weight_max", 0.35)),
        start_after=int(learning_cfg.get("start_after_effective_papers", 2)),
        full_after=int(learning_cfg.get("full_weight_after_effective_papers", 10)),
    )

    lookback_days = int(ranking_cfg.get("lookback_days", 21))
    published_after = date.fromordinal(today.toordinal() - lookback_days).isoformat()
    priority_venues = [venue.casefold() for venue in ranking_cfg.get("priority_venues", [])]
    semantic_limit = int(ranking_cfg.get("semantic_candidates", 400))

    declared_rows = repo.semantic_candidates(declared_vector, published_after, semantic_limit)
    learned_rows = repo.semantic_candidates(positive_vector, published_after, semantic_limit) if positive_vector and learned_alpha > 0 else []
    network_rows = repo.network_candidates(user_id, published_after)
    broad_rows = repo.broad_candidates(published_after, priority_venues, int(ranking_cfg.get("broad_candidates", 200)))
    seen = repo.seen_papers(user_id)

    declared_candidate_ids = {row["paper_id"] for row in declared_rows}
    learned_candidate_ids = {row["paper_id"] for row in learned_rows}
    declared_scores = {row["paper_id"]: _clamp(row.get("similarity", 0.0)) for row in declared_rows}
    positive_scores = {row["paper_id"]: _clamp(row.get("similarity", 0.0)) for row in learned_rows}
    negative_scores: dict[str, float] = {}
    network = {row["paper_id"]: row for row in network_rows}
    broad = {row["paper_id"]: row for row in broad_rows}

    union_ids = list(dict.fromkeys([*declared_scores, *positive_scores, *network, *broad]))
    union_ids = [paper_id for paper_id in union_ids if paper_id not in seen]

    _score_missing(repo, union_ids, declared_vector, declared_scores)
    if learned_alpha > 0:
        _score_missing(repo, union_ids, positive_vector, positive_scores)
        _score_missing(repo, union_ids, negative_vector, negative_scores)

    papers = repo.papers(union_ids)
    weights = ranking_cfg.get("weights", {})
    priority_set = set(priority_venues)
    ranked: list[RankedPaper] = []

    for paper_id in union_ids:
        paper = papers.get(paper_id)
        if not paper:
            continue
        declared_similarity = declared_scores.get(paper_id, 0.0)
        positive_similarity = positive_scores.get(paper_id) if positive_vector else None
        negative_similarity = negative_scores.get(paper_id) if negative_vector else None
        learned_semantic = learned_similarity(positive_similarity, negative_similarity)
        semantic_score = personal_semantic_similarity(
            declared_similarity,
            positive_similarity,
            negative_similarity,
            learned_alpha,
        )
        bluesky_score = bluesky_subscore(network.get(paper_id))
        fit_score = fit_subscore(profile_text, paper, feature_config=feature_cfg)
        quality_score = quality_subscore(paper, priority_venues=priority_set)
        broad_row = broad.get(paper_id)
        broad_score = 0.0
        if broad_row:
            broad_score = 1.0 if broad_row.get("venue_priority") else min(1.0, 0.35 + 0.15 * math.log1p(int(broad_row.get("cited_by_count") or 0)))
        novelty_score = 1.0
        recency_score = recency_subscore(paper, today=today)
        components = {
            "semantic": semantic_score,
            "bluesky": bluesky_score,
            "fit": fit_score,
            "quality": quality_score,
            "broad_discovery": broad_score,
            "novelty": novelty_score,
            "recency": recency_score,
        }
        final_score = sum(float(weights.get(name, 0.0)) * value for name, value in components.items())
        lane = "broad" if broad_row and semantic_score < 0.58 and bluesky_score < 0.35 else "focused"
        ranked.append(RankedPaper(
            paper_id=paper_id,
            final_score=_clamp(final_score),
            semantic_score=semantic_score,
            bluesky_score=bluesky_score,
            fit_score=fit_score,
            quality_score=quality_score,
            broad_discovery_score=_clamp(broad_score),
            novelty_score=novelty_score,
            recency_score=recency_score,
            lane=lane,
            provenance={
                "declared_semantic_candidate": paper_id in declared_candidate_ids,
                "learned_semantic_candidate": paper_id in learned_candidate_ids,
                "declared_similarity": declared_similarity,
                "learned_similarity": learned_semantic,
                "positive_similarity": positive_similarity,
                "negative_similarity": negative_similarity,
                "learned_weight": learned_alpha,
                "effective_feedback_count": feedback_count,
                "network": network.get(paper_id),
                "broad_candidate": bool(broad_row),
            },
        ))

    ranked.sort(key=lambda item: item.final_score, reverse=True)
    target = int(ranking_cfg.get("target_papers", 16))
    broad_fraction = float(
        profile.get("discovery_balance")
        if profile.get("discovery_balance") is not None
        else ranking_cfg.get("default_broad_fraction", 0.25)
    )
    broad_target = max(0, min(target, round(target * broad_fraction)))
    focused_target = target - broad_target
    focused = [item for item in ranked if item.lane == "focused"][:focused_target]
    broad_items = [item for item in ranked if item.lane == "broad"][:broad_target]
    selected = [*focused, *broad_items]
    if len(selected) < target:
        selected_ids = {item.paper_id for item in selected}
        remaining = [item for item in ranked if item.paper_id not in selected_ids]
        selected.extend(remaining[: target - len(selected)])
    selected.sort(key=lambda item: item.final_score, reverse=True)
    return selected[:target]
