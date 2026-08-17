from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from neuro_digest.digest_db import DigestRepository
from neuro_digest.newsletter import ResendClient

LOG = logging.getLogger(__name__)


def send_weekly_digests(repository: DigestRepository | None = None, client: ResendClient | None = None) -> tuple[int, int]:
    repo = repository or DigestRepository(); sender = client or ResendClient(); users = {row["user_id"]: row for row in repo.newsletter_users()}; sent = failed = 0
    for digest in repo.pending_delivery():
        user = users.get(digest["user_id"])
        if not user or not user.get("email"):
            repo.update_digest(digest["id"], {"delivery_error": "No newsletter recipient email available"}); failed += 1; continue
        try:
            delivery_id = sender.send(digest_id=digest["id"], to=user["email"], subject=digest["subject"], html_body=digest["rendered_html"], text_body=digest["rendered_text"])
            repo.update_digest(digest["id"], {"status": "SENT", "sent_at": datetime.now(timezone.utc).isoformat(), "delivery_provider": "resend", "delivery_id": delivery_id, "delivery_error": None}); sent += 1
        except Exception as exc:
            repo.update_digest(digest["id"], {"delivery_error": str(exc)[:2000]}); LOG.warning("Digest delivery failed for %s: %s", digest["id"], exc); failed += 1
    return sent, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Send generated Neurofeed weekly digest snapshots"); parser.add_argument("--log-level", default="INFO"); args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sent, failed = send_weekly_digests(); print(f"Weekly digest delivery: {sent} sent, {failed} failed")


if __name__ == "__main__": main()
