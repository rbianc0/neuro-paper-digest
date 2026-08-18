from neuro_digest.sources.bluesky_shared import normalize_feed_item


def _post_item(*, text: str, reason=None, embed=None, author_did="did:plc:author"):
    return {
        "reason": reason,
        "post": {
            "uri": "at://did:plc:author/app.bsky.feed.post/abc",
            "cid": "cid1",
            "author": {"did": author_did, "handle": "author.example"},
            "record": {"text": text, "createdAt": "2026-08-18T08:00:00Z", "embed": embed},
            "indexedAt": "2026-08-18T08:00:01Z",
            "embed": {},
        },
    }


def test_direct_post_extracts_doi():
    event = normalize_feed_item(
        "did:plc:followed",
        _post_item(text="New paper https://doi.org/10.1234/ABC.DEF"),
    )
    assert event is not None
    assert event["signal_type"] == "POST"
    assert event["actor_did"] == "did:plc:followed"
    assert event["post"]["author"]["did"] == "did:plc:author"
    assert any(link["doi"] == "10.1234/abc.def" for link in event["links"])


def test_repost_keeps_network_actor_distinct_from_original_author():
    event = normalize_feed_item(
        "did:plc:reposter",
        _post_item(
            text="Paper https://doi.org/10.5555/reposted",
            reason={
                "$type": "app.bsky.feed.defs#reasonRepost",
                "by": {"did": "did:plc:reposter"},
                "indexedAt": "2026-08-18T08:02:00Z",
                "uri": "at://did:plc:reposter/app.bsky.feed.repost/r1",
            },
            author_did="did:plc:original",
        ),
    )
    assert event is not None
    assert event["signal_type"] == "REPOST"
    assert event["actor_did"] == "did:plc:reposter"
    assert event["post"]["author"]["did"] == "did:plc:original"
    assert event["event_uri"].endswith("/r1")


def test_non_scholarly_post_is_ignored():
    assert normalize_feed_item("did:plc:followed", _post_item(text="ordinary lab update")) is None


def test_quote_is_classified_separately():
    event = normalize_feed_item(
        "did:plc:followed",
        _post_item(
            text="Worth reading https://doi.org/10.1000/quote",
            embed={"$type": "app.bsky.embed.record", "record": {"uri": "at://did:plc:x/app.bsky.feed.post/q"}},
        ),
    )
    assert event is not None
    assert event["signal_type"] == "QUOTE"
