from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from neuro_digest.util import normalized_title


def load_taxonomy(path: str | Path = "config/feature_taxonomy.yaml") -> dict[str, dict[str, list[str]]]:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized = normalized_title(phrase)
    if not normalized:
        return False
    return f" {normalized} " in f" {text} "


def extract_profile_features(description: str, taxonomy: dict[str, dict[str, list[str]]]) -> list[dict[str, Any]]:
    text = normalized_title(description)
    out: list[dict[str, Any]] = []
    for feature_type, entries in taxonomy.items():
        for feature_value, synonyms in entries.items():
            terms = [feature_value.replace("_", " "), *(synonyms or [])]
            if any(_contains_phrase(text, term) for term in terms):
                out.append({"feature_type": feature_type.upper(), "feature_value": feature_value, "weight": 1.0})
    return out


def paper_feature_fit(paper: dict[str, Any], user_features: list[dict[str, Any]], taxonomy: dict[str, dict[str, list[str]]]) -> float:
    relevant = [feature for feature in user_features if feature.get("feature_type", "").casefold() in {key.casefold() for key in taxonomy}]
    if not relevant:
        return 0.5
    metadata = paper.get("metadata") or {}
    text = normalized_title(" ".join([paper.get("title") or "", paper.get("abstract") or "", str(metadata.get("category") or ""), str(metadata.get("species") or "")]))
    matched = total = 0.0
    taxonomy_by_type = {key.casefold(): value for key, value in taxonomy.items()}
    for feature in relevant:
        weight = max(0.0, float(feature.get("weight") or 0.0))
        total += weight
        entries = taxonomy_by_type.get(feature["feature_type"].casefold(), {})
        synonyms = entries.get(feature["feature_value"], [])
        terms = [feature["feature_value"].replace("_", " "), *synonyms]
        if any(_contains_phrase(text, term) for term in terms):
            matched += weight
    return matched / total if total else 0.5
