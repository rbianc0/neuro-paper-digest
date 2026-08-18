from neuro_digest.jobs.sync_user_follow_graphs import _profiles_for_sync


class API:
    def __init__(self): self.params = None
    def _request(self, method, resource, *, params=None): self.params = params; return [{"user_id": "u", "bluesky_handle": "u.test", "bluesky_sync_requested_at": "2026-08-18T00:00:00Z"}]


class Social:
    def __init__(self): self.api = API()
    def profiles_with_bluesky(self): raise AssertionError("production query should use requested-sync ordering")


def test_requested_bluesky_syncs_are_prioritized_in_query():
    social = Social(); rows = _profiles_for_sync(social)
    assert rows[0]["user_id"] == "u"
    assert social.api.params["order"].startswith("bluesky_sync_requested_at.desc.nullslast")
