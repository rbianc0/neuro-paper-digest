from neuro_digest.social_db import SocialRepository
from neuro_digest.sources.bluesky import BlueskyAccountRef, FeedEvent, ScholarlyLink


class FakeAPI:
    def __init__(self): self.requests = []; self.rpc_calls = []
    def _request(self, method, resource, *, params=None, json=None, prefer=None): self.requests.append((method, resource, params, json, prefer)); return [] if method == "GET" else None
    def upsert(self, table, row, *, on_conflict): self.requests.append(("UPSERT", table, on_conflict, row, None)); return row
    def select_one(self, table, column, value): return None
    def select_one_where(self, table, filters): return None
    def rpc(self, function, args): self.rpc_calls.append((function, args)); return 2


def _event(uri, actor, doi):
    return FeedEvent(post_uri=uri, cid="cid", post_author=BlueskyAccountRef(did="did:plc:author", handle="author.test"), text=f"https://doi.org/{doi}", created_at="2026-08-17T12:00:00Z", indexed_at="2026-08-17T12:00:01Z", post_type="POST", referenced_uri=None, signal_actor_did=actor, signal_type="POST", signal_timestamp="2026-08-17T12:00:00Z", event_uri=None, links=[ScholarlyLink(f"doi:{doi}", doi=doi)], raw_record={}, raw_event={})


def test_persist_events_batches_posts_events_and_links():
    api = FakeAPI(); repo = SocialRepository(api); repo.persist_events([_event("at://did:plc:author/app.bsky.feed.post/1", "did:plc:f1", "10.1000/a"), _event("at://did:plc:author/app.bsky.feed.post/2", "did:plc:f1", "10.1000/b")])
    resources = [call[1] for call in api.requests]
    assert resources.count("bluesky_accounts") == 1; assert resources.count("bluesky_posts") == 1; assert resources.count("bluesky_post_events") == 1; assert resources.count("bluesky_scholarly_links") == 1
    link_call = next(call for call in api.requests if call[1] == "bluesky_scholarly_links"); assert "resolution=ignore-duplicates" in link_call[4]


def test_replace_follow_graph_calls_atomic_rpc_after_accounts():
    api = FakeAPI(); repo = SocialRepository(api); follows = [BlueskyAccountRef(did="did:plc:1", handle="one.test"), BlueskyAccountRef(did="did:plc:2", handle="two.test")]
    count = repo.replace_follow_graph("user-id", bluesky_did="did:plc:user", bluesky_handle="user.test", follows=follows)
    assert count == 2; assert api.rpc_calls[0][0] == "replace_user_bluesky_follows"; assert api.rpc_calls[0][1]["p_followed_dids"] == ["did:plc:1", "did:plc:2"]
