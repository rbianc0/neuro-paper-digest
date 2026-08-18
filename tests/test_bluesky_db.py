from neuro_digest.bluesky_db import BlueskyRepository


class FakeAPI:
    def __init__(self):
        self.upserts = []
        self.requests = []

    def upsert(self, table, row, *, on_conflict):
        self.upserts.append((table, row, on_conflict))
        return row

    def _request(self, method, resource, **kwargs):
        self.requests.append((method, resource, kwargs))
        return []


def test_repost_persists_original_post_as_post_and_event_as_repost():
    api = FakeAPI(); repo = BlueskyRepository(api)
    repo.persist_feed_event({
        "event_key": "repost-event",
        "actor_did": "did:plc:reposter",
        "signal_type": "REPOST",
        "signal_timestamp": "2026-08-18T08:00:00Z",
        "event_uri": "at://did:plc:reposter/app.bsky.feed.repost/r1",
        "raw_event": {},
        "links": [{"link_key": "doi:10.1/x", "doi": "10.1/x", "pmid": None, "url": "https://doi.org/10.1/x"}],
        "post": {
            "uri": "at://did:plc:original/app.bsky.feed.post/p1",
            "cid": "c1",
            "author": {"did": "did:plc:original", "handle": "original.test"},
            "text": "paper",
            "created_at": "2026-08-18T07:00:00Z",
            "indexed_at": "2026-08-18T07:00:01Z",
            "referenced_uri": None,
            "urls": ["https://doi.org/10.1/x"],
            "raw_record": {},
        },
    })
    post = next(row for table, row, _ in api.upserts if table == "bluesky_posts")
    event = next(row for table, row, _ in api.upserts if table == "bluesky_post_events")
    assert post["post_type"] == "POST"
    assert post["author_did"] == "did:plc:original"
    assert event["signal_type"] == "REPOST"
    assert event["actor_did"] == "did:plc:reposter"
