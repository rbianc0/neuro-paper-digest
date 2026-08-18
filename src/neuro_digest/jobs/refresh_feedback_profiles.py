from __future__ import annotations

import argparse
import logging

from neuro_digest.db import SupabaseDataAPI
from neuro_digest.feedback import FeedbackRepository, refresh_user_learning

LOG = logging.getLogger(__name__)


def users_with_feedback(api: SupabaseDataAPI, *, limit: int = 10000) -> list[str]:
    rows = api._request(
        "GET",
        "user_paper_events",
        params={"select": "user_id", "limit": max(1, min(limit, 50000))},
    ) or []
    return list(dict.fromkeys(row["user_id"] for row in rows if row.get("user_id")))


def refresh_feedback_profiles(*, config_path: str = "config/feedback.yaml", limit: int = 10000) -> tuple[int, int]:
    api = SupabaseDataAPI(); repository = FeedbackRepository(api); refreshed = failed = 0
    for user_id in users_with_feedback(api, limit=limit):
        try:
            state = refresh_user_learning(user_id, config_path=config_path, repository=repository)
            refreshed += 1
            LOG.info(
                "Refreshed feedback profile %s: %d effective papers (%d positive, %d negative)",
                user_id, state.feedback_count, state.positive_count, state.negative_count,
            )
        except Exception:
            failed += 1
            LOG.exception("Failed to refresh feedback profile %s", user_id)
    return refreshed, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Neurofeed learned preference centroids from append-only feedback")
    parser.add_argument("--config", default="config/feedback.yaml")
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    refreshed, failed = refresh_feedback_profiles(config_path=args.config, limit=args.limit)
    print(f"Feedback learning: {refreshed} profiles refreshed, {failed} failed")


if __name__ == "__main__":
    main()
