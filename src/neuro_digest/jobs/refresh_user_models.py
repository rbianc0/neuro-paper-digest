from __future__ import annotations

import argparse
import logging

from neuro_digest.embeddings import OpenAIEmbeddingClient, profile_embedding_text, text_hash
from neuro_digest.features import extract_profile_features, load_taxonomy
from neuro_digest.ranking_db import RankingRepository

LOG = logging.getLogger(__name__)


def refresh_user_models(*, repository: RankingRepository | None = None, client: OpenAIEmbeddingClient | None = None, taxonomy_path: str = "config/feature_taxonomy.yaml") -> tuple[int, int]:
    repo = repository or RankingRepository()
    embedder = client or OpenAIEmbeddingClient()
    taxonomy = load_taxonomy(taxonomy_path)
    profiles = repo.profiles_with_research_descriptions()
    changed: list[tuple[dict, str, str]] = []
    feature_refreshes = 0
    for profile in profiles:
        description = (profile.get("research_description") or "").strip()
        if not description:
            continue
        text = profile_embedding_text(description)
        digest = text_hash(text)
        existing = repo.get_user_embedding(profile["user_id"]) or {}
        if not existing.get("declared_embedding") or existing.get("declared_input_hash") != digest or existing.get("embedding_model") != embedder.model:
            changed.append((profile, text, digest))
        repo.replace_inferred_features(profile["user_id"], extract_profile_features(description, taxonomy))
        feature_refreshes += 1
    if changed:
        vectors = embedder.embed([text for _, text, _ in changed])
        for (profile, _text, digest), vector in zip(changed, vectors):
            repo.save_declared_user_embedding(profile["user_id"], embedding=vector, model=embedder.model, input_hash=digest)
    LOG.info("Refreshed %d declared embeddings and %d inferred feature profiles", len(changed), feature_refreshes)
    return len(changed), feature_refreshes


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh declared Neurofeed user embeddings and deterministic profile features")
    parser.add_argument("--taxonomy", default="config/feature_taxonomy.yaml")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    embeddings, features = refresh_user_models(taxonomy_path=args.taxonomy)
    print(f"Refreshed {embeddings} declared profile embeddings and {features} inferred feature profiles")


if __name__ == "__main__":
    main()
