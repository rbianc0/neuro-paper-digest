from __future__ import annotations

import hashlib
import json
import os
from typing import Iterable

import requests


DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
API_URL = "https://api.openai.com/v1/embeddings"


def normalize_embedding_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_embedding_text(text).encode("utf-8")).hexdigest()


def paper_embedding_text(paper: dict) -> str:
    parts = []
    if paper.get("title"):
        parts.append(f"Title: {paper['title']}")
    if paper.get("abstract"):
        parts.append(f"Abstract: {paper['abstract']}")
    if paper.get("journal"):
        parts.append(f"Venue: {paper['journal']}")
    return normalize_embedding_text("\n".join(parts))[:24000]


def profile_embedding_text(description: str) -> str:
    return normalize_embedding_text(f"Research interests: {description}")[:24000]


def vector_literal(vector: Iterable[float]) -> str:
    return json.dumps([float(x) for x in vector], separators=(",", ":"))


def parse_vector(value) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [float(x) for x in value]
    if isinstance(value, str):
        parsed = json.loads(value)
        return [float(x) for x in parsed]
    raise TypeError(f"Unsupported vector representation: {type(value)!r}")


class OpenAIEmbeddingClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or ""
        self.model = model or os.getenv("NEUROFEED_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required to generate Neurofeed embeddings")
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Neurofeed/0.4",
        })

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.s.post(
            API_URL,
            json={"model": self.model, "input": texts, "encoding_format": "float"},
            timeout=120,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI embeddings failed ({response.status_code}): {response.text[:500]}")
        payload = response.json()
        rows = sorted(payload.get("data") or [], key=lambda row: row.get("index", 0))
        vectors = [row.get("embedding") for row in rows]
        if len(vectors) != len(texts):
            raise RuntimeError(f"Embedding response count mismatch: expected {len(texts)}, got {len(vectors)}")
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSIONS:
                raise RuntimeError(f"Unexpected embedding dimensionality for {self.model}")
        return vectors
