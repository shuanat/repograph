"""Full semantic rebuild for all object types."""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import sqlite3
from pathlib import Path

from repograph.changes.ingest import utc_now
from repograph.config.load import load_config
from repograph.constants import DB_SQLITE, REPOGRAPH_DIR
from repograph.paths import resolve_repo_root
from repograph.semantic.blob import vector_to_blob
from repograph.semantic.embedder import Embedder
from repograph.semantic.preflight import resolve_embedder
from repograph.semantic.objects import collect_semantic_objects
from repograph.store.migrate import migrate

logger = logging.getLogger(__name__)


class SemanticRebuildError(Exception):
    """Embedding or persistence failure during semantic rebuild."""


def finalize_post_commit_message() -> str:
    return (
        "Finalize persisted to the database, but semantic rebuild failed. "
        "Re-run `repograph semantic rebuild`."
    )


def apply_post_commit_message() -> str:
    return (
        "Apply persisted to the database, but semantic rebuild failed. "
        "Re-run `repograph semantic rebuild`."
    )


def _stored_model_ids(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT model_id FROM semantic_objects ORDER BY model_id"
    ).fetchall()
    return [r[0] for r in rows]


def _warn_model_mismatch(stored: list[str], resolved: str) -> None:
    if not stored:
        return
    if len(stored) == 1 and stored[0] == resolved:
        return
    logger.warning(
        "semantic rebuild: stored model_id %s differs from resolved %s; "
        "wiping all semantic_objects before insert",
        stored,
        resolved,
    )


def run_semantic_rebuild(
    repo_root: Path | str,
    *,
    embedder: Embedder | None = None,
) -> int:
    """Replace all semantic_objects rows. Returns inserted object count."""
    root = resolve_repo_root(repo_root)
    db_path = root / REPOGRAPH_DIR / DB_SQLITE
    migrate(db_path, repo_root=root)

    config = load_config(root)
    enc: Embedder = resolve_embedder(config, embedder=embedder)
    model_id = enc.model_id

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        stored = _stored_model_ids(conn)
        _warn_model_mismatch(stored, model_id)
        objects = collect_semantic_objects(conn, root, config)

    if not objects:
        with contextlib.closing(sqlite3.connect(db_path)) as conn:
            conn.execute("DELETE FROM semantic_objects")
            conn.commit()
        return 0

    texts = [obj.embed_text for obj in objects]
    try:
        vectors = enc.embed_passages(texts)
    except Exception as exc:
        cache_hint = os.environ.get("FASTEMBED_CACHE_PATH", "(default fastembed cache)")
        msg = (
            f"semantic rebuild encode failed for model {model_id!r}: {exc}. "
            f"Try FASTEMBED_CACHE_PATH={cache_hint}"
        )
        raise SemanticRebuildError(msg) from exc

    if len(vectors) != len(objects):
        msg = f"embedder returned {len(vectors)} vectors for {len(objects)} objects"
        raise SemanticRebuildError(msg)

    now = utc_now()
    rows: list[tuple] = []
    for obj, vec in zip(objects, vectors, strict=True):
        dim = int(vec.shape[0])
        source_hash = hashlib.sha256(obj.embed_text.encode("utf-8")).hexdigest()
        rows.append(
            (
                obj.object_type,
                obj.object_key,
                vector_to_blob(vec, dim=dim),
                model_id,
                dim,
                now,
                source_hash,
            )
        )

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        try:
            conn.execute("DELETE FROM semantic_objects")
            conn.executemany(
                """
                INSERT INTO semantic_objects (
                    object_type, object_key, embedding, model_id, dim,
                    embedded_at, source_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise SemanticRebuildError(f"semantic rebuild persist failed: {exc}") from exc

    return len(rows)
