"""Embedding model resolution (D-09, D-10)."""

from __future__ import annotations

import os

from repograph.config.model import RepographConfig

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
_ENV_EMBEDDING_MODEL = "REPOGRAPH_EMBEDDING_MODEL"


def resolve_embedding_model(config: RepographConfig) -> str:
    """Env override, then yaml semantic.embedding_model, then default."""
    env_val = os.environ.get(_ENV_EMBEDDING_MODEL, "").strip()
    if env_val:
        return env_val
    if config.semantic is not None:
        yaml_val = (config.semantic.embedding_model or "").strip()
        if yaml_val:
            return yaml_val
    return DEFAULT_EMBEDDING_MODEL
