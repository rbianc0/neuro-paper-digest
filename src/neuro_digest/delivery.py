from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any, Callable

from neuro_digest.db import SupabaseDataAPI


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    username: str
    password: str
    from_address: str

    @classmethod
    def from_env(cls) -> "SMTPConfig":
        username = os.getenv("NEUROFEED_SMTP_USERNAME") or ""
        password = os.getenv("NEUROFEED_SMTP_PASSWORD") or ""
        if not username:
            raise RuntimeError("NEUROFEED_SMTP_USERNAME is required")
        if not password:
            raise RuntimeError("NEUROFEED_SMTP_PASSWORD is required")
        return cls(
            host=os.getenv("NEUROFEED_SMTP_HOST", "smtp.gmail.com"),
            port=int(os.getenv("NEUROFEED_SMTP_PORT", "587")),
            username=username,
            password=password,
            from_address=os.getenv("NEUROFEED_EMAIL_FROM") or f"Neurofeed <{username}>",
        )


@dataclass(frozen=True)
class DeliveryResult:
    provider: str
    message_id: str


class SMTPEmailSender:
    def __init__(
        self,
        config: SMTPConfig | None = None,
        *,
        smtp_factory: Callable[..., Any] = smtplib.SMTP,
    ):
        self.config = config or SMTPConfig.from_env()
        self.smtp_factory = smtp_factory

    def send(
        self,
        *,
        to_address: str,
        subject: str,
        html: str,
        text: str,
        digest_id: str,
    ) -> DeliveryResult:
        if not to_address:
            raise ValueError("A recipient email address is required")

        message = EmailMessage()
        message["From"] = self.config.from_address
        message["To"] = to_address
        message["Subject"] = subject
        sender_email = parseaddr(self.config.from_address)[1] or self.config.username
        domain = sender_email.partition("@")[2] or "localhost"
        message_id = f"<neurofeed-{digest_id}@{domain}>"
        message["Message-ID"] = message_id
        message["X-Neurofeed-Digest-ID"] = digest_id
        message.set_content(text or "")
        message.add_alternative(html or "", subtype="html")

        with self.smtp_factory(self.config.host, self.config.port, timeout=60) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(self.config.username, self.config.password)
            smtp.send_message(message)

        return DeliveryResult(provider="smtp", message_id=message_id)


class DeliveryRepository:
    def __init__(self, api: SupabaseDataAPI | None = None):
        self.api = api or SupabaseDataAPI()

    def generated_digests(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self.api._request(
            "GET",
            "digests",
            params={
                "select": "id,user_id,subject,rendered_html,rendered_text,status,generated_at",
                "status": "eq.GENERATED",
                "rendered_html": "not.is.null",
                "order": "generated_at.asc",
                "limit": str(limit),
            },
        ) or []

    def claim_for_send(self, digest_id: str) -> None:
        self.api.update(
            "digests",
            digest_id,
            {"status": "SENDING", "delivery_error": None},
        )

    def release_after_error(self, digest_id: str, error: str) -> None:
        self.api.update(
            "digests",
            digest_id,
            {"status": "GENERATED", "delivery_error": error[:2000]},
        )

    def digest_items(self, digest_id: str) -> list[dict[str, Any]]:
        return self.api._request(
            "GET",
            "digest_items",
            params={"select": "paper_id,explanation_snapshot", "digest_id": f"eq.{digest_id}"},
        ) or []

    def record_impressions(self, *, digest: dict[str, Any]) -> None:
        for item in self.digest_items(digest["id"]):
            self.api.insert(
                "user_paper_events",
                {
                    "user_id": digest["user_id"],
                    "paper_id": item["paper_id"],
                    "digest_id": digest["id"],
                    "event_type": "IMPRESSION",
                    "metadata": {"ranking_snapshot": item.get("explanation_snapshot") or {}},
                },
            )

    def mark_sent(self, digest_id: str, result: DeliveryResult) -> None:
        self.api.update(
            "digests",
            digest_id,
            {
                "status": "SENT",
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "delivery_provider": result.provider,
                "delivery_id": result.message_id,
                "delivery_error": None,
            },
        )
