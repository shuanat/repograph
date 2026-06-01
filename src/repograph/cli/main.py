"""Typer application entry."""

from __future__ import annotations

from pathlib import Path

import typer

from repograph.cli import doctor, export_cmd, guide_cmd, refresh_cmd, scan
from repograph.cli.changes_cmd import changes_app
from repograph.cli.config_cmd import config_app
from repograph.cli.label_cmd import label_app
from repograph.cli.semantic_cmd import semantic_app

app = typer.Typer(no_args_is_help=True)

doctor_app = typer.Typer(help="Verify Python, SQLite, git, and ONNX runtime readiness.")
app.add_typer(doctor_app, name="doctor")

app.add_typer(config_app, name="config")
app.add_typer(changes_app, name="changes")
app.add_typer(label_app, name="label")
app.add_typer(semantic_app, name="semantic")


@app.command("scan")
def scan_command(
    path: Path | None = typer.Argument(
        None,
        help="Repository root (default: current directory).",
    ),
) -> None:
    """Scan repository metadata into .repograph/db.sqlite (first run or cold DB)."""
    scan.run(path)


@app.command("export")
def export_command(
    path: Path | None = typer.Argument(
        None,
        help="Repository root (default: current directory).",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Markdown output path (default: .repograph/repograph.md).",
    ),
) -> None:
    """Regenerate repograph.md from .repograph/db.sqlite."""
    export_cmd.run(path, output=output)


@app.command("agent-guide")
def agent_guide_command(
    path: Path | None = typer.Argument(
        None,
        help="Repository root for optional embedding-model line (default: omit).",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Write playbook markdown to PATH instead of stdout only.",
    ),
) -> None:
    """Print agent playbook markdown to stdout."""
    guide_cmd.run(path, output=output)


@app.command("refresh")
def refresh_command(
    path: Path | None = typer.Argument(
        None,
        help="Repository root (default: current directory).",
    ),
) -> None:
    """Rescan repository metadata without dropping annotations in db.sqlite."""
    refresh_cmd.run(path)


@doctor_app.callback(invoke_without_command=True)
def doctor_command(
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat WARN as failure.",
    ),
) -> None:
    """Run environment and dependency health checks."""
    doctor.run(strict=strict)
