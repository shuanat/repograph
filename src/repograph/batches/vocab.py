"""SQLite vocab merge and DB-backed enum validation."""

from __future__ import annotations

import sqlite3

from repograph.batches.models import VocabRow
from repograph.config.model import RepographConfig

FIELD_TO_KIND: dict[str, str] = {
    "belongs_to": "belongs_to",
    "folder_kind": "folder_kind",
    "file_kind": "file_kind",
    "lifecycle": "lifecycle",
    "operational_status": "operational_status",
    "structure_zone": "structure_zone",
    "action_planned": "action_planned",
    "restructure_wave": "restructure_wave",
    "priority": "priority",
    "effort": "effort",
    "action_confidence": "action_confidence",
    "duplicate_kind": "duplicate_kind",
    "risk_level": "risk_level",
    "repo_fit": "repo_fit",
    "git_policy": "git_policy",
    "label_status": "label_status",
    "target_belongs_to": "belongs_to",
}

REQUIRED_VOCAB_KINDS = (
    "belongs_to",
    "folder_kind",
    "file_kind",
    "lifecycle",
    "label_status",
)


class ApplyError(Exception):
    """Batch apply validation failure."""


def codes_for_kind(conn: sqlite3.Connection, kind: str) -> set[str]:
    rows = conn.execute(
        "SELECT code FROM vocab WHERE kind = ?", (kind,)
    ).fetchall()
    return {r[0] for r in rows}


def merge_vocab(conn: sqlite3.Connection, rows: list[VocabRow]) -> int:
    count = 0
    for row in rows:
        label = row.label
        conn.execute(
            """
            INSERT INTO vocab (kind, code, label_ru, sort_order)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(kind, code) DO UPDATE SET
                label_ru = excluded.label_ru,
                sort_order = excluded.sort_order
            """,
            (row.kind, row.code, label, row.sort_order),
        )
        count += 1
    return count


def validate_enum(field: str, value: str | None, conn: sqlite3.Connection) -> None:
    if value is None:
        return
    kind = FIELD_TO_KIND.get(field)
    if not kind:
        return
    allowed = codes_for_kind(conn, kind)
    if value not in allowed:
        raise ApplyError(f"Invalid {field}={value!r}, not in vocab (kind={kind})")


def validate_belongs_to(
    value: str,
    config: RepographConfig,
    conn: sqlite3.Connection,
) -> None:
    if value in config.domains:
        return
    if value in codes_for_kind(conn, "belongs_to"):
        return
    raise ApplyError(
        f"belongs_to={value!r} not in repograph.yaml domains or vocab; "
        "run label vocab-apply or add domain"
    )


def ensure_required_vocab_kinds(conn: sqlite3.Connection) -> None:
    missing = [k for k in REQUIRED_VOCAB_KINDS if not codes_for_kind(conn, k)]
    if missing:
        raise ApplyError(
            f"Missing required vocab kinds: {', '.join(missing)}; "
            "run label vocab-apply or config apply with vocab section"
        )
