from pathlib import Path
import math

from neuro_digest.feedback import learned_features, refresh_feedback_models, weighted_centroid
from neuro_digest.features import load_taxonomy, paper_feature_fit

ROOT = Path(__file__).parents[1]
TAX = str(ROOT / "config/feature_taxonomy.yaml")
CONFIG = str(ROOT / "config/feedback.yaml")


def test_positive_and_negative_centroids_are_weighted_and_normalized():
    rows = [
        {"paper_id": "a", "effective_weight": 2.0, "embedding": "[1,0]"},
        {"paper_id": "b", "effective_weight": 1.0, "embedding": "[0,1]"},
        {"paper_id": "c", "effective_weight": -3.0, "embedding": "[0,2]"},
    ]
    positive = weighted_centroid(rows, positive=True); negative = weighted_centroid(rows, positive=False)
    assert math.isclose(math.sqrt(sum(value * value for value in positive)), 1.0)
    assert positive[0] > positive[1] > 0
    assert negative == [0.0, 1.0]


def test_learned_features_can_be_negative_and_reduce_fit():
    taxonomy = load_taxonomy(TAX)
    papers = {
        "good": {"title": "MEG in humans", "abstract": "magnetoencephalography human", "metadata": {}},
        "bad": {"title": "mouse calcium imaging", "abstract": "two photon imaging in mice", "metadata": {}},
    }
    rows = [{"paper_id": "good", "effective_weight": 1.5}, {"paper_id": "bad", "effective_weight": -1.5}]
    features = learned_features(rows, papers, taxonomy, min_absolute_signal=1.0, saturation_signal=3.0)
    by_feature = {(row["feature_type"], row["feature_value"]): row["weight"] for row in features}
    assert by_feature[("METHOD", "meg")] > 0
    assert by_feature[("METHOD", "calcium_imaging")] < 0
    user_features = [{"feature_type": "METHOD", "feature_value": "meg", "weight": 1.0}, {"feature_type": "METHOD", "feature_value": "calcium_imaging", "weight": -1.0}]
    assert paper_feature_fit(papers["good"], user_features, taxonomy) > paper_feature_fit(papers["bad"], user_features, taxonomy)


class Ranking:
    def get_papers(self, ids): return {"p1": {"title": "MEG human", "abstract": "magnetoencephalography", "metadata": {}}} if "p1" in ids else {}


class Repo:
    def __init__(self): self.ranking = Ranking(); self.saved = []; self.features = []
    def user_ids(self): return ["u1", "u2"]
    def effective_feedback(self, user_id, config): return [{"paper_id": "p1", "effective_weight": 1.5, "embedding": "[1,0]"}] if user_id == "u1" else []
    def save_learned_embeddings(self, user_id, **kwargs): self.saved.append((user_id, kwargs))
    def replace_learned_features(self, user_id, features): self.features.append((user_id, features))


def test_refresh_rebuilds_and_clears_models_reproducibly():
    repo = Repo(); users, papers = refresh_feedback_models(repository=repo, config_path=CONFIG, taxonomy_path=TAX)
    assert (users, papers) == (2, 1)
    saved = dict(repo.saved); u1 = saved["u1"]; u2 = saved["u2"]
    assert u1["positive"] == [1.0, 0.0] and u1["negative"] is None and u1["feedback_count"] == 1
    assert u2["positive"] is None and u2["negative"] is None and u2["feedback_count"] == 0
