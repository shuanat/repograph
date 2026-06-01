"""repograph semantic — embedding rebuild and query."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from repograph.config.load import load_config
from repograph.constants import DB_SQLITE, REPOGRAPH_DIR
from repograph.paths import resolve_repo_root
from repograph.semantic.config import resolve_embedding_model
from repograph.semantic.query import run_semantic_query
from repograph.semantic.rebuild import SemanticRebuildError, run_semantic_rebuild
from repograph.store.migrate import migrate

semantic_app = typer.Typer(
    help="Local semantic embeddings (FastEmbed / ONNX).",
    no_args_is_help=True,
)
_err = Console(stderr=True)
_out = Console()


def _semantic_object_count(repo_root: Path) -> int:
    db_path = repo_root / REPOGRAPH_DIR / DB_SQLITE
    migrate(db_path, repo_root=repo_root)
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM semantic_objects").fetchone()
        return int(row[0]) if row else 0


def _warn_model_mismatch(repo_root: Path) -> None:
    import sqlite3

    config = load_config(repo_root)
    resolved = resolve_embedding_model(config)
    db_path = repo_root / REPOGRAPH_DIR / DB_SQLITE
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT model_id FROM semantic_objects"
        ).fetchall()
    stored = {r[0] for r in rows}
    if stored and stored != {resolved}:
        _err.print(
            f"[yellow]Warning: stored embeddings use model_id {sorted(stored)!r} "
            f"but config resolves {resolved!r}; run semantic rebuild.[/yellow]"
        )


@semantic_app.command("rebuild")
def rebuild_command(
    path: Path | None = typer.Argument(
        None,
        help="Repository root (default: current directory).",
    ),
) -> None:
    """Rebuild semantic_objects embeddings for this repository."""
    root = resolve_repo_root(path or Path.cwd())
    try:
        count = run_semantic_rebuild(root)
    except SemanticRebuildError as exc:
        _err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    _out.print(f"[green]Semantic rebuild complete: {count} object(s) written.[/green]")


@semantic_app.command("query")
def query_command(
    query_text: str = typer.Argument(..., help="Natural-language search query."),
    path: Path | None = typer.Argument(
        None,
        help="Repository root (default: current directory).",
    ),
    limit: int = typer.Option(10, "--limit", min=1, help="Maximum hits to return."),
    table: bool = typer.Option(
        False,
        "--table",
        help="Human-readable table instead of JSON on stdout.",
    ),
) -> None:
    """Query semantic_objects by cosine similarity (JSON on stdout by default)."""
    root = resolve_repo_root(path or Path.cwd())
    if _semantic_object_count(root) == 0:
        _err.print(
            "[red]No semantic embeddings found. Run "
            "`repograph semantic rebuild` first.[/red]"
        )
        raise typer.Exit(code=1)

    _warn_model_mismatch(root)
    try:
        payload = run_semantic_query(root, query_text, limit=limit)
    except SemanticRebuildError as exc:
        _err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if table:
        rows = payload.get("results") or []
        if not rows:
            _err.print("[yellow]No matching semantic objects.[/yellow]")
            raise typer.Exit(code=1)
        rich_table = Table(title=f"Semantic query ({payload.get('model_id', '')})")
        rich_table.add_column("object_type")
        rich_table.add_column("score", justify="right")
        rich_table.add_column("path")
        rich_table.add_column("snippet")
        for hit in rows:
            rich_table.add_row(
                str(hit.get("object_type", "")),
                f"{float(hit.get('score', 0)):.4f}",
                str(hit.get("path_norm") or ""),
                str(hit.get("snippet", ""))[:80],
            )
        _out.print(rich_table)
        return

    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
