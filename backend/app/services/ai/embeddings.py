"""Configurable embedding providers (Prompt 14).

Embeddings are deliberately decoupled from the conversational model: a small,
cheap embedding model can be served on its OWN endpoint (set
``embedding_provider="openai_compatible"`` + ``embedding_base_url`` to a TEI /
llama.cpp / vLLM embedding server). The default ``"dry_run"`` provider is a
deterministic, offline feature-hashing embedder — it needs no network, produces
stable vectors (so "re-embed only changed content" works), and gives cosine
similarity that tracks token overlap (so retrieval ranking is meaningful in the
test suite and in air-gapped dev).

Only TEXT is ever embedded; binary image data never reaches this layer.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol, Sequence

from app.config import settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    provider: str
    dim: int


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dim: int

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        ...


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 1e-12:
        return vec
    return [v / norm for v in vec]


class DeterministicEmbedder:
    """Offline feature-hashing embedder.

    Each token is hashed into a bucket (with a signed contribution); the vector
    is L2-normalised. Identical text → identical vector; texts sharing vocabulary
    get higher cosine similarity. No randomness, no network."""

    name = "local"

    def __init__(self, *, model: str, dim: int) -> None:
        self.model = model
        self.dim = dim

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = _tokenize(text)
        if not tokens:
            return vec
        for tok in tokens:
            digest = hashlib.sha1(tok.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[bucket] += sign
        return _l2_normalize(vec)

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        vectors = [self._embed_one(t) for t in texts]
        return EmbeddingResult(
            vectors=vectors, model=self.model, provider=self.name, dim=self.dim
        )


class OpenAICompatibleEmbedder:
    """Calls a separate OpenAI-compatible ``/embeddings`` endpoint (TEI, vLLM,
    llama.cpp, OpenAI, …). The API key, base URL and model are configured
    INDEPENDENTLY of the conversational model."""

    name = "openai_compatible"

    def __init__(
        self, *, base_url: str, model: str, dim: int,
        api_key: str | None = None, timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dim = dim
        self.api_key = api_key
        self.timeout = timeout

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        import httpx  # local import; only the real backend needs it

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = httpx.post(
            f"{self.base_url}/embeddings",
            headers=headers,
            json={"model": self.model, "input": list(texts)},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        # Preserve request order (OpenAI returns an ``index`` per item).
        ordered = sorted(data, key=lambda d: d.get("index", 0))
        vectors = [list(item["embedding"]) for item in ordered]
        dim = len(vectors[0]) if vectors else self.dim
        return EmbeddingResult(vectors=vectors, model=self.model, provider=self.name, dim=dim)


_cache: dict[str, EmbeddingProvider] = {}


def reset_embedding_cache() -> None:
    """Clear the cached embedder (tests / config changes)."""
    _cache.clear()


def _build() -> EmbeddingProvider:
    kind = (settings.embedding_provider or "dry_run").lower()
    if kind in ("dry_run", "local"):
        return DeterministicEmbedder(model=settings.embedding_model, dim=settings.embedding_dim)
    if kind in ("openai_compatible", "openai", "vllm", "tei", "lm_studio"):
        if not settings.embedding_base_url:
            raise ValueError(
                f"Embedding provider {kind!r} requires EMBEDDING_BASE_URL "
                "(a separate embedding endpoint)."
            )
        return OpenAICompatibleEmbedder(
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            dim=settings.embedding_dim,
            api_key=settings.embedding_api_key,
            timeout=settings.embedding_request_timeout,
        )
    raise ValueError(f"Unknown embedding provider: {kind!r}")


def get_embedding_provider() -> EmbeddingProvider:
    """Return the configured embedder, cached per process."""
    key = settings.embedding_provider or "dry_run"
    if key not in _cache:
        _cache[key] = _build()
    return _cache[key]


def embed_texts(texts: Sequence[str]) -> EmbeddingResult:
    """Convenience: embed a batch with the configured provider."""
    return get_embedding_provider().embed(texts)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity for two equal-length vectors (0 when either is empty)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return dot / (na * nb)
