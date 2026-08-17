from __future__ import annotations

import hashlib
import os
import uuid
from datetime import date, timedelta
from typing import Any

from neuro_digest.config import load_config
from neuro_digest.digest_db import DigestRepository
from neuro_digest.embeddings import text_hash
from neuro_digest.interactions import build_interaction_link
from neuro_digest.newsletter import OpenAISummaryClient, assign_sections, render_newsletter, why_recommended
from neuro_digest.ranking import RankingService


class DigestService:
    def __init__(self, repository: DigestRepository | None = None, ranking: RankingService | None = None, summarizer: OpenAISummaryClient | None = None, *, config_path: str = "config/digest.yaml", base_url: str | None = None):
        self.repo = repository or DigestRepository()
        self.ranking = ranking or RankingService()
        self.config = load_config(config_path)
        self.summarizer = summarizer or OpenAISummaryClient(model=(self.config.get("summary") or {}).get("model"))
        self.base_url = (base_url or os.getenv("NEUROFEED_BASE_URL") or "").rstrip("/")
        if not self.base_url:
            raise RuntimeError("NEUROFEED_BASE_URL is required to generate newsletter interaction links")

    def generate_user(self, user: dict[str, Any], *, period_start: str, period_end: str, version: str | None = None) -> tuple[str | None, bool]:
        version = version or self.config.get("version", "v1")
        existing = self.repo.existing_digest(user["user_id"], period_start, period_end, version)
        if existing:
            return existing["id"], False
        ranked = self.ranking.rank_user(user["user_id"], total=int(self.config.get("digest_size", 16)))
        if not ranked:
            return None, False
        paper_map = self.repo.paper_data([row.paper_id for row in ranked])
        ranked = [row for row in ranked if row.paper_id in paper_map]
        if not ranked:
            return None, False
        sections = assign_sections(ranked, int(self.config.get("must_read_count", 4)))
        summary_cfg = self.config.get("summary") or {}
        summaries: dict[str, str] = {}
        batch_size = max(1, int(summary_cfg.get("batch_size", 8)))
        summarizable = [paper_map[row.paper_id] for row in ranked if paper_map[row.paper_id].get("abstract")]
        for offset in range(0, len(summarizable), batch_size):
            summaries.update(self.summarizer.summarize(summarizable[offset:offset + batch_size]))
        digest_id = str(uuid.uuid4())
        subject = f"{self.config.get('subject_prefix', 'Neurofeed Weekly')} — {period_end}"
        self.repo.insert_digest({"id": digest_id, "user_id": user["user_id"], "period_start": period_start, "period_end": period_end, "version": version, "status": "BUILDING", "subject": subject})
        token_cfg = self.config.get("interaction_tokens") or {}
        token_rows: list[dict[str, Any]] = []
        item_rows: list[dict[str, Any]] = []
        render_items: list[dict[str, Any]] = []
        try:
            for rank_index, ranked_row in enumerate(ranked, start=1):
                paper = paper_map[ranked_row.paper_id]
                paper_url = paper.get("canonical_url")
                click = build_interaction_link(base_url=self.base_url, user_id=user["user_id"], paper_id=ranked_row.paper_id, digest_id=digest_id, action_type="CLICK", expiry_days=int(token_cfg.get("click_expiry_days", 365)), redirect_url=paper_url, single_use=False) if paper_url else None
                save = build_interaction_link(base_url=self.base_url, user_id=user["user_id"], paper_id=ranked_row.paper_id, digest_id=digest_id, action_type="SAVE", expiry_days=int(token_cfg.get("action_expiry_days", 90)))
                more = build_interaction_link(base_url=self.base_url, user_id=user["user_id"], paper_id=ranked_row.paper_id, digest_id=digest_id, action_type="MORE_LIKE_THIS", expiry_days=int(token_cfg.get("action_expiry_days", 90)))
                less = build_interaction_link(base_url=self.base_url, user_id=user["user_id"], paper_id=ranked_row.paper_id, digest_id=digest_id, action_type="LESS_LIKE_THIS", expiry_days=int(token_cfg.get("action_expiry_days", 90)))
                links = [link for link in (click, save, more, less) if link]
                token_rows.extend(link.db_row for link in links)
                summary = summaries.get(ranked_row.paper_id) or "Abstract unavailable in the current metadata; open the paper for details."
                why = why_recommended(ranked_row)
                summary_input = "\n".join(str(paper.get(key) or "") for key in ("title", "abstract", "journal", "publication_date", "first_online_date"))
                item_rows.append({"digest_id": digest_id, "paper_id": ranked_row.paper_id, "rank": rank_index, "section": sections[ranked_row.paper_id], "final_score": ranked_row.final_score, "semantic_score": ranked_row.semantic_score, "bluesky_score": ranked_row.bluesky_score, "fit_score": ranked_row.fit_score, "quality_score": ranked_row.quality_score, "broad_discovery_score": ranked_row.broad_discovery_score, "novelty_score": ranked_row.novelty_score, "recency_score": ranked_row.recency_score, "summary": summary, "why_recommended": why, "paper_url": paper_url, "summary_model": getattr(self.summarizer, "model", None) if paper.get("abstract") else None, "summary_input_hash": text_hash(summary_input), "explanation_snapshot": {"provenance": ranked_row.provenance, "lane": ranked_row.lane}})
                render_items.append({**paper, "section": sections[ranked_row.paper_id], "summary": summary, "why_recommended": why, "read_url": click.url if click else None, "save_url": save.url, "more_url": more.url, "less_url": less.url})
            self.repo.insert_items(item_rows)
            self.repo.insert_tokens(token_rows)
            html_body, text_body = render_newsletter(subject=subject, items=render_items)
            content_hash = hashlib.sha256(html_body.encode("utf-8")).hexdigest()
            self.repo.update_digest(digest_id, {"rendered_html": html_body, "rendered_text": text_body, "content_hash": content_hash, "status": "GENERATED"})
            return digest_id, True
        except Exception as exc:
            self.repo.update_digest(digest_id, {"status": "ERROR", "delivery_error": str(exc)[:2000]})
            raise


def weekly_period(today: date | None = None) -> tuple[str, str]:
    end = today or date.today()
    start = end - timedelta(days=7)
    return start.isoformat(), end.isoformat()
