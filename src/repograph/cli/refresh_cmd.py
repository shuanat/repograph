"""repograph refresh command — rescan without dropping annotations."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from repograph.config.load import ConfigLoadError
from repograph.paths import resolve_repo_root
from repograph.scan.runner import run_scan

console = Console()


def run(path: Path | None = None) -> None:
    repo_root = resolve_repo_root(path or Path.cwd())
    if not repo_root.is_dir():
        console.print(f"[red]Not a directory:[/red] {repo_root}")
        raise typer.Exit(code=1)

    try:
        result = run_scan(repo_root, preserve_annotations=True)
    except ConfigLoadError as exc:
        console.print(f"[red]Invalid repograph config:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(
        f"Refresh complete: {result.file_count} files, {result.dir_count} dirs "
        f"(errors={result.issue_counts.get('error', 0)}, "
        f"warns={result.issue_counts.get('warn', 0)})"
    )
    if result.has_error:
        raise typer.Exit(code=1)
