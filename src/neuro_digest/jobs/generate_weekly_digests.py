from __future__ import annotations

import os
from datetime import date, timedelta

from neuro_digest.newsletter import DigestRepository, prepare_digest_for_user


def _period_end() -> date:
    raw = os.getenv("NEUROFEED_PERIOD_END")
    return date.fromisoformat(raw) if raw else date.today()


def main() -> None:
    base_url = (os.getenv("NEUROFEED_PUBLIC_URL") or "").strip()
    if not base_url:
        raise RuntimeError("NEUROFEED_PUBLIC_URL is required to generate newsletter interaction links")

    repo = DigestRepository()
    users = repo.newsletter_users()
    period_end = _period_end()
    period_start = period_end - timedelta(days=6)

    generated = 0
    skipped = 0
    for user in users:
        digest = prepare_digest_for_user(
            user,
            period_start=period_start,
            period_end=period_end,
            base_url=base_url,
            repository=repo,
        )
        if digest is None:
            skipped += 1
            continue
        generated += 1
        print(f"digest {digest.digest_id}: {digest.email} ({digest.item_count} papers, {digest.status})")

    print(f"weekly digest generation complete: users={len(users)} generated_or_existing={generated} empty={skipped}")


if __name__ == "__main__":
    main()
