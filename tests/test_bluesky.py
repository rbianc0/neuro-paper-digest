from neuro_digest.sources.bluesky import _extract_signal_rows

def test_extracts_link_from_facet_and_repost():
    followed={"handle":"researcher.bsky.social","did":"did:plc:abc"}; item={"reason":{"$type":"app.bsky.feed.defs#reasonRepost","indexedAt":"2026-08-16T12:00:00Z"},"post":{"uri":"at://did:plc:paper/app.bsky.feed.post/xyz","author":{"handle":"author.bsky.social"},"record":{"text":"Interesting paper","createdAt":"2026-08-15T12:00:00Z","facets":[{"features":[{"$type":"app.bsky.richtext.facet#link","uri":"https://doi.org/10.1038/test.123"}]}]}}}; rows=_extract_signal_rows(followed,item); assert rows[0]["dois"]==["10.1038/test.123"]; assert rows[0]["signal"].action=="repost"

def test_detects_quote():
    followed={"handle":"researcher.bsky.social","did":"did:plc:abc"}; item={"post":{"uri":"at://did:plc:abc/app.bsky.feed.post/q1","author":{"handle":"researcher.bsky.social"},"record":{"text":"Worth reading https://doi.org/10.1016/j.neuron.2026.01.001","createdAt":"2026-08-16T12:00:00Z","embed":{"$type":"app.bsky.embed.record","record":{"uri":"at://did:plc:x/app.bsky.feed.post/x"}}}}}; rows=_extract_signal_rows(followed,item); assert rows[0]["signal"].action=="quote"
