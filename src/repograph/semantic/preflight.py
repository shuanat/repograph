"""Embedder availability checks for doctor and semantic CLI."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from repograph.config.model import RepographConfig
from repograph.semantic.config import resolve_embedding_model
from repograph.semantic.embedder import Embedder, FastEmbedEmbedder

if TYPE_CHECKING:
    pass


def probe_fastembed_cache(model_id: str) -> tuple[str, str]:
    """Return (level, message) for doctor: PASS, WARN, or FAIL."""
    try:
        import onnxruntime  # noqa: F401
    except ImportError as exc:
        return "FAIL", f"onnxruntime import failed: {exc}"

    try:
        from fastembed import TextEmbedding

        TextEmbedding(model_name=model_id, local_files_only=True, lazy_load=True)
    except Exception as exc:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            return (
                "WARN",
                f"CI runner: embedding model not cached ({model_id}); "
                "semantic rebuild skipped in default CI",
            )
        msg = str(exc).lower()
        if "local_files_only" in msg or "not found" in msg or "cache" in msg:
            cache = os.environ.get("FASTEMBED_CACHE_PATH", "(default fastembed cache)")
            return (
                "WARN",
                f"model not cached yet ({model_id}); run semantic rebuild or set "
                f"FASTEMBED_CACHE_PATH={cache}",
            )
        return "FAIL", f"cannot probe {model_id}: {exc}"
    return "PASS", f"model cached locally ({model_id})"


def resolve_embedder(
    config: RepographConfig,
    *,
    embedder: Embedder | None = None,
):
    """Return injectable embedder or construct FastEmbedEmbedder; fail fast if unavailable."""
    from repograph.semantic.rebuild import SemanticRebuildError

    if embedder is not None:
        return embedder

    model_id = resolve_embedding_model(config)
    try:
        import onnxruntime  # noqa: F401
    except ImportError as exc:
        msg = (
            f"semantic encode requires onnxruntime: {exc}. "
            "Install repograph with semantic extras or run repograph doctor."
        )
        raise SemanticRebuildError(msg) from exc

    try:
        return FastEmbedEmbedder(model_id)
    except Exception as exc:
        cache_hint = os.environ.get("FASTEMBED_CACHE_PATH", "(default fastembed cache)")
        msg = (
            f"semantic encode failed for model {model_id!r}: {exc}. "
            f"Ensure the model is cached or set FASTEMBED_CACHE_PATH={cache_hint}"
        )
        raise SemanticRebuildError(msg) from exc
