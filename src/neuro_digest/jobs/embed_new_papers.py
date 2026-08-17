from __future__ import annotations

import argparse
import logging

from neuro_digest.embeddings import OpenAIEmbeddingClient, paper_embedding_text, text_hash, vector_literal
from neuro_digest.ranking_db import RankingRepository

LOG = logging.getLogger(__name__)


def embed_new_papers(*, batch_size: int = 64, max_papers: int = 5000, repository: RankingRepository | None = None, client: OpenAIEmbeddingClient | None = None) -> int:
    repo = repository or RankingRepository()
    embedder = client or OpenAIEmbeddingClient()
    completed = 0
    while completed < max_papers:
        rows = repo.papers_missing_embeddings(limit=min(batch_size, max_papers - completed))
        if not rows:
            break
        texts = [paper_embedding_text(row) for row in rows]
        usable = [(row, text) for row, text in zip(rows, texts) if text]
        if not usable:
            LOG.warning("No embeddable text in returned paper batch; stopping to avoid a retry loop")
            break
        vectors = embedder.embed([text for _, text in usable])
        repo.save_paper_embeddings([
            {"id": row["id"], "embedding": vector_literal(vector), "embedding_model": embedder.model, "embedding_input_hash": text_hash(text)}
            for (row, text), vector in zip(usable, vectors)
        ])
        completed += len(usable)
        LOG.info("Embedded %d papers (%d total)", len(usable), completed)
        if len(rows) < batch_size:
            break
    return completed


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate embeddings for new/changed canonical Neurofeed papers")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-papers", type=int, default=5000)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    count = embed_new_papers(batch_size=max(1, args.batch_size), max_papers=max(1, args.max_papers))
    print(f"Embedded {count} canonical papers")


if __name__ == "__main__":
    main()
