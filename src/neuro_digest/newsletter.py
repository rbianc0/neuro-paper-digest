from __future__ import annotations

import html
import json
import os
from typing import Any

import requests

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
RESEND_URL = "https://api.resend.com/emails"


def _response_output_text(payload: dict[str, Any]) -> str:
    texts: list[str] = []
    for item in payload.get("output") or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                texts.append(content["text"])
    return "".join(texts)


class OpenAISummaryClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or ""
        self.model = model or os.getenv("NEUROFEED_SUMMARY_MODEL") or "gpt-5-mini"
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for digest summaries")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "User-Agent": "Neurofeed/0.6"})

    def summarize(self, papers: list[dict[str, Any]]) -> dict[str, str]:
        if not papers:
            return {}
        prompt_rows = [{"paper_id": paper["paper_id"], "title": paper.get("title"), "authors": [author.get("name") for author in (paper.get("authors") or [])[:12]], "journal": paper.get("journal"), "publication_date": paper.get("first_online_date") or paper.get("publication_date"), "abstract": paper.get("abstract")} for paper in papers]
        schema = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"paper_id": {"type": "string"}, "summary": {"type": "string"}}, "required": ["paper_id", "summary"], "additionalProperties": False}}}, "required": ["items"], "additionalProperties": False}
        prompt = "Summarize each scientific paper in 1-2 concise factual sentences for a researcher newsletter. Use only the supplied metadata/abstract. Do not invent results, methods, sample sizes, claims, bibliographic details, or significance. If the abstract is insufficient, state only what the metadata supports. Return one item for every paper_id.\n\n" + json.dumps(prompt_rows, ensure_ascii=False)
        response = self.s.post(OPENAI_RESPONSES_URL, json={"model": self.model, "input": prompt, "store": False, "text": {"format": {"type": "json_schema", "name": "neurofeed_digest_summaries", "strict": True, "schema": schema}}}, timeout=180)
        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI digest summary failed ({response.status_code}): {response.text[:500]}")
        parsed = json.loads(_response_output_text(response.json()))
        result = {item["paper_id"]: item["summary"].strip() for item in parsed.get("items") or []}
        missing = {paper["paper_id"] for paper in papers} - set(result)
        if missing:
            raise RuntimeError(f"Summary response omitted paper IDs: {sorted(missing)}")
        return result


class ResendClient:
    def __init__(self, api_key: str | None = None, from_email: str | None = None):
        self.api_key = api_key or os.getenv("RESEND_API_KEY") or ""
        self.from_email = from_email or os.getenv("NEUROFEED_FROM_EMAIL") or ""
        if not self.api_key or not self.from_email:
            raise RuntimeError("RESEND_API_KEY and NEUROFEED_FROM_EMAIL are required for newsletter delivery")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "User-Agent": "Neurofeed/0.6"})

    def send(self, *, digest_id: str, to: str, subject: str, html_body: str, text_body: str) -> str:
        response = self.s.post(RESEND_URL, headers={"Idempotency-Key": f"neurofeed-digest-{digest_id}"}, json={"from": self.from_email, "to": [to], "subject": subject, "html": html_body, "text": text_body, "tags": [{"name": "digest_id", "value": digest_id}]}, timeout=60)
        if response.status_code >= 400:
            raise RuntimeError(f"Resend delivery failed ({response.status_code}): {response.text[:500]}")
        delivery_id = (response.json() or {}).get("id")
        if not delivery_id:
            raise RuntimeError("Resend response did not contain an email ID")
        return delivery_id


def why_recommended(row) -> str:
    reasons: list[str] = []
    provenance = row.provenance
    if provenance.get("authored_by_followed"):
        reasons.append("authored by a scientist you follow on Bluesky")
    actors = int(provenance.get("independent_followed_actors") or 0)
    if actors:
        reasons.append(f"shared or discussed by {actors} scientist{'s' if actors != 1 else ''} you follow")
    if row.semantic_score >= 0.75:
        reasons.append("strong semantic match to your research profile")
    if row.fit_score >= 0.75:
        reasons.append("strong method/species fit")
    if row.lane == "BROAD":
        reasons.append("selected for broader scientific discovery")
    if not reasons:
        reasons.append("high combined Neurofeed relevance score")
    return "; ".join(reasons[:3]).capitalize() + "."


def assign_sections(rows, must_read_count: int = 4) -> dict[str, str]:
    sections: dict[str, str] = {}
    for index, row in enumerate(rows):
        if index < must_read_count:
            sections[row.paper_id] = "Must Read"
        elif row.lane == "BROAD":
            sections[row.paper_id] = "Broader Discovery"
        elif row.provenance.get("network_candidate"):
            sections[row.paper_id] = "From Your Bluesky Network"
        else:
            sections[row.paper_id] = "Highly Relevant"
    return sections


def render_newsletter(*, subject: str, items: list[dict[str, Any]]) -> tuple[str, str]:
    section_order = ["Must Read", "Highly Relevant", "From Your Bluesky Network", "Broader Discovery"]
    grouped = {section: [item for item in items if item["section"] == section] for section in section_order}
    html_parts = ["<html><body style=\"font-family:Arial,sans-serif;max-width:760px;margin:auto;color:#111\">", f"<h1>{html.escape(subject)}</h1>"]
    text_parts = [subject, ""]
    for section in section_order:
        rows = grouped[section]
        if not rows:
            continue
        html_parts.append(f"<h2>{html.escape(section)}</h2>")
        text_parts.extend([section, "=" * len(section), ""])
        for item in rows:
            title = html.escape(item.get("title") or "Untitled paper")
            authors = ", ".join(author.get("name") or "" for author in (item.get("authors") or [])[:6] if author.get("name"))
            if len(item.get("authors") or []) > 6:
                authors += ", et al."
            venue = item.get("journal") or ""
            summary = item.get("summary") or ""
            why = item.get("why_recommended") or ""
            html_parts.append(f"<div style=\"margin:0 0 28px\"><h3 style=\"margin-bottom:6px\">{title}</h3>")
            if authors:
                html_parts.append(f"<div style=\"color:#555\">{html.escape(authors)}</div>")
            if venue:
                html_parts.append(f"<div style=\"color:#777\">{html.escape(venue)}</div>")
            html_parts.append(f"<p>{html.escape(summary)}</p><p><strong>Why:</strong> {html.escape(why)}</p><p>")
            if item.get("read_url"):
                html_parts.append(f"<a href=\"{html.escape(item['read_url'], quote=True)}\">Read paper</a> &nbsp; ")
            html_parts.append(f"<a href=\"{html.escape(item['save_url'], quote=True)}\">Save</a> &nbsp; <a href=\"{html.escape(item['more_url'], quote=True)}\">More like this</a> &nbsp; <a href=\"{html.escape(item['less_url'], quote=True)}\">Less like this</a></p></div>")
            text_parts.extend([item.get("title") or "Untitled paper", authors, venue, summary, f"Why: {why}"])
            if item.get("read_url"):
                text_parts.append(f"Read: {item['read_url']}")
            text_parts.extend([f"Save: {item['save_url']}", f"More like this: {item['more_url']}", f"Less like this: {item['less_url']}", ""])
    html_parts.append("</body></html>")
    return "".join(html_parts), "\n".join(text_parts)
