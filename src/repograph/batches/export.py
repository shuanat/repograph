"""Build label export JSON envelope."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repograph.batches.models import (
    ExportItem,
    LabelExportEnvelope,
    ParentEffective,
    VocabRow,
)
from repograph.batches.queue import QueueFilters, iter_queue_paths
from repograph.paths import parent_path

PROJECT_VOCAB_CAP = 200
PREVIEW_MAX_BYTES = 65536
PREVIEW_MAX_CHARS = 4000


def _preview_file(scan_root: Path, path_norm: str) -> Path | None:
    """Resolved file path for preview, or None if outside repo or missing."""
    root = scan_root.resolve()
    try:
        fp = (root / Path(path_norm)).resolve()
        fp.relative_to(root)
    except ValueError:
        return None
    if not fp.is_file():
        return None
    return fp

VOCAB_KINDS_FOR_EXPORT = tuple(
    {
        "belongs_to",
        "folder_kind",
        "file_kind",
        "lifecycle",
        "operational_status",
        "structure_zone",
        "action_planned",
        "restructure_wave",
        "priority",
        "effort",
        "action_confidence",
        "duplicate_kind",
        "risk_level",
        "repo_fit",
        "git_policy",
        "label_status",
    }
)


def child_sample(
    conn: sqlite3.Connection,
    path_norm: str,
    limit: int = 12,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT name, entry_kind FROM entries
        WHERE present = 1 AND parent_path_norm = ?
        ORDER BY entry_kind DESC, name
        LIMIT ?
        """,
        (path_norm if path_norm else None, limit),
    ).fetchall()
    if not rows and path_norm == "":
        rows = conn.execute(
            """
            SELECT name, entry_kind FROM entries
            WHERE present = 1 AND parent_path_norm IS NULL AND path_norm != ''
            ORDER BY entry_kind DESC, name
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out: list[str] = []
    for name, entry_kind in rows:
        suffix = "/" if entry_kind == "directory" else ""
        out.append(name + suffix)
    return out


def issues_for_path(conn: sqlite3.Connection, path_norm: str) -> list[str]:
    rows = conn.execute(
        "SELECT code, message FROM issues WHERE path_norm = ?",
        (path_norm,),
    ).fetchall()
    return [f"{code}: {message}" for code, message in rows]


def parent_effective(
    conn: sqlite3.Connection,
    path_norm: str,
) -> ParentEffective | None:
    pp = parent_path(path_norm)
    if not pp:
        return None
    row = conn.execute(
        """
        SELECT effective_purpose, effective_belongs_to, effective_lifecycle,
               inherited_from
        FROM v_effective WHERE path_norm = ?
        """,
        (pp,),
    ).fetchone()
    if not row or not row[0]:
        return None
    return ParentEffective(
        purpose=row[0],
        belongs_to=row[1],
        lifecycle=row[2],
        inherited_from=row[3],
    )


def _load_project_vocab(conn: sqlite3.Connection) -> list[VocabRow]:
    placeholders = ",".join("?" for _ in VOCAB_KINDS_FOR_EXPORT)
    rows = conn.execute(
        f"""
        SELECT kind, code, label_ru, sort_order FROM vocab
        WHERE kind IN ({placeholders})
        ORDER BY kind, sort_order, code
        LIMIT ?
        """,
        (*VOCAB_KINDS_FOR_EXPORT, PROJECT_VOCAB_CAP),
    ).fetchall()
    return [
        VocabRow(kind=r[0], code=r[1], label=r[2], sort_order=r[3] or 0)
        for r in rows
    ]


def build_export(
    conn: sqlite3.Connection,
    repo_root: Path,
    filters: QueueFilters,
    *,
    with_preview: bool = False,
) -> LabelExportEnvelope:
    conn.row_factory = sqlite3.Row
    paths = iter_queue_paths(conn, filters)
    items: list[ExportItem] = []

    repo_row = conn.execute(
        "SELECT repo_root FROM scan_meta WHERE id = 1"
    ).fetchone()
    scan_root = Path(repo_row["repo_root"]) if repo_row and repo_row["repo_root"] else repo_root

    for path_norm in paths:
        entry = conn.execute(
            "SELECT * FROM entries WHERE path_norm = ?", (path_norm,)
        ).fetchone()
        if not entry or entry["is_sensitive"]:
            continue

        item = ExportItem(
            path_norm=path_norm,
            entry_kind=entry["entry_kind"],
            depth=entry["depth"],
            name=entry["name"],
            domain_auto=entry["domain_auto"],
            role_auto=entry["role_auto"],
            legacy_auto=entry["legacy_auto"],
            extension=entry["extension"],
            size_bytes=entry["size_bytes"],
            child_sample=child_sample(conn, path_norm),
            issues=issues_for_path(conn, path_norm),
            parent_effective=parent_effective(conn, path_norm),
        )

        if (
            with_preview
            and entry["entry_kind"] == "file"
            and (entry["size_bytes"] or 0) <= PREVIEW_MAX_BYTES
        ):
            fp = _preview_file(scan_root, path_norm)
            if fp is not None:
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                    item.content_preview = text[:PREVIEW_MAX_CHARS]
                except OSError:
                    pass

        items.append(item)

    return LabelExportEnvelope(
        project_vocab=_load_project_vocab(conn),
        items=items,
    )
