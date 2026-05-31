"""Persist issues to SQLite."""

from __future__ import annotations

import sqlite3

IssueRow = tuple[str, str, str | None, str]


def post_issues(conn: sqlite3.Connection, rows: list[IssueRow]) -> None:
    conn.execute("DELETE FROM issues")
    if rows:
        conn.executemany(
            "INSERT INTO issues (severity, code, path_norm, message) VALUES (?, ?, ?, ?)",
            rows,
        )


_PATH_LOCAL_CODES = ("BROKEN_MD_LINK", "SENSITIVE_PATH")


def replace_issues_for_paths(
    conn: sqlite3.Connection,
    paths: set[str],
    rows: list[IssueRow],
) -> None:
    """Replace path-local issue rows for touched paths only (HLT-03)."""
    if not paths:
        return
    placeholders = ",".join("?" * len(paths))
    code_placeholders = ",".join("?" * len(_PATH_LOCAL_CODES))
    conn.execute(
        f"""
        DELETE FROM issues
        WHERE path_norm IN ({placeholders})
          AND code IN ({code_placeholders})
        """,
        [*paths, *_PATH_LOCAL_CODES],
    )
    if rows:
        conn.executemany(
            "INSERT INTO issues (severity, code, path_norm, message) VALUES (?, ?, ?, ?)",
            rows,
        )
