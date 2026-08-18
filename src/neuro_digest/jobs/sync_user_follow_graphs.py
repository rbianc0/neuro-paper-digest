from __future__ import annotations

import argparse
import logging

from neuro_digest.bluesky_db import BlueskyRepository
from neuro_digest.sources.bluesky_shared import get_follows, get_profile

LOG = logging.getLogger(__name__)


def _profiles_for_sync(repo: BlueskyRepository, *, limit: int) -> list[dict]:
    """Prefer explicit web refresh requests without making Phase 3 depend on Phase 7."""
    try:
        rows = repo.api._request(
            "GET",
            "profiles",
            params={
                "select": "user_id,bluesky_handle,bluesky_did,last_bluesky_sync_at,bluesky_sync_requested_at",
                "bluesky_handle": "not.is.null",
                "order": "bluesky_sync_requested_at.desc.nullslast,last_bluesky_sync_at.asc.nullsfirst,user_id.asc",
                "limit": max(1, min(limit, 5000)),
            },
        )
        if rows is not None:
            return rows
    except Exception as exc:
        # The fallback preserves compatibility if this Phase 7 column is not
        # present in an older/local database.
        LOG.debug("Requested-refresh prioritization unavailable: %s", exc)
    return repo.list_profiles_for_sync(limit=limit)


def sync_user_follow_graphs(*, limit: int = 500, repository: BlueskyRepository | None = None) -> tuple[int, int]:
    repo = repository or BlueskyRepository(); synced = 0; failed = 0
    for profile in _profiles_for_sync(repo, limit=limit):
        user_id = profile["user_id"]; handle = profile.get("bluesky_handle")
        if not handle:
            continue
        try:
            owner = get_profile(handle)
            repo.upsert_account(owner)
            follows = get_follows(owner["did"])
            for followed in follows:
                repo.upsert_account(followed)
            repo.replace_user_follows(
                user_id=user_id,
                user_did=owner["did"],
                user_handle=owner.get("handle") or handle,
                followed_dids=[f["did"] for f in follows if f.get("did")],
            )
            synced += 1
            LOG.info("Synced %s: %d follows", handle, len(follows))
        except Exception as exc:
            failed += 1
            repo.record_follow_sync_error(user_id, str(exc))
            LOG.exception("Failed Bluesky follow sync for %s", handle)
    return synced, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Mirror Neurofeed users' public Bluesky follow graphs")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    synced, failed = sync_user_follow_graphs(limit=args.limit)
    print(f"Follow graphs: {synced} synced, {failed} failed")


if __name__ == "__main__":
    main()
