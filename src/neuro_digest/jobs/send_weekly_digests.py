from __future__ import annotations

from neuro_digest.delivery import DeliveryRepository, SMTPEmailSender
from neuro_digest.newsletter import DigestRepository


def main() -> None:
    sender = SMTPEmailSender()
    delivery_repo = DeliveryRepository()
    newsletter_repo = DigestRepository(delivery_repo.api)
    recipients = {row["user_id"]: row["email"] for row in newsletter_repo.newsletter_users()}

    sent = 0
    failed = 0
    skipped = 0
    for digest in delivery_repo.generated_digests():
        to_address = recipients.get(digest["user_id"])
        if not to_address:
            skipped += 1
            print(f"digest {digest['id']}: skipped because recipient email is unavailable")
            continue

        delivery_repo.claim_for_send(digest["id"])
        try:
            result = sender.send(
                to_address=to_address,
                subject=digest.get("subject") or "Neurofeed Weekly",
                html=digest.get("rendered_html") or "",
                text=digest.get("rendered_text") or "",
                digest_id=digest["id"],
            )
            delivery_repo.record_impressions(digest=digest)
            delivery_repo.mark_sent(digest["id"], result)
            sent += 1
            print(f"digest {digest['id']}: sent to {to_address} as {result.message_id}")
        except Exception as exc:
            failed += 1
            delivery_repo.release_after_error(digest["id"], str(exc))
            print(f"digest {digest['id']}: delivery failed: {exc}")

    print(f"weekly digest delivery complete: sent={sent} failed={failed} skipped={skipped}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
