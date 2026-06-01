"""Warn-only staging status for hooks and pre-commit (CHG-05)."""

from __future__ import annotations

import contextlib
import sqlite3
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from repograph.changes.staging import staging_count
from repograph.constants import DB_SQLITE, REPOGRAPH_DIR
from repograph.paths import resolve_repo_root
from repograph.store.migrate import migrate


def run_status(repo_root: Path | str, *, strict: bool = False) -> int:
    """Report staging state. Exit 0 when empty or warn-only; 1 when strict and non-empty."""
    root = resolve_repo_root(repo_root)
    db_path = root / REPOGRAPH_DIR / DB_SQLITE
    migrate(db_path, repo_root=root)

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        count = staging_count(conn)
        if count == 0:
            Console().print("staging empty")
            return 0

        rows = conn.execute(
            """
            SELECT path_norm, op, lines_added, lines_deleted
            FROM changes_staging
            ORDER BY path_norm
            """
        ).fetchall()

    console = Console(file=sys.stderr)
    console.print(
        f"[yellow]WARN[/yellow]: {count} path(s) in change staging "
        "(run [bold]repograph changes prepare[/bold] or finalize)."
    )
    table = Table(title="changes staging")
    table.add_column("path")
    table.add_column("op")
    table.add_column("+/-", justify="right")
    for path_norm, op, added, deleted in rows:
        table.add_row(path_norm, op, f"+{added}/-{deleted}")
    console.print(table)

    if strict:
        return 1
    return 0
