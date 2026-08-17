from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from dateutil.parser import isoparse

from neuro_digest.config import load_config
from neuro_digest.embeddings import parse_vector
from neuro_digest.features import load_taxonomy, paper_feature_fit
from neuro_digest.ranking_db import RankingRepository


@dataclass
class RankedCandidate:
    paper_id: str
    title: str | None
    lane: str
    final_score: float
    semantic_score: float
    bluesky_score: float
    fit_score: float
    quality_score: float
    broad_discovery_score: float
    novelty_score: float
    recency_score: float
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _age_days(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    try:
        parsed = isoparse(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (now - parsed).total_seconds() / 86400)
    except (TypeError, ValueError):
        return None


def _half_life_score(age_days: float | None, half_life_days: float, default: float = 0.5) -> float:
    if age_days is None:
        return default
    return math.exp(-math.log(2) * age_days / half_life_days)


class RankingService:
    def __init__(self, repository: RankingRepository | None = None, *, ranking_config_path: str = "config/ranking.yaml", taxonomy_path: str = "config/feature_taxonomy.yaml"):
        self.repo = repository or RankingRepository()
        self.config = load_config(ranking_config_path)
        self.taxonomy = load_taxonomy(taxonomy_path)

    def rank_user(self, user_id: str, *, total: int = 20, now: datetime | None = None) -> list[RankedCandidate]:
        now = now or datetime.now(timezone.utc)
        profile = self.repo.get_profile(user_id)
        embeddings = self.repo.get_user_embedding(user_id)
        if not profile or not embeddings:
            return []
        declared = parse_vector(embeddings.get("declared_embedding"))
        if not declared:
            return []

        lookback_days = int(self.config.get("candidate_lookback_days", 14))
        published_after = (now.date() - timedelta(days=lookback_days)).isoformat()
        seen = self.repo.seen_paper_ids(user_id)

        semantic_rows = self.repo.match_papers(declared, published_after, limit=int(self.config.get("semantic_top_k", 400)))
        semantic_seed_ids = {row["paper_id"] for row in semantic_rows}

        positive = parse_vector(embeddings.get("learned_positive_embedding"))
        negative = parse_vector(embeddings.get("learned_negative_embedding"))
        feedback_count = int(embeddings.get("feedback_count") or 0)
        if positive and feedback_count:
            positive_rows = self.repo.match_papers(positive, published_after, limit=int(self.config.get("learned_top_k", 200)))
            semantic_seed_ids.update(row["paper_id"] for row in positive_rows)

        network_rows = self.repo.network_candidates(user_id, published_after)
        network_by_id = {row["paper_id"]: row for row in network_rows}

        venues = self.config.get("priority_venues", [])
        broad_rows = self.repo.broad_candidates(published_after, venues, limit=int(self.config.get("broad_top_k", 200)))
        broad_by_id = {row["paper_id"]: row for row in broad_rows}

        candidate_ids = (semantic_seed_ids | set(network_by_id) | set(broad_by_id)) - seen
        if not candidate_ids:
            return []
        paper_ids = sorted(candidate_ids)
        papers = self.repo.get_papers(paper_ids)
        paper_ids = [paper_id for paper_id in paper_ids if paper_id in papers]
        if not paper_ids:
            return []

        declared_scores = self.repo.score_papers(paper_ids, declared)
        positive_scores = self.repo.score_papers(paper_ids, positive)
        negative_scores = self.repo.score_papers(paper_ids, negative)
        user_features = self.repo.get_user_features(user_id)
        weights = self.config.get("weights", {})
        priority_venues = {venue.casefold() for venue in venues}
        scored: list[RankedCandidate] = []

        maturity = min(1.0, feedback_count / float(self.config.get("feedback_maturity_count", 10)))
        learned_weight = 0.35 * maturity if positive else 0.0
        for paper_id in paper_ids:
            paper = papers[paper_id]
            declared_similarity = float(declared_scores.get(paper_id, 0.0))
            positive_similarity = float(positive_scores.get(paper_id, declared_similarity))
            negative_similarity = float(negative_scores.get(paper_id, 0.0))
            semantic = (1 - learned_weight) * declared_similarity + learned_weight * positive_similarity
            semantic -= float(self.config.get("negative_similarity_penalty", 0.15)) * maturity * negative_similarity
            semantic = _clamp(semantic)

            network = network_by_id.get(paper_id)
            bluesky = self._bluesky_score(network, now)
            fit = _clamp(paper_feature_fit(paper, user_features, self.taxonomy))
            quality = self._quality_score(paper, priority_venues)
            broad_meta = broad_by_id.get(paper_id)
            if broad_meta:
                if broad_meta.get("venue_priority"):
                    broad = 1.0
                else:
                    broad = _clamp(math.log1p(max(0, int(broad_meta.get("cited_by_count") or 0))) / math.log1p(10))
            else:
                broad = 0.0
            novelty = _clamp(_half_life_score(_age_days(paper.get("created_at"), now), float(self.config.get("novelty_half_life_days", 21)), default=0.7))
            publication_value = paper.get("first_online_date") or paper.get("publication_date")
            recency = _clamp(_half_life_score(_age_days(publication_value, now), float(self.config.get("recency_half_life_days", 14)), default=0.5))
            final_score = _clamp(
                semantic * float(weights.get("semantic", 0.35))
                + bluesky * float(weights.get("bluesky", 0.30))
                + fit * float(weights.get("fit", 0.10))
                + quality * float(weights.get("quality", 0.10))
                + broad * float(weights.get("broad", 0.05))
                + novelty * float(weights.get("novelty", 0.05))
                + recency * float(weights.get("recency", 0.05))
            )
            scored.append(RankedCandidate(
                paper_id=paper_id, title=paper.get("title"), lane="UNASSIGNED", final_score=final_score,
                semantic_score=semantic, bluesky_score=bluesky, fit_score=fit, quality_score=quality,
                broad_discovery_score=broad, novelty_score=novelty, recency_score=recency,
                provenance={
                    "semantic_candidate": paper_id in semantic_seed_ids,
                    "network_candidate": paper_id in network_by_id,
                    "broad_candidate": paper_id in broad_by_id,
                    "independent_followed_actors": int((network or {}).get("independent_actors") or 0),
                    "authored_by_followed": bool((network or {}).get("authored_by_followed")),
                    "direct_count": int((network or {}).get("direct_count") or 0),
                    "repost_count": int((network or {}).get("repost_count") or 0),
                    "quote_count": int((network or {}).get("quote_count") or 0),
                    "latest_signal_at": (network or {}).get("latest_signal_at"),
                },
            ))
        return self._select_lanes(scored, profile, semantic_seed_ids, set(network_by_id), set(broad_by_id), total)

    def _bluesky_score(self, network: dict[str, Any] | None, now: datetime) -> float:
        if not network:
            return 0.0
        actors = int(network.get("independent_actors") or 0)
        direct = int(network.get("direct_count") or 0)
        repost = int(network.get("repost_count") or 0)
        quote = int(network.get("quote_count") or 0)
        actor_saturation = 1 - math.exp(-actors / 2.0) if actors else 0.0
        action_strength = _clamp((direct + 1.2 * quote + 0.5 * repost) / 3.0)
        signal_recency = _half_life_score(_age_days(network.get("latest_signal_at"), now), 4.0, default=0.0) if actors else 0.0
        discussion = _clamp(0.60 * actor_saturation + 0.25 * signal_recency + 0.15 * action_strength)
        author_component = 0.70 if network.get("authored_by_followed") else 0.0
        return _clamp(1 - (1 - author_component) * (1 - discussion))

    def _quality_score(self, paper: dict[str, Any], priority_venues: set[str]) -> float:
        journal = (paper.get("journal") or "").casefold()
        if journal in priority_venues:
            base = 0.90
        elif "biorxiv" in journal or "medrxiv" in journal:
            base = 0.45
        elif journal:
            base = 0.60
        else:
            base = 0.40
        citations = max(0, int(paper.get("cited_by_count") or 0))
        return _clamp(base + min(0.10, math.log1p(citations) / 50.0))

    def _select_lanes(self, scored: list[RankedCandidate], profile: dict[str, Any], semantic_ids: set[str], network_ids: set[str], broad_ids: set[str], total: int) -> list[RankedCandidate]:
        total = max(1, min(int(total), 50))
        broad_fraction = _clamp(float(profile.get("discovery_balance") or 0.25))
        broad_target = min(total, round(total * broad_fraction))
        focused_target = total - broad_target
        focused_pool = [item for item in scored if item.paper_id in semantic_ids or item.paper_id in network_ids]
        focused_pool.sort(key=lambda item: item.final_score, reverse=True)
        selected: list[RankedCandidate] = []
        selected_ids: set[str] = set()
        for item in focused_pool[:focused_target]:
            item.lane = "FOCUSED"; selected.append(item); selected_ids.add(item.paper_id)
        broad_pool = [item for item in scored if item.paper_id in broad_ids and item.paper_id not in selected_ids]
        broad_pool.sort(key=lambda item: 0.40 * item.quality_score + 0.25 * item.bluesky_score + 0.15 * item.recency_score + 0.10 * item.semantic_score + 0.10 * item.novelty_score, reverse=True)
        for item in broad_pool[:broad_target]:
            item.lane = "BROAD"; selected.append(item); selected_ids.add(item.paper_id)
        if len(selected) < total:
            remainder = [item for item in sorted(scored, key=lambda x: x.final_score, reverse=True) if item.paper_id not in selected_ids]
            current_broad = sum(item.lane == "BROAD" for item in selected)
            for item in remainder[: total - len(selected)]:
                if item.paper_id in broad_ids and current_broad < broad_target:
                    item.lane = "BROAD"; current_broad += 1
                else:
                    item.lane = "FOCUSED"
                selected.append(item); selected_ids.add(item.paper_id)
        selected.sort(key=lambda item: item.final_score, reverse=True)
        return selected
