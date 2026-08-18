from neuro_digest.embeddings import EmbeddingConfig, OpenAIEmbedder, embedding_input_hash, normalized_embedding_text, vector_literal


class FakeResponse:
    content = b"x"
    def raise_for_status(self):
        return None
    def json(self):
        return {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}


class FakeSession:
    def __init__(self):
        self.call = None
    def post(self, url, **kwargs):
        self.call = (url, kwargs)
        return FakeResponse()


def test_embedding_text_and_hash_are_deterministic():
    text = normalized_embedding_text("  A   title ", None, " Journal ")
    assert text == "A title\n\nJournal"
    assert embedding_input_hash(text) == embedding_input_hash(text)
    assert vector_literal([0.1, 0.2]) == "[0.1,0.2]"


def test_embedder_requests_configured_dimensions_and_preserves_order():
    session = FakeSession()
    embedder = OpenAIEmbedder("test-key", config=EmbeddingConfig(model="test-embedding", dimensions=3), session=session)
    assert embedder.embed(["paper text"]) == [[0.1, 0.2, 0.3]]
    url, kwargs = session.call
    assert url.endswith("/v1/embeddings")
    assert kwargs["json"]["model"] == "test-embedding"
    assert kwargs["json"]["dimensions"] == 3
