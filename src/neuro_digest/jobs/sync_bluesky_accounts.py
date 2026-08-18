from __future__ import annotations

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from neuro_digest.bluesky_db import BlueskyRepository
from neuro_digest.sources.bluesky_shared import fetch_author_feed_events, get_profile

LOG = logging.getLogger(__name__)


def _sync_one(account: dict, *, lookback_days: int, repository: BlueskyRepository) -> tuple[str, int]:
    did = account["did"]
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    profile = get_profile(did)
    repository.upsert_account(profile)
    events = fetch_author_feed_events(did, since=since)
    for event in events:
        repository.persist_feed_event(event)
    repository.mark_account_fetch_success(did, handle=profile.get("handle"))
    return did, len(events)


def sync_bluesky_accounts(*, stale_hours: int = 18, lookback_days: int = 8, limit: int = 1000, workers: int = 8, repository: BlueskyRepository | None = None) -> tuple[int, int, int]:
    repo = repository or BlueskyRepository()
    stale_before = (datetime.now(timezone.utc) - timedelta(hours=stale_hours)).isoformat()
    accounts = repo.get_stale_accounts(stale_before=stale_before, limit=limit)
    succeeded = failed = events = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_sync_one, account, lookback_days=lookback_days, repository=repo): account for account in accounts}
        for future in as_completed(futures):
            account = futures[future]
            try:
                did, count = future.result(); succeeded += 1; events += count
                LOG.info("Fetched %s: %d scholarly feed events", did, count)
            except Exception as exc:
                failed += 1
                error_count = int(account.get("error_count") or 0) + 1
                backoff_hours = min(24, 2 ** min(error_count, 4))
                next_fetch = (datetime.now(timezone.utc) + timedelta(hours=backoff_hours)).isoformat()
                repo.mark_account_fetch_error(account["did"], error_count, str(exc), next_fetch)
                LOG.exception("Failed shared Bluesky account ingestion for %s", account["did"])
    return succeeded, failed, events


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch stale unique Bluesky accounts once globally")
    parser.add_argument("--stale-hours", type=int, default=18)
    parser.add_argument("--lookback-days", type=int, default=8)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ok, failed, events = sync_bluesky_accounts(stale_hours=args.stale_hours, lookback_days=args.lookback_days, limit=args.limit, workers=args.workers)
    print(f"Shared Bluesky ingestion: {ok} accounts synced, {failed} failed, {events} scholarly events persisted")


if __name__ == "__main__":
    main()
