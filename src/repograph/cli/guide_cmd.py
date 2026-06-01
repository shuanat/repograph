"""repograph agent-guide — print agent playbook markdown."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from repograph.guide.build import assemble_agent_guide
from repograph.paths import resolve_repo_root


def run(
    path: Path | None = None,
    *,
    output: Path | None = None,
) -> None:
    repo_root: Path | None = None
    if path is not None:
        repo_root = resolve_repo_root(path)
    text = assemble_agent_guide(repo_root=repo_root)
    if output is not None:
        out_path = output.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.parent / f"{out_path.name}.tmp"
        if tmp_path.exists():
            tmp_path.unlink()
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, out_path)
    typer.echo(text, nl=False)
