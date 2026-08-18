from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Iterable

import requests


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str = "text-embedding-3-small"
    dimensions: int = 1536


def normalized_embedding_text(*parts: str | None) -> str:
    return "\n\n".join(" ".join(part.split()) for part in parts if part and part.strip())


def embedding_input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def vector_literal(values: Iterable[float]) -> str:
    return "[" + ",".join(f"{float(value):.10g}" for value in values) + "]"


class OpenAIEmbedder:
    def __init__(self, api_key: str | None = None, *, config: EmbeddingConfig | None = None, session: requests.Session | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or ""
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for embeddings")
        self.config = config or EmbeddingConfig(
            model=os.getenv("NEUROFEED_EMBEDDING_MODEL", "text-embedding-3-small"),
            dimensions=int(os.getenv("NEUROFEED_EMBEDDING_DIMENSIONS", "1536")),
        )
        self.s = session or requests.Session()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.s.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Neurofeed/0.4",
            },
            json={
                "model": self.config.model,
                "input": texts,
                "dimensions": self.config.dimensions,
                "encoding_format": "float",
            },
            timeout=120,
        )
        response.raise_for_status()
        rows = sorted(response.json().get("data") or [], key=lambda row: row["index"])
        vectors = [row["embedding"] for row in rows]
        if len(vectors) != len(texts):
            raise RuntimeError(f"Embedding response contained {len(vectors)} vectors for {len(texts)} inputs")
        if any(len(vector) != self.config.dimensions for vector in vectors):
            raise RuntimeError("Embedding dimensionality does not match Neurofeed database schema")
        return vectors
