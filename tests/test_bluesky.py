from datetime import datetime, timezone

import neuro_digest.sources.bluesky as module
from neuro_digest.sources.bluesky import BlueskyClient, extract_scholarly_links, parse_feed_item


def test_direct_post_extracts_doi():
    item = {"post": {"uri": "at://did:plc:a/app.bsky.feed.post/1", "cid": "c1", "author": {"did": "did:plc:a", "handle": "a.bsky.social"}, "indexedAt": "2026-08-17T10:00:01Z", "record": {"text": "Read https://doi.org/10.1038/ABC.123", "createdAt": "2026-08-17T10:00:00Z"}}}
    event = parse_feed_item("did:plc:a", item)
    assert event.signal_type == "POST"; assert event.post_type == "POST"; assert [(link.link_key, link.doi) for link in event.links] == [("doi:10.1038/abc.123", "10.1038/abc.123")]


def test_repost_uses_followed_actor_and_repost_time():
    item = {"reason": {"$type": "app.bsky.feed.defs#reasonRepost", "indexedAt": "2026-08-17T12:00:00Z"}, "post": {"uri": "at://did:plc:b/app.bsky.feed.post/old", "author": {"did": "did:plc:b", "handle": "b.bsky.social"}, "record": {"text": "https://pubmed.ncbi.nlm.nih.gov/123456/", "createdAt": "2026-01-01T00:00:00Z"}}}
    event = parse_feed_item("did:plc:a", item)
    assert event.signal_type == "REPOST"; assert event.post_type == "POST"; assert event.signal_actor_did == "did:plc:a"; assert event.post_author.did == "did:plc:b"; assert event.signal_timestamp == "2026-08-17T12:00:00Z"; assert event.links[0].pmid == "123456"


def test_quote_post_keeps_intrinsic_quote_and_extracts_quoted_view_link():
    item = {"post": {"uri": "at://did:plc:a/app.bsky.feed.post/q", "author": {"did": "did:plc:a"}, "record": {"text": "worth reading", "createdAt": "2026-08-17T13:00:00Z", "embed": {"$type": "app.bsky.embed.record", "record": {"uri": "at://did:plc:b/app.bsky.feed.post/x", "cid": "x"}}}, "embed": {"record": {"value": {"text": "paper https://doi.org/10.1101/2026.01.01.1"}}}}}
    event = parse_feed_item("did:plc:a", item)
    assert event.signal_type == "QUOTE"; assert event.post_type == "QUOTE"; assert event.referenced_uri == "at://did:plc:b/app.bsky.feed.post/x"; assert event.links[0].doi == "10.1101/2026.01.01.1"


def test_same_doi_in_text_and_url_becomes_one_link():
    links = extract_scholarly_links({"text": "doi:10.1038/abc.123 https://doi.org/10.1038/abc.123"})
    assert len(links) == 1; assert links[0].link_key == "doi:10.1038/abc.123"


def test_get_follows_paginates(monkeypatch):
    responses = [{"follows": [{"did": "did:plc:1", "handle": "one.test"}], "cursor": "next"}, {"follows": [{"did": "did:plc:2", "handle": "two.test"}]}]; calls = []
    def fake_get_json(session, url, *, params=None, timeout=30): calls.append(params); return responses.pop(0)
    monkeypatch.setattr(module, "get_json", fake_get_json); follows = BlueskyClient().get_follows("did:plc:user")
    assert [x.did for x in follows] == ["did:plc:1", "did:plc:2"]; assert calls[0]["limit"] == 100; assert calls[1]["cursor"] == "next"


def test_author_feed_uses_repost_time_and_only_returns_scholarly_events(monkeypatch):
    feed = [{"reason": {"$type": "app.bsky.feed.defs#reasonRepost", "indexedAt": "2026-08-17T12:00:00Z"}, "post": {"uri": "at://did:plc:b/app.bsky.feed.post/old", "author": {"did": "did:plc:b"}, "record": {"text": "https://doi.org/10.1000/old", "createdAt": "2025-01-01T00:00:00Z"}}}, {"post": {"uri": "at://did:plc:a/app.bsky.feed.post/chat", "author": {"did": "did:plc:a"}, "record": {"text": "no scholarly link here", "createdAt": "2026-08-17T11:00:00Z"}}}, {"post": {"uri": "at://did:plc:a/app.bsky.feed.post/stop", "author": {"did": "did:plc:a"}, "record": {"text": "https://doi.org/10.1000/too-old", "createdAt": "2026-08-01T00:00:00Z"}}}]
    monkeypatch.setattr(module, "get_json", lambda session, url, *, params=None, timeout=30: {"feed": feed})
    events = BlueskyClient().get_author_feed("did:plc:a", datetime(2026, 8, 10, tzinfo=timezone.utc))
    assert len(events) == 1; assert events[0].signal_type == "REPOST"
