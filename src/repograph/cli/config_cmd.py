"""repograph config init | apply | validate."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import typer
import yaml
from pathspec import PathSpec
from rich.console import Console

from repograph.config.draft import build_draft_config, write_draft_yaml
from repograph.config.load import config_path, load_config
from repograph.batches.vocab import merge_vocab
from repograph.config.model import RepographConfig
from repograph.constants import REPOGRAPH_DIR
from repograph.paths import resolve_repo_root
from repograph.store.migrate import migrate

console = Console()
config_app = typer.Typer(help="Manage repograph.yaml")


def _validate_file(path: Path) -> RepographConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        msg = "repograph.yaml must be a mapping"
        raise ValueError(msg)
    config = RepographConfig.model_validate(raw)
    PathSpec.from_lines("gitwildmatch", list(config.ignore))
    PathSpec.from_lines("gitwildmatch", list(config.sensitive_globs))
    return config


@config_app.command("init")
def config_init(
    path: Path | None = typer.Argument(None, help="Repository root."),
) -> None:
    """Write draft repograph.yaml from scan heuristics."""
    repo_root = resolve_repo_root(path or Path.cwd())
    db = repo_root / REPOGRAPH_DIR / "db.sqlite"
    if not db.is_file():
        console.print("[red]No scan database — run repograph scan first.[/red]")
        raise typer.Exit(code=1)
    migrate(db, repo_root=repo_root)
    conn = sqlite3.connect(db)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE present = 1"
        ).fetchone()[0]
        if count == 0:
            console.print("[red]Scan database has no entries — run repograph scan first.[/red]")
            raise typer.Exit(code=1)
        draft = build_draft_config(conn)
    finally:
        conn.close()
    out = write_draft_yaml(repo_root, draft)
    console.print(f"Draft config written: {out}")


@config_app.command("apply")
def config_apply(
    path: Path | None = typer.Argument(None, help="Repository root."),
    file: Path | None = typer.Option(
        None,
        "--file",
        "-f",
        help="Yaml file to apply (default: .repograph/repograph.yaml).",
    ),
) -> None:
    """Validate and atomically write repograph.yaml."""
    repo_root = resolve_repo_root(path or Path.cwd())
    source = file or config_path(repo_root)
    if not source.is_file():
        console.print(f"[red]Config file not found:[/red] {source}")
        raise typer.Exit(code=1)
    try:
        config = _validate_file(source)
    except (ValueError, yaml.YAMLError) as exc:
        console.print(f"[red]Invalid config:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    dest = config_path(repo_root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=dest.parent, prefix="repograph.yaml.", suffix=".tmp"
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        tmp.replace(dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise

    if config.vocab:
        db = repo_root / REPOGRAPH_DIR / DB_SQLITE
        migrate(db, repo_root=repo_root)
        conn = sqlite3.connect(db)
        try:
            merge_vocab(conn, config.vocab)
            conn.commit()
        finally:
            conn.close()

    console.print(f"Applied config: {dest}")


@config_app.command("validate")
def config_validate(
    path: Path | None = typer.Argument(None, help="Repository root."),
    file: Path | None = typer.Option(None, "--file", "-f"),
) -> None:
    """Validate repograph.yaml without writing."""
    repo_root = resolve_repo_root(path or Path.cwd())
    source = file or config_path(repo_root)
    if not source.is_file():
        console.print(f"[red]Config file not found:[/red] {source}")
        raise typer.Exit(code=1)
    try:
        _validate_file(source)
    except (ValueError, yaml.YAMLError) as exc:
        console.print(f"[red]Invalid config:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print("[green]Config valid.[/green]")
