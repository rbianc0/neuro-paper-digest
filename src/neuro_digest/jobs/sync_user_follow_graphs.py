from __future__ import annotations

import argparse
import logging

from neuro_digest.social_db import SocialRepository
from neuro_digest.sources.bluesky import BlueskyAccountRef, BlueskyClient

LOG = logging.getLogger(__name__)


def sync_user_follow_graphs(social: SocialRepository | None = None, client: BlueskyClient | None = None) -> tuple[int, int, int]:
    social = social or SocialRepository(); client = client or BlueskyClient(); users = social.profiles_with_bluesky(); succeeded = failed = follows_total = 0
    for profile in users:
        user_id = profile["user_id"]; handle = profile["bluesky_handle"]
        try:
            did = client.resolve_handle(handle)
            try: own_account = client.get_profile(did)
            except Exception: own_account = BlueskyAccountRef(did=did, handle=handle)
            social.upsert_account(own_account, profile_fetched=True)
            follows = client.get_follows(did)
            count = social.replace_follow_graph(user_id, bluesky_did=did, bluesky_handle=own_account.handle or handle, follows=follows)
            succeeded += 1; follows_total += count; LOG.info("Synced Bluesky follows for %s: %d", handle, count)
        except Exception as exc:
            failed += 1; LOG.warning("Bluesky follow sync failed for %s: %s", handle, exc); social.mark_profile_sync_error(user_id, str(exc))
    return succeeded, failed, follows_total


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize Neurofeed users' public Bluesky follow graphs"); parser.add_argument("--log-level", default="INFO"); args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    succeeded, failed, follows = sync_user_follow_graphs(); print(f"Follow graph sync: {succeeded} users succeeded, {failed} failed, {follows} active follow relationships")


if __name__ == "__main__": main()
