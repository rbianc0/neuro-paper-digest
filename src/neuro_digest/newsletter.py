from __future__ import annotations

import hashlib
import html
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from neuro_digest.config import load_config
from neuro_digest.db import SupabaseDataAPI
from neuro_digest.ranking import RankedPaper, rank_for_user
from neuro_digest.summaries import OpenAISummarizer, PaperNarrative


SECTION_ORDER = ["Must Read", "From Your Bluesky Network", "Highly Relevant", "Broader Discovery"]


@dataclass
class PreparedDigest:
    digest_id: str
    user_id: str
    email: str
    subject: str
    html: str
    text: str
    status: str
    item_count: int


class DigestRepository:
    def __init__(self, api: SupabaseDataAPI | None = None):
        self.api = api or SupabaseDataAPI()

    def newsletter_users(self) -> list[dict[str, Any]]:
        return self.api.rpc("get_newsletter_users", {}) or []

    def existing_digest(self, user_id: str, period_start: str, period_end: str, version: str) -> dict[str, Any] | None:
        return self.api.select_one_where(
            "digests",
            {"user_id": user_id, "period_start": period_start, "period_end": period_end, "version": version},
        )

    def create_digest(self, row: dict[str, Any]) -> dict[str, Any]:
        return self.api.insert("digests", row)

    def delete_digest(self, digest_id: str) -> None:
        self.api._request("DELETE", "digests", params={"id": f"eq.{digest_id}"}, prefer="return=minimal")

    def update_digest(self, digest_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return self.api.update("digests", digest_id, changes)

    def paper_data(self, paper_ids: list[str]) -> dict[str, dict[str, Any]]:
        rows = self.api.rpc("get_digest_paper_data", {"p_paper_ids": paper_ids}) or []
        return {row["paper_id"]: row for row in rows}

    def save_item(self, row: dict[str, Any]) -> None:
        self.api.upsert("digest_items", row, on_conflict="digest_id,paper_id")

    def create_interaction_token(self, row: dict[str, Any]) -> None:
        self.api.insert("interaction_tokens", row)

    def digest_items(self, digest_id: str) -> list[dict[str, Any]]:
        return self.api._request(
            "GET",
            "digest_items",
            params={"select": "*", "digest_id": f"eq.{digest_id}", "order": "rank.asc"},
        ) or []


def assign_sections(ranked: list[RankedPaper], *, must_read_count: int, network_threshold: float) -> dict[str, str]:
    sections: dict[str, str] = {}
    focused = [item for item in ranked if item.lane != "broad"]
    for item in focused[:max(0, must_read_count)]:
        sections[item.paper_id] = "Must Read"
    for item in ranked:
        if item.paper_id in sections:
            continue
        if item.lane == "broad":
            sections[item.paper_id] = "Broader Discovery"
        elif item.bluesky_score >= network_threshold:
            sections[item.paper_id] = "From Your Bluesky Network"
        else:
            sections[item.paper_id] = "Highly Relevant"
    return sections


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _new_interaction(repo: DigestRepository, *, base_url: str, user_id: str, paper_id: str, digest_id: str, action: str, redirect_url: str | None, days: int, metadata: dict[str, Any]) -> str:
    raw = secrets.token_urlsafe(32)
    repo.create_interaction_token({
        "token_hash": _token_hash(raw),
        "user_id": user_id,
        "paper_id": paper_id,
        "digest_id": digest_id,
        "action_type": action,
        "redirect_url": redirect_url,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
        "single_use": action != "CLICK",
        "metadata": metadata,
    })
    base = base_url.rstrip("/")
    if action == "CLICK":
        return f"{base}/r/{quote(raw, safe='')}"
    slug = {
        "SAVE": "save",
        "MORE_LIKE_THIS": "more",
        "LESS_LIKE_THIS": "less",
    }[action]
    return f"{base}/action/{slug}/{quote(raw, safe='')}"


def _author_line(paper: dict[str, Any]) -> str:
    names = [author.get("name") for author in (paper.get("authors") or []) if author.get("name")]
    if not names:
        return ""
    if len(names) <= 4:
        return ", ".join(names)
    return ", ".join(names[:3]) + " et al."


def render_digest(*, display_name: str | None, ranked: list[RankedPaper], papers: dict[str, dict[str, Any]], narratives: dict[str, PaperNarrative], sections: dict[str, str], links: dict[str, dict[str, str]]) -> tuple[str, str]:
    by_section: dict[str, list[RankedPaper]] = {section: [] for section in SECTION_ORDER}
    for item in ranked:
        by_section.setdefault(sections[item.paper_id], []).append(item)

    greeting = f"Hi {display_name}," if display_name else "Hello,"
    html_parts = [
        "<!doctype html><html><body style=\"font-family:Arial,sans-serif;max-width:760px;margin:0 auto;padding:24px;color:#111;line-height:1.45\">",
        "<h1 style=\"margin-bottom:4px\">Neurofeed Weekly</h1>",
        f"<p>{html.escape(greeting)} here are the papers selected for you this week.</p>",
    ]
    text_parts = ["NEUROFEED WEEKLY", "", greeting, "Here are the papers selected for you this week.", ""]

    for section in SECTION_ORDER:
        items = by_section.get(section) or []
        if not items:
            continue
        html_parts.append(f"<h2 style=\"margin-top:30px\">{html.escape(section)}</h2>")
        text_parts.extend([section.upper(), "-"])
        for item in items:
            paper = papers[item.paper_id]
            narrative = narratives[item.paper_id]
            item_links = links[item.paper_id]
            title = paper.get("title") or "Untitled paper"
            authors = _author_line(paper)
            venue = paper.get("journal") or ""
            meta = " · ".join(part for part in [authors, venue] if part)
            html_parts.extend([
                "<div style=\"margin:0 0 26px 0;padding:0 0 20px 0;border-bottom:1px solid #ddd\">",
                f"<h3 style=\"margin-bottom:5px\"><a href=\"{html.escape(item_links['read'])}\">{html.escape(title)}</a></h3>",
                f"<div style=\"color:#555;font-size:14px\">{html.escape(meta)}</div>" if meta else "",
                f"<p>{html.escape(narrative.summary)}</p>",
                f"<p><strong>Why this reached you:</strong> {html.escape(narrative.why_recommended)}</p>",
                "<p style=\"font-size:14px\">"
                f"<a href=\"{html.escape(item_links['read'])}\">Read paper</a> · "
                f"<a href=\"{html.escape(item_links['save'])}\">Save</a> · "
                f"<a href=\"{html.escape(item_links['more'])}\">More like this</a> · "
                f"<a href=\"{html.escape(item_links['less'])}\">Less like this</a>"
                "</p></div>",
            ])
            text_parts.extend([
                title,
                meta,
                narrative.summary,
                f"Why this reached you: {narrative.why_recommended}",
                f"Read: {item_links['read']}",
                f"Save: {item_links['save']}",
                f"More like this: {item_links['more']}",
                f"Less like this: {item_links['less']}",
                "",
            ])
    html_parts.append("<p style=\"margin-top:32px;color:#666;font-size:12px\">Neurofeed uses your declared interests, your Bluesky scientific network, and your feedback to rank papers. Following researchers remains on Bluesky.</p></body></html>")
    text_parts.extend(["Neurofeed uses your declared interests, your Bluesky scientific network, and your feedback to rank papers. Following researchers remains on Bluesky."])
    return "".join(html_parts), "\n".join(text_parts)


def prepare_digest_for_user(
    user: dict[str, Any],
    *,
    period_start: date,
    period_end: date,
    ranking_config_path: str = "config/ranking.yaml",
    feedback_config_path: str = "config/feedback.yaml",
    newsletter_config_path: str = "config/newsletter.yaml",
    base_url: str,
    repository: DigestRepository | None = None,
    summarizer: OpenAISummarizer | None = None,
) -> PreparedDigest | None:
    repo = repository or DigestRepository()
    config = load_config(newsletter_config_path)
    digest_cfg = config.get("digest", {})
    summary_cfg = config.get("summary", {})
    version = str(digest_cfg.get("version", "v1"))
    existing = repo.existing_digest(user["user_id"], period_start.isoformat(), period_end.isoformat(), version)
    if existing and existing.get("status") in {"GENERATED", "SENT"} and existing.get("rendered_html"):
        return PreparedDigest(
            digest_id=existing["id"], user_id=user["user_id"], email=user["email"],
            subject=existing.get("subject") or "Neurofeed Weekly",
            html=existing.get("rendered_html") or "", text=existing.get("rendered_text") or "",
            status=existing.get("status") or "GENERATED", item_count=len(repo.digest_items(existing["id"])),
        )
    if existing:
        repo.delete_digest(existing["id"])

    ranked = rank_for_user(
        user["user_id"],
        config_path=ranking_config_path,
        feedback_config_path=feedback_config_path,
        repository=None,
        today=period_end,
    )
    if not ranked:
        return None
    paper_ids = [item.paper_id for item in ranked]
    papers = repo.paper_data(paper_ids)
    if set(paper_ids) - set(papers):
        raise RuntimeError("Canonical digest metadata is missing for one or more ranked papers")

    ranking_snapshots = {item.paper_id: item.to_dict() for item in ranked}
    narrator = summarizer or OpenAISummarizer(model=str(summary_cfg.get("model", "gpt-5.6")))
    narratives = narrator.summarize(
        [papers[paper_id] for paper_id in paper_ids],
        ranking_snapshots,
        max_abstract_chars=int(summary_cfg.get("max_abstract_chars", 5000)),
    )
    sections = assign_sections(
        ranked,
        must_read_count=int(digest_cfg.get("must_read_count", 3)),
        network_threshold=float(digest_cfg.get("network_threshold", 0.35)),
    )

    digest_id = str(uuid.uuid4())
    repo.create_digest({
        "id": digest_id,
        "user_id": user["user_id"],
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "version": version,
        "status": "PREPARING",
    })

    interaction_days = int(digest_cfg.get("interaction_token_days", 45))
    links: dict[str, dict[str, str]] = {}
    try:
        for rank_index, item in enumerate(ranked, start=1):
            paper = papers[item.paper_id]
            narrative = narratives[item.paper_id]
            snapshot = item.to_dict()
            repo.save_item({
                "digest_id": digest_id,
                "paper_id": item.paper_id,
                "rank": rank_index,
                "section": sections[item.paper_id],
                "final_score": item.final_score,
                "semantic_score": item.semantic_score,
                "bluesky_score": item.bluesky_score,
                "fit_score": item.fit_score,
                "quality_score": item.quality_score,
                "broad_discovery_score": item.broad_discovery_score,
                "novelty_score": item.novelty_score,
                "recency_score": item.recency_score,
                "explanation_snapshot": snapshot,
                "summary": narrative.summary,
                "why_recommended": narrative.why_recommended,
                "paper_url": paper.get("canonical_url"),
                "summary_model": narrator.model,
                "summary_input_hash": narrative.input_hash,
            })
            token_meta = {"ranking_snapshot": snapshot, "section": sections[item.paper_id]}
            links[item.paper_id] = {
                "read": _new_interaction(repo, base_url=base_url, user_id=user["user_id"], paper_id=item.paper_id, digest_id=digest_id, action="CLICK", redirect_url=paper.get("canonical_url"), days=interaction_days, metadata=token_meta),
                "save": _new_interaction(repo, base_url=base_url, user_id=user["user_id"], paper_id=item.paper_id, digest_id=digest_id, action="SAVE", redirect_url=None, days=interaction_days, metadata=token_meta),
                "more": _new_interaction(repo, base_url=base_url, user_id=user["user_id"], paper_id=item.paper_id, digest_id=digest_id, action="MORE_LIKE_THIS", redirect_url=None, days=interaction_days, metadata=token_meta),
                "less": _new_interaction(repo, base_url=base_url, user_id=user["user_id"], paper_id=item.paper_id, digest_id=digest_id, action="LESS_LIKE_THIS", redirect_url=None, days=interaction_days, metadata=token_meta),
            }

        rendered_html, rendered_text = render_digest(
            display_name=user.get("display_name"), ranked=ranked, papers=papers,
            narratives=narratives, sections=sections, links=links,
        )
        subject = f"{config.get('email', {}).get('subject_prefix', 'Neurofeed Weekly')} — {len(ranked)} papers for you"
        content_hash = hashlib.sha256((rendered_html + "\n" + rendered_text).encode("utf-8")).hexdigest()
        repo.update_digest(digest_id, {
            "subject": subject,
            "rendered_html": rendered_html,
            "rendered_text": rendered_text,
            "content_hash": content_hash,
            "status": "GENERATED",
        })
        return PreparedDigest(
            digest_id=digest_id, user_id=user["user_id"], email=user["email"],
            subject=subject, html=rendered_html, text=rendered_text, status="GENERATED", item_count=len(ranked),
        )
    except Exception:
        repo.delete_digest(digest_id)
        raise
