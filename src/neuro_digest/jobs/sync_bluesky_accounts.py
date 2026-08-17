from __future__ import annotations

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from neuro_digest.social_db import SocialRepository
from neuro_digest.sources.bluesky import BlueskyClient, FeedEvent

LOG = logging.getLogger(__name__)


def _fetch_account(did: str, since: datetime, max_pages: int) -> tuple[str, list[FeedEvent]]:
    return did, BlueskyClient().get_author_feed(did, since, max_pages=max_pages)


def sync_bluesky_accounts(*, stale_hours: int = 22, lookback_days: int = 8, batch_size: int = 1000, max_workers: int = 8, max_pages: int = 10, social: SocialRepository | None = None) -> tuple[int, int, int]:
    social = social or SocialRepository(); now = datetime.now(timezone.utc); stale_before = now - timedelta(hours=stale_hours); since = now - timedelta(days=lookback_days); accounts = social.stale_accounts(stale_before, limit=batch_size); succeeded = failed = events_total = 0
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futures = {pool.submit(_fetch_account, account["did"], since, max_pages): account["did"] for account in accounts}
        for future in as_completed(futures):
            did = futures[future]
            try:
                _, events = future.result(); social.persist_events(events); social.mark_account_success(did); succeeded += 1; events_total += len(events); LOG.info("Synced Bluesky account %s: %d scholarly feed events", did, len(events))
            except Exception as exc:
                failed += 1; LOG.warning("Bluesky account sync failed for %s: %s", did, exc); social.mark_account_error(did, str(exc))
    return succeeded, failed, events_total


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch stale unique Bluesky accounts into the shared Neurofeed cache"); parser.add_argument("--stale-hours", type=int, default=22); parser.add_argument("--lookback-days", type=int, default=8); parser.add_argument("--batch-size", type=int, default=1000); parser.add_argument("--max-workers", type=int, default=8); parser.add_argument("--max-pages", type=int, default=10); parser.add_argument("--log-level", default="INFO"); args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    succeeded, failed, events = sync_bluesky_accounts(stale_hours=args.stale_hours, lookback_days=args.lookback_days, batch_size=args.batch_size, max_workers=args.max_workers, max_pages=args.max_pages); print(f"Shared Bluesky sync: {succeeded} accounts succeeded, {failed} failed, {events} scholarly feed events")


if __name__ == "__main__": main()
