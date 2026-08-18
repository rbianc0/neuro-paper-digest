from types import SimpleNamespace

from neuro_digest.embeddings import embedding_input_hash, normalized_embedding_text
from neuro_digest.jobs.embed_user_profiles import embed_user_profiles


class FakeAPI:
    def __init__(self):
        self.profiles = [
            {"user_id": "u1", "research_description": "MEG fear conditioning and arousal"},
            {"user_id": "u2", "research_description": "EEG normative modelling"},
        ]
        self.user_embeddings = [
            {
                "user_id": "u2",
                "declared_input_hash": embedding_input_hash(normalized_embedding_text("EEG normative modelling")),
                "embedding_model": "text-embedding-3-small",
            }
        ]
        self.upserts = []

    def _request(self, method, resource, *, params=None, json=None, prefer=None):
        assert method == "GET"
        if resource == "profiles":
            return self.profiles
        if resource == "user_embeddings":
            return self.user_embeddings
        raise AssertionError(resource)

    def upsert(self, table, row, *, on_conflict):
        assert table == "user_embeddings"
        assert on_conflict == "user_id"
        self.upserts.append(row)
        return row


class FakeEmbedder:
    config = SimpleNamespace(model="text-embedding-3-small", dimensions=3)

    def __init__(self):
        self.inputs = []

    def embed(self, texts):
        self.inputs.append(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]


def test_embed_user_profiles_embeds_missing_and_skips_unchanged():
    api = FakeAPI()
    embedder = FakeEmbedder()

    stats = embed_user_profiles(api=api, embedder=embedder, batch_size=10)

    assert stats == {"profiles": 2, "embedded": 1, "skipped": 1}
    assert embedder.inputs == [["MEG fear conditioning and arousal"]]
    assert len(api.upserts) == 1
    row = api.upserts[0]
    assert row["user_id"] == "u1"
    assert row["declared_embedding"] == "[0.1,0.2,0.3]"
    assert row["embedding_model"] == "text-embedding-3-small"
    assert row["declared_input_hash"] == embedding_input_hash("MEG fear conditioning and arousal")
