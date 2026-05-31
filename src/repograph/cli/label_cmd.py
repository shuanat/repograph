"""repograph label — vocab, export, queue, apply-batch."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import sys
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from repograph.batches.apply import ApplyExportError, apply_batch
from repograph.semantic.rebuild import (
    SemanticRebuildError,
    apply_post_commit_message,
    run_semantic_rebuild,
)
from repograph.batches.export import build_export
from repograph.batches.models import LabelApplyPayload, VocabApplyPayload
from repograph.batches.queue import QueueFilters, iter_queue_paths
from repograph.batches.vocab import merge_vocab
from repograph.constants import DB_SQLITE, REPOGRAPH_DIR
from repograph.paths import resolve_repo_root
from repograph.store.migrate import migrate

LABEL_SCHEMA_MIN_VERSION = 4

label_app = typer.Typer(
    help="Export and apply LLM annotation batches (see docs/label-batch.md).",
    no_args_is_help=True,
)
console = Console()


def _open_db(repo_root: Path) -> sqlite3.Connection:
    db_path = repo_root / REPOGRAPH_DIR / DB_SQLITE
    migrate(db_path, repo_root=repo_root)
    conn = sqlite3.connect(db_path)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < LABEL_SCHEMA_MIN_VERSION:
        console.print(
            f"[red]Database schema v{version} after migrate — expected "
            f"v{LABEL_SCHEMA_MIN_VERSION}. Database may be corrupt; remove "
            f".repograph/db.sqlite and run repograph scan.[/red]"
        )
        raise typer.Exit(code=1)
    conn.row_factory = sqlite3.Row
    return conn


def _read_json(file: Path | None) -> object:
    if file is not None:
        return json.loads(file.read_text(encoding="utf-8"))
    if not sys.stdin.isatty():
        return json.loads(sys.stdin.read())
    console.print("[red]Provide JSON via stdin or --file/-f.[/red]")
    raise typer.Exit(code=2)


def _filters_from_options(
    *,
    limit: int,
    depth: int | None,
    depth_max: int | None,
    kind: str | None,
    domain: str | None,
    has_issues: bool,
    full_queue: bool,
) -> QueueFilters:
    return QueueFilters(
        limit=limit,
        depth=depth,
        depth_max=depth_max,
        kind=kind,
        domain=domain,
        has_issues=has_issues,
        full_queue=full_queue,
    )


@label_app.command("vocab-apply")
def label_vocab_apply(
    path: Path | None = typer.Argument(None, help="Repository root."),
    file: Path | None = typer.Option(None, "--file", "-f", help="JSON vocab file."),
) -> None:
    """Merge vocab declarations from JSON into SQLite."""
    repo_root = resolve_repo_root(path or Path.cwd())
    raw = _read_json(file)
    try:
        payload = VocabApplyPayload.model_validate(raw)
    except ValidationError as exc:
        console.print(f"[red]Invalid vocab JSON:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    with contextlib.closing(_open_db(repo_root)) as conn:
        count = merge_vocab(conn, payload.entries)
        conn.commit()
    typer.echo(f"Merged {count} vocab row(s).")


@label_app.command("vocab-list")
def label_vocab_list(
    path: Path | None = typer.Argument(None, help="Repository root."),
    as_json: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """List all vocab rows (for agents when export cap applies)."""
    repo_root = resolve_repo_root(path or Path.cwd())
    with contextlib.closing(_open_db(repo_root)) as conn:
        rows = conn.execute(
            "SELECT kind, code, label_ru, sort_order FROM vocab ORDER BY kind, sort_order, code"
        ).fetchall()
    data = [
        {"kind": r[0], "code": r[1], "label": r[2], "sort_order": r[3]}
        for r in rows
    ]
    if as_json:
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return
    table = Table("kind", "code", "label", "sort")
    for row in data:
        table.add_row(row["kind"], row["code"], row["label"] or "", str(row["sort"]))
    console.print(table)


@label_app.command("export")
def label_export(
    path: Path | None = typer.Argument(None, help="Repository root."),
    limit: int = typer.Option(25, "--limit", min=1, help="Max items in batch."),
    depth: int | None = typer.Option(None, "--depth"),
    depth_max: int | None = typer.Option(None, "--depth-max"),
    kind: str | None = typer.Option(None, "--kind"),
    domain: str | None = typer.Option(None, "--domain"),
    has_issues: bool = typer.Option(False, "--has-issues"),
    full_queue: bool = typer.Option(
        False, "--full-queue", help="Use v_label_queue instead of actionable."
    ),
    with_preview: bool = typer.Option(False, "--with-preview"),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Export actionable label batch JSON with project_vocab snapshot."""
    repo_root = resolve_repo_root(path or Path.cwd())
    filters = _filters_from_options(
        limit=limit,
        depth=depth,
        depth_max=depth_max,
        kind=kind,
        domain=domain,
        has_issues=has_issues,
        full_queue=full_queue,
    )
    with contextlib.closing(_open_db(repo_root)) as conn:
        envelope = build_export(
            conn, repo_root, filters, with_preview=with_preview
        )
    text = json.dumps(
        envelope.model_dump(by_alias=True),
        indent=2,
        ensure_ascii=False,
    )
    if output:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"Wrote {len(envelope.items)} item(s) to {output}")
    else:
        typer.echo(text)


@label_app.command("queue")
def label_queue(
    path: Path | None = typer.Argument(None, help="Repository root."),
    limit: int = typer.Option(25, "--limit", min=1),
    depth: int | None = typer.Option(None, "--depth"),
    depth_max: int | None = typer.Option(None, "--depth-max"),
    kind: str | None = typer.Option(None, "--kind"),
    domain: str | None = typer.Option(None, "--domain"),
    has_issues: bool = typer.Option(False, "--has-issues"),
    full_queue: bool = typer.Option(False, "--full-queue"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List label queue paths (same filters as export)."""
    repo_root = resolve_repo_root(path or Path.cwd())
    filters = _filters_from_options(
        limit=limit,
        depth=depth,
        depth_max=depth_max,
        kind=kind,
        domain=domain,
        has_issues=has_issues,
        full_queue=full_queue,
    )
    view = filters.view_name
    with contextlib.closing(_open_db(repo_root)) as conn:
        paths = iter_queue_paths(conn, filters)
        if as_json:
            rows = []
            for pn in paths:
                row = conn.execute(
                    f"""
                    SELECT path_norm, entry_kind, depth, domain_auto,
                           role_auto, label_status
                    FROM {view} WHERE path_norm = ?
                    """,
                    (pn,),
                ).fetchone()
                if row:
                    rows.append(dict(row))
            typer.echo(json.dumps(rows, indent=2))
            return

        table = Table("depth", "kind", "path", "domain", "status")
        for pn in paths:
            row = conn.execute(
                f"""
                SELECT depth, entry_kind, path_norm, domain_auto, label_status
                FROM {view} WHERE path_norm = ?
                """,
                (pn,),
            ).fetchone()
            if row:
                table.add_row(
                    str(row[0]),
                    str(row[1])[:3],
                    row[2] or ".",
                    row[3] or "",
                    row[4] or "",
                )
        console.print(table)


@label_app.command("apply-batch")
def label_apply_batch(
    path: Path | None = typer.Argument(None, help="Repository root."),
    file: Path | None = typer.Option(None, "--file", "-f"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    model: str = typer.Option("unknown", "--model"),
    prompt_version: str = typer.Option("1", "--prompt-version"),
    export_after: bool = typer.Option(
        False, "--export", help="Run repograph export after successful apply."
    ),
    no_semantic_rebuild: bool = typer.Option(
        False,
        "--no-semantic-rebuild",
        help="Skip semantic rebuild after successful apply.",
    ),
) -> None:
    """Validate and apply a label batch in one transaction."""
    from repograph.batches.vocab import ApplyError
    from repograph.config.load import load_config

    repo_root = resolve_repo_root(path or Path.cwd())
    raw = _read_json(file)
    try:
        payload = LabelApplyPayload.model_validate(raw)
    except ValidationError as exc:
        console.print(f"[red]Invalid batch JSON:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    config = load_config(repo_root)
    with contextlib.closing(_open_db(repo_root)) as conn:
        try:
            count = apply_batch(
                conn,
                payload,
                config=config,
                model=model,
                prompt_version=prompt_version,
                dry_run=dry_run,
            )
        except ApplyError as exc:
            console.print(f"[red]Apply failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    if dry_run:
        typer.echo(f"Dry-run OK: {count} item(s) validated.")
        return

    typer.echo(f"Applied {count} annotation(s).")

    if export_after:
        from repograph.cli import export_cmd

        try:
            export_cmd.run(repo_root)
        except ApplyExportError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except Exception as exc:
            typer.echo(
                "Apply persisted but export failed. Re-run `repograph export`.",
                err=True,
            )
            raise typer.Exit(code=1) from exc

    if not no_semantic_rebuild:
        try:
            run_semantic_rebuild(repo_root)
        except SemanticRebuildError as exc:
            typer.echo(apply_post_commit_message(), err=True)
            if str(exc):
                typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc


@label_app.command("print-prompt")
def label_print_prompt() -> None:
    """Print packaged label-entry prompt for external LLMs."""
    import importlib.resources

    text = (
        importlib.resources.files("repograph.prompts")
        .joinpath("label-entry.md")
        .read_text(encoding="utf-8")
    )
    typer.echo(text)
