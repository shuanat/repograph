"""Transactional label batch apply."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from repograph.batches.models import LabelApplyPayload, LabelItem
from repograph.batches.vocab import (
    FIELD_TO_KIND,
    ApplyError,
    ensure_required_vocab_kinds,
    validate_belongs_to,
    validate_enum,
)
from repograph.config.model import RepographConfig

ANNOTATION_FIELDS = (
    "purpose",
    "belongs_to",
    "folder_kind",
    "file_kind",
    "lifecycle",
    "operational_status",
    "content_summary",
    "structure_zone",
    "target_path_norm",
    "target_name",
    "target_belongs_to",
    "action_planned",
    "restructure_wave",
    "priority",
    "effort",
    "action_confidence",
    "canonical_path_norm",
    "duplicate_kind",
    "keep_reason",
    "risk_level",
    "blocks_restructure",
    "runtime_touchpoints",
    "move_group_id",
    "repo_fit",
    "git_policy",
    "applies_to_descendants",
    "notes",
    "restructure_notes",
    "label_status",
)


class ApplyExportError(Exception):
    """Apply persisted but post-commit export failed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _apply_one(
    conn: sqlite3.Connection,
    item: LabelItem,
    *,
    config: RepographConfig,
    model: str,
    prompt_version: str,
    source: str = "llm",
) -> None:
    path_norm = item.path_norm
    row = conn.execute(
        """
        SELECT entry_kind, is_sensitive, present
        FROM entries WHERE path_norm = ?
        """,
        (path_norm,),
    ).fetchone()
    if not row or not row[2]:
        raise ApplyError(f"path not in entries: {path_norm}")
    if row[1]:
        raise ApplyError(f"sensitive path cannot be labeled: {path_norm}")

    entry_kind = row[0]
    data: dict[str, Any] = item.model_dump(exclude_none=True)
    data.pop("path_norm", None)
    data["label_status"] = data.get("label_status") or "labeled"
    data["source"] = source
    data["model"] = model
    data["prompt_version"] = prompt_version
    data["labeled_at"] = utc_now()

    if data.get("applies_to_descendants") is None and entry_kind == "directory":
        data["applies_to_descendants"] = 1

    validate_belongs_to(data["belongs_to"], config, conn)
    for field in ANNOTATION_FIELDS:
        if field in data and field in FIELD_TO_KIND:
            validate_enum(field, data.get(field), conn)

    if entry_kind == "directory" and not data.get("folder_kind"):
        raise ApplyError(f"folder_kind required for directory: {path_norm}")
    if entry_kind == "file" and not data.get("file_kind"):
        raise ApplyError(f"file_kind required for file: {path_norm}")

    insert_cols = ["path_norm"] + [c for c in ANNOTATION_FIELDS if c in data] + [
        "source",
        "model",
        "prompt_version",
        "labeled_at",
    ]
    vals = [path_norm] + [data[c] for c in ANNOTATION_FIELDS if c in data] + [
        data["source"],
        data["model"],
        data["prompt_version"],
        data["labeled_at"],
    ]
    placeholders = ", ".join("?" for _ in insert_cols)
    col_names = ", ".join(insert_cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in insert_cols if c != "path_norm")

    conn.execute(
        f"INSERT INTO annotations ({col_names}) VALUES ({placeholders}) "
        f"ON CONFLICT(path_norm) DO UPDATE SET {updates}",
        vals,
    )


def apply_batch(
    conn: sqlite3.Connection,
    payload: LabelApplyPayload,
    *,
    config: RepographConfig,
    model: str,
    prompt_version: str,
    source: str = "llm",
    dry_run: bool = False,
) -> int:
    ensure_required_vocab_kinds(conn)
    conn.execute("BEGIN")
    try:
        for item in payload.items:
            _apply_one(
                conn,
                item,
                config=config,
                model=model,
                prompt_version=prompt_version,
                source=source,
            )
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
        return len(payload.items)
    except Exception:
        conn.rollback()
        raise
