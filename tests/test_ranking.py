from datetime import date

from neuro_digest.ranking import (
    bluesky_subscore,
    fit_subscore,
    learned_similarity,
    personal_semantic_similarity,
    rank_for_user,
)


def test_followed_author_creates_strong_bluesky_floor():
    score = bluesky_subscore({
        "independent_actors": 0,
        "direct_count": 0,
        "repost_count": 0,
        "quote_count": 0,
        "latest_signal_at": None,
        "authored_by_followed": True,
    })
    assert score >= 0.72


def test_more_independent_network_sources_increase_bluesky_score():
    base = {
        "direct_count": 1,
        "repost_count": 0,
        "quote_count": 0,
        "latest_signal_at": None,
        "authored_by_followed": False,
    }
    assert bluesky_subscore({**base, "independent_actors": 4}) > bluesky_subscore({**base, "independent_actors": 1})


def test_fit_rewards_method_and_species_overlap():
    config = {
        "methods": {"meg": ["meg", "magnetoencephalography"]},
        "species": {"human": ["human", "participants"]},
    }
    matching = fit_subscore(
        "Human MEG fear generalization",
        {"title": "MEG markers of fear generalization", "abstract": "We studied human participants."},
        feature_config=config,
    )
    mismatch = fit_subscore(
        "Human MEG fear generalization",
        {"title": "Calcium imaging of retinal development", "abstract": "Mouse retinal cells."},
        feature_config=config,
    )
    assert matching > mismatch


def test_learned_similarity_rewards_positive_and_penalizes_negative_proximity():
    preferred = learned_similarity(0.90, 0.20)
    disliked = learned_similarity(0.30, 0.85)
    assert preferred is not None and disliked is not None
    assert preferred > disliked


def test_declared_profile_remains_anchor_at_partial_learning_weight():
    score = personal_semantic_similarity(0.90, 0.20, None, 0.10)
    assert 0.80 < score < 0.90


class FakeRepository:
    def profile(self, user_id):
        return {"user_id": user_id, "research_description": "human MEG fear conditioning", "discovery_balance": 0.25}

    def embeddings(self, user_id):
        return {
            "user_id": user_id,
            "declared_embedding": "[0.1,0.2]",
            "learned_positive_embedding": None,
            "learned_negative_embedding": None,
            "feedback_count": 0,
        }

    def semantic_candidates(self, vector, published_after, limit):
        return [
            {"paper_id": "focus1", "similarity": 0.95},
            {"paper_id": "focus2", "similarity": 0.85},
            {"paper_id": "focus3", "similarity": 0.82},
            {"paper_id": "focus4", "similarity": 0.80},
        ]

    def network_candidates(self, user_id, published_after):
        return [{
            "paper_id": "focus2", "independent_actors": 3, "direct_count": 2,
            "repost_count": 1, "quote_count": 1, "latest_signal_at": None,
            "authored_by_followed": False,
        }]

    def broad_candidates(self, published_after, priority_venues, limit):
        return [
            {"paper_id": "broad1", "venue_priority": True, "cited_by_count": 8},
            {"paper_id": "broad2", "venue_priority": True, "cited_by_count": 6},
        ]

    def seen_papers(self, user_id):
        return set()

    def semantic_scores(self, paper_ids, vector):
        scores = {"broad1": 0.30, "broad2": 0.28}
        return [{"paper_id": paper_id, "similarity": scores[paper_id]} for paper_id in paper_ids]

    def papers(self, paper_ids):
        return {
            paper_id: {
                "id": paper_id,
                "title": "MEG fear paper" if paper_id.startswith("focus") else "Important social cognition discovery",
                "abstract": "human participants" if paper_id.startswith("focus") else "large behavioral experiment",
                "journal": "Nature" if paper_id.startswith("broad") else "NeuroImage",
                "publication_date": "2026-08-15",
                "first_online_date": "2026-08-15",
                "cited_by_count": 0,
                "canonical_doi": None,
                "metadata": {},
            }
            for paper_id in paper_ids
        }


def test_controlled_discovery_reserves_broad_lane(tmp_path):
    config = tmp_path / "ranking.yaml"
    config.write_text("""
ranking:
  lookback_days: 21
  semantic_candidates: 20
  broad_candidates: 20
  target_papers: 4
  default_broad_fraction: 0.25
  priority_venues: [nature]
  weights:
    semantic: 0.35
    bluesky: 0.30
    fit: 0.10
    quality: 0.10
    broad_discovery: 0.05
    novelty: 0.05
    recency: 0.05
features:
  methods:
    meg: [meg]
  species:
    human: [human, participants]
""")
    ranked = rank_for_user("u1", config_path=str(config), repository=FakeRepository(), today=date(2026, 8, 18))
    assert len(ranked) == 4
    assert sum(item.lane == "broad" for item in ranked) == 1
    assert any(item.paper_id == "focus2" and item.bluesky_score > 0 for item in ranked)
