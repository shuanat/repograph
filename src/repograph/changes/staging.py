"""SQLite helpers for changes_staging."""

from __future__ import annotations

import sqlite3


def upsert_staging(
    conn: sqlite3.Connection,
    path_norm: str,
    op: str,
    *,
    old_path_norm: str | None = None,
    lines_added: int = 0,
    lines_deleted: int = 0,
    git_status: str | None = None,
    now_iso: str,
) -> None:
    """Insert or update one staging row, preserving earliest first_seen_at."""
    conn.execute(
        """
        INSERT INTO changes_staging (
            path_norm, op, old_path_norm, first_seen_at, last_seen_at,
            lines_added, lines_deleted, git_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path_norm) DO UPDATE SET
            op = excluded.op,
            old_path_norm = excluded.old_path_norm,
            last_seen_at = excluded.last_seen_at,
            lines_added = excluded.lines_added,
            lines_deleted = excluded.lines_deleted,
            git_status = excluded.git_status
        """,
        (
            path_norm,
            op,
            old_path_norm,
            now_iso,
            now_iso,
            lines_added,
            lines_deleted,
            git_status,
        ),
    )


def staged_path_set(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT path_norm FROM changes_staging").fetchall()
    return {r[0] for r in rows}


def delete_staging_path(conn: sqlite3.Connection, path_norm: str) -> None:
    conn.execute("DELETE FROM changes_staging WHERE path_norm = ?", (path_norm,))


def prune_staging_except(conn: sqlite3.Connection, keep: set[str]) -> None:
    """Remove staging rows not present in the current git candidate set."""
    for path_norm in staged_path_set(conn) - keep:
        delete_staging_path(conn, path_norm)


def staging_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM changes_staging").fetchone()
    return int(row[0]) if row else 0
