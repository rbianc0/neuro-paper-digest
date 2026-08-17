from datetime import datetime, timezone
from pathlib import Path

from neuro_digest.embeddings import OpenAIEmbeddingClient, paper_embedding_text, parse_vector, text_hash, vector_literal
from neuro_digest.features import extract_profile_features, load_taxonomy, paper_feature_fit
from neuro_digest.jobs.embed_new_papers import embed_new_papers
from neuro_digest.jobs.refresh_user_models import refresh_user_models
from neuro_digest.ranking import RankingService

ROOT = Path(__file__).parents[1]
TAX = str(ROOT / "config/feature_taxonomy.yaml")
RANK = str(ROOT / "config/ranking.yaml")


def test_embedding_helpers_round_trip_and_hash_is_stable():
    text = paper_embedding_text({"title": "  Fear  study ", "abstract": "MEG\nanalysis", "journal": "Neuron"})
    assert text == "Title: Fear study Abstract: MEG analysis Venue: Neuron"
    vector = [0.1, 0.2]
    assert parse_vector(vector_literal(vector)) == vector
    assert text_hash(" a   b ") == text_hash("a b")


def test_embedding_client_validates_and_orders_response():
    class Response:
        status_code = 200
        content = b"1"
        text = ""
        def json(self):
            vector = [0.0] * 1536
            return {"data": [{"index": 1, "embedding": vector}, {"index": 0, "embedding": vector}]}
    class Session:
        def post(self, *args, **kwargs): return Response()
    client = OpenAIEmbeddingClient(api_key="x"); client.s = Session()
    out = client.embed(["a", "b"])
    assert len(out) == 2 and len(out[0]) == 1536


def test_profile_feature_extraction_and_paper_fit():
    taxonomy = load_taxonomy(TAX)
    features = extract_profile_features("I use MEG in mice and intracranial EEG in humans.", taxonomy)
    values = {(row["feature_type"], row["feature_value"]) for row in features}
    assert ("METHOD", "meg") in values and ("METHOD", "intracranial_eeg") in values
    assert ("SPECIES", "mouse") in values and ("SPECIES", "human") in values
    fit = paper_feature_fit({"title": "MEG in mice", "abstract": "magnetoencephalography mouse neural dynamics", "metadata": {}}, features, taxonomy)
    assert 0 < fit <= 1


class EmbedRepo:
    def __init__(self): self.calls = 0; self.saved = []
    def papers_missing_embeddings(self, limit=64):
        self.calls += 1
        return [{"id": "p1", "title": "Paper", "abstract": "Abstract", "journal": "Neuron"}] if self.calls == 1 else []
    def save_paper_embeddings(self, rows): self.saved.extend(rows)


class EmbedClient:
    model = "test-embedding"
    def embed(self, texts): return [[0.01] * 1536 for _ in texts]


def test_embed_job_is_incremental_and_saves_hash_model():
    repo = EmbedRepo(); count = embed_new_papers(repository=repo, client=EmbedClient())
    assert count == 1 and repo.saved[0]["embedding_model"] == "test-embedding"
    assert len(parse_vector(repo.saved[0]["embedding"])) == 1536
    assert len(repo.saved[0]["embedding_input_hash"]) == 64


class UserRepo:
    def __init__(self): self.saved = []; self.features = []
    def profiles_with_research_descriptions(self): return [{"user_id": "u1", "research_description": "MEG in mice"}]
    def get_user_embedding(self, user_id): return None
    def save_declared_user_embedding(self, user_id, **kwargs): self.saved.append((user_id, kwargs))
    def replace_inferred_features(self, user_id, features): self.features.append((user_id, features))


class UserClient:
    model = "test-embedding"
    def embed(self, texts): return [[0.01] * 1536 for _ in texts]


def test_user_model_refresh_updates_embedding_and_features():
    repo = UserRepo(); embeddings, features = refresh_user_models(repository=repo, client=UserClient(), taxonomy_path=TAX)
    assert (embeddings, features) == (1, 1)
    assert repo.saved[0][0] == "u1"
    assert any(row["feature_value"] == "meg" for row in repo.features[0][1])


class RankRepo:
    def __init__(self):
        self.papers = {
            "p1": {"id": "p1", "title": "Strong network", "abstract": "MEG human", "journal": "Neuron", "publication_date": "2026-08-17", "first_online_date": "2026-08-17", "cited_by_count": 0, "created_at": "2026-08-17T00:00:00Z", "metadata": {}},
            "p2": {"id": "p2", "title": "Semantic only", "abstract": "MEG human", "journal": "Other", "publication_date": "2026-08-17", "first_online_date": "2026-08-17", "cited_by_count": 0, "created_at": "2026-08-17T00:00:00Z", "metadata": {}},
            "p3": {"id": "p3", "title": "Broad important", "abstract": "memory behavior", "journal": "Nature", "publication_date": "2026-08-17", "first_online_date": "2026-08-17", "cited_by_count": 4, "created_at": "2026-08-17T00:00:00Z", "metadata": {}},
            "seen": {"id": "seen", "title": "Seen", "abstract": "MEG", "journal": "Neuron", "publication_date": "2026-08-17", "first_online_date": "2026-08-17", "cited_by_count": 0, "created_at": "2026-08-17T00:00:00Z", "metadata": {}},
        }
    def get_profile(self, user_id): return {"user_id": user_id, "discovery_balance": 0.25}
    def get_user_embedding(self, user_id): return {"declared_embedding": "[1,0]", "learned_positive_embedding": None, "learned_negative_embedding": None, "feedback_count": 0}
    def seen_paper_ids(self, user_id): return {"seen"}
    def match_papers(self, embedding, published_after, limit=400): return [{"paper_id": "p1"}, {"paper_id": "p2"}, {"paper_id": "seen"}]
    def network_candidates(self, user_id, published_after): return [{"paper_id": "p1", "independent_actors": 3, "direct_count": 2, "repost_count": 1, "quote_count": 1, "latest_signal_at": "2026-08-18T00:00:00Z", "authored_by_followed": False}]
    def broad_candidates(self, published_after, venues, limit=200): return [{"paper_id": "p3", "venue_priority": True, "cited_by_count": 4}]
    def get_papers(self, ids): return {paper_id: self.papers[paper_id] for paper_id in ids}
    def score_papers(self, ids, embedding): return {paper_id: 0.75 if paper_id in ("p1", "p2") else 0.30 for paper_id in ids} if embedding else {}
    def get_user_features(self, user_id): return [{"feature_type": "METHOD", "feature_value": "meg", "weight": 1.0, "source": "INFERRED"}]


def test_ranking_bluesky_boost_seen_suppression_and_broad_quota():
    service = RankingService(RankRepo(), ranking_config_path=RANK, taxonomy_path=TAX)
    rows = service.rank_user("u1", total=3, now=datetime(2026, 8, 18, tzinfo=timezone.utc))
    ids = [row.paper_id for row in rows]
    assert "seen" not in ids and set(ids) == {"p1", "p2", "p3"}
    p1 = next(row for row in rows if row.paper_id == "p1"); p2 = next(row for row in rows if row.paper_id == "p2"); p3 = next(row for row in rows if row.paper_id == "p3")
    assert p1.bluesky_score > p2.bluesky_score and p1.final_score > p2.final_score
    assert p3.lane == "BROAD" and p3.broad_discovery_score == 1.0
    for row in rows:
        assert all(0 <= getattr(row, name) <= 1 for name in ("final_score", "semantic_score", "bluesky_score", "fit_score", "quality_score", "broad_discovery_score", "novelty_score", "recency_score"))
