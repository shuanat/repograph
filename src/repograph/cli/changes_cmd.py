"""repograph changes — change journal CLI."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import sys
from pathlib import Path

import typer
from pydantic import ValidationError

from repograph.changes.finalize import FinalizeError, FinalizeExportError, run_finalize
from repograph.semantic.rebuild import (
    SemanticRebuildError,
    finalize_post_commit_message,
    run_semantic_rebuild,
)
from repograph.changes.ingest import run_ingest
from repograph.changes.models import FinalizePayload
from repograph.changes.prepare import render_prepare_brief
from repograph.changes.query import list_events, show_event
from repograph.changes.status import run_status
from repograph.constants import DB_SQLITE, REPOGRAPH_DIR
from repograph.paths import normalize_path, resolve_repo_root
from repograph.store.migrate import migrate

changes_app = typer.Typer(
    help="Record, prepare, and finalize repository change journal entries.",
    no_args_is_help=True,
)


def _open_db(repo_root: Path) -> sqlite3.Connection:
    db_path = repo_root / REPOGRAPH_DIR / DB_SQLITE
    migrate(db_path, repo_root=repo_root)
    return sqlite3.connect(db_path)


@changes_app.command("ingest")
def changes_ingest(
    path: Path | None = typer.Argument(None, help="Repository root."),
) -> None:
    """Discover git changes and upsert changes_staging rows."""
    repo_root = resolve_repo_root(path or Path.cwd())
    result = run_ingest(repo_root)
    for warning in result.warnings:
        typer.echo(warning, err=True)
    if result.touched_count:
        typer.echo(
            f"Ingested {result.touched_count} path(s); "
            f"staging table: {result.staged_count} path(s)."
        )
    else:
        typer.echo(f"Staging table: {result.staged_count} path(s).")


@changes_app.command("prepare")
def changes_prepare(
    path: Path | None = typer.Argument(None, help="Repository root."),
) -> None:
    """Print a markdown brief of staged changes for the agent."""
    repo_root = resolve_repo_root(path or Path.cwd())
    with contextlib.closing(_open_db(repo_root)) as conn:
        typer.echo(render_prepare_brief(conn, repo_root))


@changes_app.command("finalize")
def changes_finalize(
    path: Path | None = typer.Argument(None, help="Repository root."),
    file: Path | None = typer.Option(
        None,
        "--file",
        "-f",
        help="JSON file (default: stdin).",
    ),
    export: bool = typer.Option(
        False,
        "--export",
        help="Run repograph export after successful finalize.",
    ),
    no_semantic_rebuild: bool = typer.Option(
        False,
        "--no-semantic-rebuild",
        help="Skip semantic rebuild after successful finalize.",
    ),
) -> None:
    """Validate finalize JSON and persist change_events."""
    repo_root = resolve_repo_root(path or Path.cwd())
    if file is not None:
        raw = file.read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    try:
        data = json.loads(raw)
        payload = FinalizePayload.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        typer.echo(f"Invalid finalize JSON: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    try:
        run_finalize(repo_root, payload, export=export)
    except FinalizeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except FinalizeExportError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Finalized {len(payload.events)} event(s).")
    if not no_semantic_rebuild:
        try:
            run_semantic_rebuild(repo_root)
        except SemanticRebuildError as exc:
            typer.echo(finalize_post_commit_message(), err=True)
            if str(exc):
                typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc


@changes_app.command("status")
def changes_status(
    path: Path | None = typer.Argument(None, help="Repository root."),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit 1 when staging is non-empty (mirror doctor --strict).",
    ),
) -> None:
    """Report staging state (warn when non-empty; exit 0 unless --strict)."""
    repo_root = resolve_repo_root(path or Path.cwd())
    code = run_status(repo_root, strict=strict)
    if code:
        raise typer.Exit(code=code)


@changes_app.command("list")
def changes_list(
    path: Path | None = typer.Argument(None, help="Repository root."),
    since: str | None = typer.Option(None, help="ISO timestamp lower bound."),
    path_filter: str | None = typer.Option(
        None,
        "--path",
        help="Filter events touching this path_norm.",
    ),
    limit: int = typer.Option(50, "--limit", min=1, max=500),
) -> None:
    """List finalized change events."""
    repo_root = resolve_repo_root(path or Path.cwd())
    path_norm = normalize_path(path_filter) if path_filter else None
    with contextlib.closing(_open_db(repo_root)) as conn:
        rows = list_events(conn, since=since, path=path_norm, limit=limit)
    if not rows:
        typer.echo("No change events found.")
        return
    for event_id, finalized_at, title, path_count in rows:
        date = finalized_at[:10] if len(finalized_at) >= 10 else finalized_at
        typer.echo(f"{event_id}\t{date}\t{title}\t{path_count} path(s)")


@changes_app.command("show")
def changes_show(
    event_id: int = typer.Argument(..., help="change_events.id to display."),
    path: Path | None = typer.Option(None, help="Repository root."),
) -> None:
    """Show one change event as markdown on stdout."""
    repo_root = resolve_repo_root(path or Path.cwd())
    with contextlib.closing(_open_db(repo_root)) as conn:
        markdown = show_event(conn, event_id)
    if markdown is None:
        typer.echo(f"Event {event_id} not found.", err=True)
        raise typer.Exit(code=1)
    typer.echo(markdown)
