from neuro_digest.jobs.sync_user_follow_graphs import _profiles_for_sync


class FakeAPI:
    def __init__(self, rows=None, error=None):
        self.rows = rows
        self.error = error
        self.params = None

    def _request(self, method, resource, *, params=None, **kwargs):
        assert method == "GET"
        assert resource == "profiles"
        self.params = params
        if self.error:
            raise self.error
        return self.rows


class FakeRepository:
    def __init__(self, api, fallback=None):
        self.api = api
        self.fallback = fallback or []
        self.fallback_called = False

    def list_profiles_for_sync(self, *, limit):
        self.fallback_called = True
        return self.fallback[:limit]


def test_phase7_prioritizes_explicit_refresh_requests():
    rows = [{"user_id": "u1", "bluesky_handle": "one.example", "bluesky_sync_requested_at": "2026-08-18T12:00:00Z"}]
    api = FakeAPI(rows=rows)
    repo = FakeRepository(api)

    assert _profiles_for_sync(repo, limit=50) == rows
    assert repo.fallback_called is False
    assert "bluesky_sync_requested_at.desc.nullslast" in api.params["order"]
    assert "last_bluesky_sync_at.asc.nullsfirst" in api.params["order"]
    assert api.params["limit"] == 50


def test_phase7_refresh_priority_falls_back_without_phase7_schema():
    fallback = [{"user_id": "u2", "bluesky_handle": "two.example"}]
    repo = FakeRepository(FakeAPI(error=RuntimeError("column missing")), fallback=fallback)

    assert _profiles_for_sync(repo, limit=10) == fallback
    assert repo.fallback_called is True
