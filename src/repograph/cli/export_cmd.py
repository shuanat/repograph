"""repograph export command — write repograph.md from SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import typer
from rich.console import Console

from repograph.constants import DB_SQLITE, REPOGRAPH_DIR, REPOGRAPH_MD
from repograph.export.summary import export_markdown
from repograph.paths import resolve_repo_root

console = Console()

SCHEMA_MIN_VERSION = 2


def run(
    path: Path | None = None,
    *,
    output: Path | None = None,
) -> None:
    repo_root = resolve_repo_root(path or Path.cwd())
    if not repo_root.is_dir():
        console.print(f"[red]Not a directory:[/red] {repo_root}")
        raise typer.Exit(code=1)

    db_path = repo_root / REPOGRAPH_DIR / DB_SQLITE
    if not db_path.is_file():
        console.print(
            f"[red]Database not found:[/red] {db_path}\n"
            "Run [bold]repograph scan[/bold] first."
        )
        raise typer.Exit(code=1)

    out_path = output or (repo_root / REPOGRAPH_DIR / REPOGRAPH_MD)
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < SCHEMA_MIN_VERSION:
            console.print(
                f"[red]Schema version {version} is too old[/red] "
                f"(need {SCHEMA_MIN_VERSION}+).\n"
                "Run [bold]repograph scan[/bold] to rebuild the database."
            )
            raise typer.Exit(code=1)
        markdown = export_markdown(conn, repo_root)
    finally:
        conn.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.parent / f"{out_path.name}.tmp"
    if tmp_path.exists():
        tmp_path.unlink()
    tmp_path.write_text(markdown, encoding="utf-8")
    tmp_path.replace(out_path)
    console.print(f"Export written: {out_path}")
