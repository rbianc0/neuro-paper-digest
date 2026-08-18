from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class PaperNarrative:
    paper_id: str
    summary: str
    why_recommended: str
    input_hash: str


def summary_input_hash(paper: dict[str, Any], ranking: dict[str, Any]) -> str:
    payload = {
        "paper_id": paper.get("paper_id"),
        "title": paper.get("title"),
        "abstract": paper.get("abstract"),
        "journal": paper.get("journal"),
        "authors": paper.get("authors") or [],
        "ranking": ranking,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _response_text(payload: dict[str, Any]) -> str:
    for item in payload.get("output") or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                return content["text"]
    raise RuntimeError("OpenAI response did not contain output_text")


class OpenAISummarizer:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = "gpt-5.6-luna",
        reasoning_effort: str = "xhigh",
        session: requests.Session | None = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or ""
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for newsletter summaries")
        self.model = os.getenv("NEUROFEED_SUMMARY_MODEL", model)
        self.reasoning_effort = os.getenv("NEUROFEED_SUMMARY_REASONING_EFFORT", reasoning_effort)
        self.s = session or requests.Session()

    def summarize(self, papers: list[dict[str, Any]], rankings: dict[str, dict[str, Any]], *, max_abstract_chars: int = 5000) -> dict[str, PaperNarrative]:
        if not papers:
            return {}
        inputs = []
        hashes: dict[str, str] = {}
        for paper in papers:
            paper_id = paper["paper_id"]
            ranking = rankings[paper_id]
            hashes[paper_id] = summary_input_hash(paper, ranking)
            inputs.append({
                "paper_id": paper_id,
                "title": paper.get("title"),
                "abstract": (paper.get("abstract") or "")[:max_abstract_chars],
                "journal": paper.get("journal"),
                "authors": [a.get("name") for a in (paper.get("authors") or []) if a.get("name")][:12],
                "recommendation_evidence": {
                    "semantic_score": ranking.get("semantic_score"),
                    "bluesky_score": ranking.get("bluesky_score"),
                    "fit_score": ranking.get("fit_score"),
                    "quality_score": ranking.get("quality_score"),
                    "broad_discovery_score": ranking.get("broad_discovery_score"),
                    "lane": ranking.get("lane"),
                    "network": (ranking.get("provenance") or {}).get("network"),
                },
            })

        schema = {
            "type": "object",
            "properties": {
                "papers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "paper_id": {"type": "string"},
                            "summary": {"type": "string"},
                            "why_recommended": {"type": "string"},
                        },
                        "required": ["paper_id", "summary", "why_recommended"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["papers"],
            "additionalProperties": False,
        }
        prompt = (
            "You write concise Neurofeed newsletter annotations for scientists. "
            "Use ONLY the canonical metadata supplied below. Do not browse, infer missing bibliographic facts, "
            "or claim results not supported by the title/abstract. For each paper, write: "
            "(1) a compact 1–2 sentence scientific summary focused on the actual question/method/result when present; "
            "if the abstract is absent or insufficient, explicitly keep the summary limited to what the title supports; "
            "(2) one concise sentence explaining why Neurofeed selected it, grounded only in the recommendation evidence. "
            "Do not mention numerical scores. Do not use hype.\n\nPAPERS:\n" + json.dumps(inputs, ensure_ascii=False)
        )
        response = self.s.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Neurofeed/0.6",
            },
            json={
                "model": self.model,
                "reasoning": {"effort": self.reasoning_effort},
                "input": prompt,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "neurofeed_paper_summaries",
                        "strict": True,
                        "schema": schema,
                    }
                },
            },
            timeout=180,
        )
        response.raise_for_status()
        parsed = json.loads(_response_text(response.json()))
        output: dict[str, PaperNarrative] = {}
        expected = {paper["paper_id"] for paper in papers}
        for row in parsed.get("papers") or []:
            paper_id = row.get("paper_id")
            if paper_id not in expected or paper_id in output:
                continue
            output[paper_id] = PaperNarrative(
                paper_id=paper_id,
                summary=(row.get("summary") or "").strip(),
                why_recommended=(row.get("why_recommended") or "").strip(),
                input_hash=hashes[paper_id],
            )
        missing = expected - set(output)
        if missing:
            raise RuntimeError(f"Summary response omitted {len(missing)} selected papers")
        return output
