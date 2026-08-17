from __future__ import annotations

import argparse
import logging

from neuro_digest.digest import DigestService, weekly_period

LOG = logging.getLogger(__name__)


def generate_weekly_digests(service: DigestService | None = None) -> tuple[int, int, int]:
    service = service or DigestService(); start, end = weekly_period(); created = existing = empty = 0
    for user in service.repo.newsletter_users():
        try:
            digest_id, was_created = service.generate_user(user, period_start=start, period_end=end)
            if digest_id is None: empty += 1
            elif was_created: created += 1
            else: existing += 1
        except Exception as exc:
            LOG.exception("Digest generation failed for %s: %s", user.get("user_id"), exc)
    return created, existing, empty


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze weekly Neurofeed ranked recommendations into immutable digest snapshots"); parser.add_argument("--log-level", default="INFO"); args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    created, existing, empty = generate_weekly_digests(); print(f"Weekly digest generation: {created} created, {existing} already existed, {empty} users with no candidates")


if __name__ == "__main__": main()
