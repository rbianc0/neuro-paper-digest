from __future__ import annotations

import argparse
import logging

from neuro_digest.config import load_config
from neuro_digest.db import SupabaseDataAPI
from neuro_digest.embeddings import EmbeddingConfig, OpenAIEmbedder, embedding_input_hash, normalized_embedding_text, vector_literal

LOG = logging.getLogger(__name__)


def _embedding_config(config: dict) -> EmbeddingConfig:
    section = config.get("embedding", {})
    return EmbeddingConfig(
        model=section.get("model", "text-embedding-3-small"),
        dimensions=int(section.get("dimensions", 1536)),
    )


def embed_papers(*, config_path: str = "config/ranking.yaml", limit: int = 1000, api: SupabaseDataAPI | None = None, embedder: OpenAIEmbedder | None = None) -> int:
    config = load_config(config_path); embedding_config = _embedding_config(config); db = api or SupabaseDataAPI(); model = embedder or OpenAIEmbedder(config=embedding_config)
    batch_size = max(1, min(int(config.get("embedding", {}).get("paper_batch_size", 100)), 500))
    rows = db._request(
        "GET", "papers",
        params={
            "select": "id,title,abstract,journal,embedding_input_hash",
            "embedding": "is.null",
            "order": "first_online_date.desc.nullslast,created_at.desc",
            "limit": max(1, min(limit, 10000)),
        },
    ) or []
    embedded = 0
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset:offset + batch_size]
        texts = [normalized_embedding_text(row.get("title"), row.get("abstract"), row.get("journal")) for row in batch]
        valid = [(row, text) for row, text in zip(batch, texts) if text]
        if not valid:
            continue
        vectors = model.embed([text for _, text in valid])
        for (row, text), vector in zip(valid, vectors):
            db._request(
                "PATCH", "papers",
                params={"id": f"eq.{row['id']}"},
                json={
                    "embedding": vector_literal(vector),
                    "embedding_model": embedding_config.model,
                    "embedding_input_hash": embedding_input_hash(text),
                },
                prefer="return=minimal",
            )
            embedded += 1
    return embedded


def embed_declared_profiles(*, config_path: str = "config/ranking.yaml", limit: int = 1000, api: SupabaseDataAPI | None = None, embedder: OpenAIEmbedder | None = None) -> int:
    config = load_config(config_path); embedding_config = _embedding_config(config); db = api or SupabaseDataAPI(); model = embedder or OpenAIEmbedder(config=embedding_config)
    profiles = db._request(
        "GET", "profiles",
        params={
            "select": "user_id,research_description",
            "research_description": "not.is.null",
            "limit": max(1, min(limit, 10000)),
        },
    ) or []
    existing = db._request("GET", "user_embeddings", params={"select": "user_id,declared_input_hash"}) or []
    known_hash = {row["user_id"]: row.get("declared_input_hash") for row in existing}
    pending = []
    for profile in profiles:
        text = normalized_embedding_text(profile.get("research_description"))
        if not text:
            continue
        digest = embedding_input_hash(text)
        if known_hash.get(profile["user_id"]) != digest:
            pending.append((profile, text, digest))
    for offset in range(0, len(pending), 100):
        batch = pending[offset:offset + 100]
        vectors = model.embed([text for _, text, _ in batch])
        for (profile, _text, digest), vector in zip(batch, vectors):
            db.upsert(
                "user_embeddings",
                {
                    "user_id": profile["user_id"],
                    "declared_embedding": vector_literal(vector),
                    "embedding_model": embedding_config.model,
                    "declared_input_hash": digest,
                },
                on_conflict="user_id",
            )
    return len(pending)


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed new Neurofeed papers and changed declared user profiles")
    parser.add_argument("--config", default="config/ranking.yaml")
    parser.add_argument("--paper-limit", type=int, default=5000)
    parser.add_argument("--profile-limit", type=int, default=1000)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    papers = embed_papers(config_path=args.config, limit=args.paper_limit)
    profiles = embed_declared_profiles(config_path=args.config, limit=args.profile_limit)
    print(f"Embeddings: {papers} papers, {profiles} declared profiles")


if __name__ == "__main__":
    main()
