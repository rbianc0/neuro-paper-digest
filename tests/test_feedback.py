import pytest

from neuro_digest.feedback import learned_weight, parse_vector, weighted_centroid


def test_parse_pgvector_literal():
    assert parse_vector("[0.1,0.2,-0.3]") == [0.1, 0.2, -0.3]


def test_weighted_centroids_keep_positive_and_negative_preferences_separate():
    rows = [
        {"effective_weight": 2.0, "embedding": "[1,0]"},
        {"effective_weight": 1.0, "embedding": "[0,1]"},
        {"effective_weight": -3.0, "embedding": "[-1,0]"},
    ]
    positive = weighted_centroid(rows, positive=True)
    negative = weighted_centroid(rows, positive=False)
    assert positive == pytest.approx([2 / 3, 1 / 3])
    assert negative == pytest.approx([-1, 0])


def test_learned_weight_is_zero_until_enough_feedback_then_ramps_to_ceiling():
    assert learned_weight(0, maximum=0.35, start_after=2, full_after=10) == 0
    assert learned_weight(1, maximum=0.35, start_after=2, full_after=10) == 0
    early = learned_weight(2, maximum=0.35, start_after=2, full_after=10)
    middle = learned_weight(6, maximum=0.35, start_after=2, full_after=10)
    full = learned_weight(10, maximum=0.35, start_after=2, full_after=10)
    assert 0 < early < middle < full
    assert full == pytest.approx(0.35)
