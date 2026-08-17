from dataclasses import dataclass
from pathlib import Path

from neuro_digest.digest import DigestService
from neuro_digest.interactions import build_interaction_link, token_hash
from neuro_digest.newsletter import OpenAISummaryClient, ResendClient, render_newsletter

ROOT = Path(__file__).parents[1]
CONFIG = str(ROOT / "config/digest.yaml")


def test_interaction_links_store_only_hash_and_use_action_specific_paths():
    click = build_interaction_link(base_url="https://neurofeed.test", user_id="u", paper_id="p", digest_id="d", action_type="CLICK", expiry_days=10, redirect_url="https://doi.org/x", single_use=False)
    save = build_interaction_link(base_url="https://neurofeed.test", user_id="u", paper_id="p", digest_id="d", action_type="SAVE", expiry_days=10)
    assert "/r/" in click.url and "/a/" in save.url
    assert click.raw_token not in str(click.db_row)
    assert click.db_row["token_hash"] == token_hash(click.raw_token)
    assert click.db_row["single_use"] is False and save.db_row["single_use"] is True


def test_summary_client_uses_structured_response_output():
    class Response:
        status_code = 200
        text = ""
        def json(self): return {"output": [{"type": "message", "content": [{"type": "output_text", "text": '{"items":[{"paper_id":"p1","summary":"A factual summary."}]}'}]}]}
    class Session:
        def __init__(self): self.payload = None
        def post(self, url, **kwargs): self.payload = kwargs["json"]; return Response()
    client = OpenAISummaryClient(api_key="x", model="gpt-test"); client.s = Session()
    result = client.summarize([{"paper_id": "p1", "title": "T", "abstract": "A", "authors": [], "journal": "J"}])
    assert result == {"p1": "A factual summary."}
    assert client.s.payload["store"] is False
    assert client.s.payload["text"]["format"]["type"] == "json_schema"


@dataclass
class Ranked:
    paper_id: str
    title: str
    lane: str
    final_score: float
    semantic_score: float
    bluesky_score: float
    fit_score: float
    quality_score: float
    broad_discovery_score: float
    novelty_score: float
    recency_score: float
    provenance: dict


class Ranker:
    def rank_user(self, user_id, total=16):
        return [
            Ranked("p1", "One", "FOCUSED", .9, .9, .4, .8, .8, 0, .8, .9, {"network_candidate": True, "independent_followed_actors": 2, "authored_by_followed": False}),
            Ranked("p2", "Two", "BROAD", .7, .4, 0, .5, .9, 1, .8, .9, {"network_candidate": False, "independent_followed_actors": 0, "authored_by_followed": False}),
        ]


class Summary:
    model = "gpt-test"
    def summarize(self, papers): return {paper["paper_id"]: f"Summary {paper['paper_id']}" for paper in papers}


class Repo:
    def __init__(self): self.digest = None; self.items = []; self.tokens = []; self.updated = []
    def existing_digest(self, *args): return self.digest
    def paper_data(self, ids): return {paper_id: {"paper_id": paper_id, "title": paper_id, "abstract": "abstract", "journal": "Neuron", "publication_date": "2026-08-18", "first_online_date": "2026-08-18", "canonical_url": f"https://doi.org/{paper_id}", "authors": [{"name": "Ada"}]} for paper_id in ids}
    def insert_digest(self, row): self.digest = dict(row); return row
    def insert_items(self, rows): self.items.extend(rows)
    def insert_tokens(self, rows): self.tokens.extend(rows)
    def update_digest(self, digest_id, changes): self.digest.update(changes); self.updated.append(changes); return self.digest


def test_digest_generation_freezes_unique_items_and_is_idempotent():
    repo = Repo(); service = DigestService(repository=repo, ranking=Ranker(), summarizer=Summary(), config_path=CONFIG, base_url="https://neurofeed.test")
    digest_id, created = service.generate_user({"user_id": "u1"}, period_start="2026-08-11", period_end="2026-08-18")
    assert created and digest_id
    assert len(repo.items) == 2 and len({row["paper_id"] for row in repo.items}) == 2
    assert repo.items[0]["section"] == "Must Read"
    assert repo.digest["status"] == "GENERATED" and repo.digest["rendered_html"] and repo.digest["content_hash"]
    assert len(repo.tokens) == 8
    second, created2 = service.generate_user({"user_id": "u1"}, period_start="2026-08-11", period_end="2026-08-18")
    assert second == digest_id and created2 is False and len(repo.items) == 2


def test_resend_uses_digest_idempotency_key():
    class Response:
        status_code = 200
        text = ""
        def json(self): return {"id": "email-1"}
    class Session:
        def __init__(self): self.headers = None
        def post(self, url, **kwargs): self.headers = kwargs["headers"]; return Response()
    client = ResendClient(api_key="re_x", from_email="Neurofeed <n@example.org>"); client.s = Session()
    assert client.send(digest_id="d1", to="u@example.org", subject="s", html_body="<p>x</p>", text_body="x") == "email-1"
    assert client.s.headers["Idempotency-Key"] == "neurofeed-digest-d1"


def test_renderer_escapes_untrusted_metadata():
    html_body, _ = render_newsletter(subject="S", items=[{"section": "Must Read", "title": "<script>", "authors": [], "journal": "J", "summary": "<b>x</b>", "why_recommended": "why", "read_url": None, "save_url": "https://x", "more_url": "https://x", "less_url": "https://x"}])
    assert "<script>" not in html_body and "&lt;script&gt;" in html_body and "<b>x</b>" not in html_body
