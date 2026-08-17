from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from neuro_digest.util import normalized_title


def load_taxonomy(path: str | Path = "config/feature_taxonomy.yaml") -> dict[str, dict[str, list[str]]]:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized = normalized_title(phrase)
    return bool(normalized) and f" {normalized} " in f" {text} "


def _paper_text(paper: dict[str, Any]) -> str:
    metadata = paper.get("metadata") or {}
    return normalized_title(" ".join([paper.get("title") or "", paper.get("abstract") or "", str(metadata.get("category") or ""), str(metadata.get("species") or "")]))


def extract_profile_features(description: str, taxonomy: dict[str, dict[str, list[str]]]) -> list[dict[str, Any]]:
    text = normalized_title(description)
    out: list[dict[str, Any]] = []
    for feature_type, entries in taxonomy.items():
        for feature_value, synonyms in entries.items():
            terms = [feature_value.replace("_", " "), *(synonyms or [])]
            if any(_contains_phrase(text, term) for term in terms):
                out.append({"feature_type": feature_type.upper(), "feature_value": feature_value, "weight": 1.0})
    return out


def extract_paper_features(paper: dict[str, Any], taxonomy: dict[str, dict[str, list[str]]]) -> list[tuple[str, str]]:
    text = _paper_text(paper)
    out: list[tuple[str, str]] = []
    for feature_type, entries in taxonomy.items():
        for feature_value, synonyms in entries.items():
            terms = [feature_value.replace("_", " "), *(synonyms or [])]
            if any(_contains_phrase(text, term) for term in terms):
                out.append((feature_type.upper(), feature_value))
    return out


def paper_feature_fit(paper: dict[str, Any], user_features: list[dict[str, Any]], taxonomy: dict[str, dict[str, list[str]]]) -> float:
    taxonomy_types = {key.casefold() for key in taxonomy}
    relevant = [feature for feature in user_features if feature.get("feature_type", "").casefold() in taxonomy_types and float(feature.get("weight") or 0.0) != 0]
    if not relevant:
        return 0.5
    present = set(extract_paper_features(paper, taxonomy))
    positive_total = sum(max(0.0, float(feature.get("weight") or 0.0)) for feature in relevant)
    negative_total = sum(abs(min(0.0, float(feature.get("weight") or 0.0))) for feature in relevant)
    positive_match = sum(max(0.0, float(feature.get("weight") or 0.0)) for feature in relevant if (feature["feature_type"].upper(), feature["feature_value"]) in present)
    negative_match = sum(abs(min(0.0, float(feature.get("weight") or 0.0))) for feature in relevant if (feature["feature_type"].upper(), feature["feature_value"]) in present)
    positive_score = positive_match / positive_total if positive_total else 0.5
    negative_score = negative_match / negative_total if negative_total else 0.0
    if positive_total:
        return max(0.0, min(1.0, positive_score * (1 - 0.5 * negative_score)))
    return max(0.0, min(1.0, 0.5 * (1 - negative_score)))
