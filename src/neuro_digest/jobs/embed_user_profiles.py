from __future__ import annotations

import os

from neuro_digest.db import SupabaseDataAPI
from neuro_digest.embeddings import OpenAIEmbedder, embedding_input_hash, normalized_embedding_text, vector_literal


def embed_user_profiles(
    *,
    api: SupabaseDataAPI | None = None,
    embedder: OpenAIEmbedder | None = None,
    batch_size: int | None = None,
) -> dict[str, int]:
    api = api or SupabaseDataAPI()
    embedder = embedder or OpenAIEmbedder()
    batch_size = batch_size or int(os.getenv("NEUROFEED_USER_EMBED_BATCH_SIZE", "100"))

    profiles = api._request(
        "GET",
        "profiles",
        params={
            "select": "user_id,research_description",
            "research_description": "not.is.null",
            "order": "created_at.asc",
        },
    ) or []
    existing_rows = api._request(
        "GET",
        "user_embeddings",
        params={"select": "user_id,declared_input_hash,embedding_model"},
    ) or []
    existing = {row["user_id"]: row for row in existing_rows}

    pending: list[tuple[str, str, str]] = []
    skipped = 0
    for profile in profiles:
        text = normalized_embedding_text(profile.get("research_description"))
        if not text:
            skipped += 1
            continue
        input_hash = embedding_input_hash(text)
        current = existing.get(profile["user_id"])
        if (
            current
            and current.get("declared_input_hash") == input_hash
            and current.get("embedding_model") == embedder.config.model
        ):
            skipped += 1
            continue
        pending.append((profile["user_id"], text, input_hash))

    embedded = 0
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        vectors = embedder.embed([text for _, text, _ in batch])
        for (user_id, _text, input_hash), vector in zip(batch, vectors, strict=True):
            api.upsert(
                "user_embeddings",
                {
                    "user_id": user_id,
                    "declared_embedding": vector_literal(vector),
                    "embedding_model": embedder.config.model,
                    "declared_input_hash": input_hash,
                },
                on_conflict="user_id",
            )
            embedded += 1

    return {"profiles": len(profiles), "embedded": embedded, "skipped": skipped}


def main() -> None:
    stats = embed_user_profiles()
    print(
        "user profile embeddings: "
        f"profiles={stats['profiles']} embedded={stats['embedded']} skipped={stats['skipped']}"
    )


if __name__ == "__main__":
    main()
