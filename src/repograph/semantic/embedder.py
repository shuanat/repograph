"""Embedder protocol and test/production implementations."""

from __future__ import annotations

import hashlib
from typing import Iterable, Protocol

import numpy as np

_FAKE_DIM = 384
_DEFAULT_MODEL_ID = "BAAI/bge-small-en-v1.5"


class Embedder(Protocol):
    model_id: str
    dim: int

    def embed_passages(self, texts: list[str]) -> list[np.ndarray]:
        """Return one float32 vector per corpus passage."""
        ...

    def embed_query(self, text: str) -> np.ndarray:
        """Return a float32 query vector."""
        ...


class FakeEmbedder:
    """Deterministic vectors for tests (no network)."""

    model_id: str = _DEFAULT_MODEL_ID
    dim: int = _FAKE_DIM

    def embed_passages(self, texts: list[str]) -> list[np.ndarray]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text)

    def _vector(self, text: str) -> np.ndarray:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], "big") % (2**31)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(self.dim).astype(np.float32)
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        return vec

    def encode(self, texts: list[str], *, dim: int = _FAKE_DIM) -> list[np.ndarray]:
        """Backward-compatible alias used by early Phase 6 tests."""
        if dim != self.dim:
            msg = f"FakeEmbedder dim is {self.dim}, got dim={dim}"
            raise ValueError(msg)
        return self.embed_passages(texts)


class FastEmbedEmbedder:
    """FastEmbed ONNX encoder for corpus and query vectors."""

    def __init__(self, model_id: str) -> None:
        from fastembed import TextEmbedding

        self.model_id = model_id
        self._model = TextEmbedding(model_name=model_id)
        self.dim = int(TextEmbedding.get_embedding_size(model_id))

    def embed_passages(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []
        raw = list(
            self._model.passage_embed(texts, batch_size=32)
        )
        return [np.asarray(v, dtype=np.float32) for v in raw]

    def embed_query(self, text: str) -> np.ndarray:
        raw = next(iter(self._model.query_embed([text])))
        return np.asarray(raw, dtype=np.float32)

    def encode(self, texts: list[str], *, dim: int) -> list[np.ndarray]:
        vectors = self.embed_passages(texts)
        for vec in vectors:
            if int(vec.shape[0]) != dim:
                msg = f"expected dim {dim}, got {vec.shape[0]}"
                raise ValueError(msg)
        return vectors
