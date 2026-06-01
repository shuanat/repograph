"""Semantic query: cosine rank over stored vectors (D-14–D-19)."""

from __future__ import annotations

import contextlib
import hashlib
import logging
import sqlite3
from pathlib import Path

import numpy as np

from repograph.config.load import load_config, pathspec_for_config
from repograph.config.model import RepographConfig
from repograph.constants import DB_SQLITE, REPOGRAPH_DIR
from repograph.paths import resolve_repo_root
from repograph.semantic.blob import blob_to_vector
from repograph.semantic.embedder import Embedder
from repograph.semantic.objects import SemanticObject, collect_semantic_objects
from repograph.semantic.preflight import resolve_embedder
from repograph.semantic.rebuild import SemanticRebuildError
from repograph.store.migrate import migrate

logger = logging.getLogger(__name__)

_SNIPPET_MAX = 200


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _metadata_map(
    conn: sqlite3.Connection,
    repo_root: Path,
    config: RepographConfig,
) -> dict[tuple[str, str], SemanticObject]:
    return {
        (obj.object_type, obj.object_key): obj
        for obj in collect_semantic_objects(conn, repo_root, config)
    }


def _path_norm_for_row(
    object_type: str,
    object_key: str,
    meta: SemanticObject | None,
) -> str | None:
    if meta is not None and meta.path_norm is not None:
        return meta.path_norm
    if object_type == "entry":
        return object_key
    return None


def _is_sensitive_hit(
    object_type: str,
    object_key: str,
    path_norm: str | None,
    sensitive_spec,
) -> bool:
    candidate = path_norm
    if candidate is None and object_type == "entry":
        candidate = object_key
    if candidate is None:
        return False
    return bool(sensitive_spec.match_file(candidate))


def _snippet_for(meta: SemanticObject | None, object_key: str) -> str:
    text = meta.embed_text if meta is not None else object_key
    return text[:_SNIPPET_MAX]


def _embed_text_hash(embed_text: str) -> str:
    return hashlib.sha256(embed_text.encode("utf-8")).hexdigest()


def run_semantic_query(
    repo_root: Path | str,
    query_text: str,
    *,
    limit: int = 10,
    embedder: Embedder | None = None,
) -> dict:
    """Rank semantic_objects by cosine similarity to query_text (JSON envelope D-14)."""
    root = resolve_repo_root(repo_root)
    db_path = root / REPOGRAPH_DIR / DB_SQLITE
    migrate(db_path, repo_root=root)

    config = load_config(root)
    _, sensitive_spec = pathspec_for_config(config)

    enc = resolve_embedder(config, embedder=embedder)
    model_id = enc.model_id
    try:
        query_vec = enc.embed_query(query_text)
    except Exception as exc:
        raise SemanticRebuildError(
            f"semantic query embed failed for model {model_id!r}: {exc}"
        ) from exc

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT object_type, object_key, embedding, dim, model_id, source_hash
            FROM semantic_objects
            """
        ).fetchall()
        if not rows:
            return {
                "query": query_text,
                "model_id": model_id,
                "limit": limit,
                "stale_skipped": 0,
                "results": [],
            }

        stored_models = {r[4] for r in rows}
        if len(stored_models) > 1 or (
            len(stored_models) == 1 and model_id not in stored_models
        ):
            raise SemanticRebuildError(
                f"stored embeddings use model_id {sorted(stored_models)!r} but "
                f"resolved {model_id!r}; run `repograph semantic rebuild`"
            )

        meta_map = _metadata_map(conn, root, config)

    query_dim = int(query_vec.shape[0])
    stale_skipped = 0
    scored: list[dict] = []
    for object_type, object_key, blob, dim, _stored_model, stored_hash in rows:
        meta = meta_map.get((object_type, object_key))
        path_norm = _path_norm_for_row(object_type, object_key, meta)
        if _is_sensitive_hit(object_type, object_key, path_norm, sensitive_spec):
            continue

        if meta is not None:
            current_hash = _embed_text_hash(meta.embed_text)
            if stored_hash != current_hash:
                stale_skipped += 1
                logger.warning(
                    "semantic query: skipping stale %s/%s (source_hash mismatch)",
                    object_type,
                    object_key,
                )
                continue

        stored_dim = int(dim)
        if stored_dim != query_dim:
            raise SemanticRebuildError(
                f"stored embedding dim {stored_dim} != query dim {query_dim} "
                f"for {object_type}/{object_key!r}; run `repograph semantic rebuild`"
            )
        try:
            vec = blob_to_vector(blob, dim=stored_dim)
        except ValueError as exc:
            raise SemanticRebuildError(
                f"invalid embedding blob for {object_type}/{object_key!r}: {exc}"
            ) from exc
        score = cosine_similarity(query_vec, vec)
        event_id = meta.event_id if meta is not None else None
        scored.append(
            {
                "object_type": object_type,
                "object_key": object_key,
                "score": score,
                "path_norm": path_norm,
                "event_id": event_id,
                "snippet": _snippet_for(meta, object_key),
            }
        )

    scored.sort(key=lambda hit: hit["score"], reverse=True)
    if limit > 0:
        scored = scored[:limit]

    return {
        "query": query_text,
        "model_id": model_id,
        "limit": limit,
        "stale_skipped": stale_skipped,
        "results": scored,
    }
