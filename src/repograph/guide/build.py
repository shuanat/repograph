"""Assemble agent playbook markdown from packaged fragments + CLI introspection."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from repograph.guide.introspect import render_command_appendix

FRAGMENT_ORDER: tuple[str, ...] = (
    "quickstart.md",
    "workflow.md",
    "doctor.md",
    "scan-config.md",
    "label-batches.md",
    "change-journal.md",
    "semantic-layer.md",
    "export.md",
    "exit-codes.md",
    "canonical-store.md",
    "mini-lab.md",
    "anti-patterns.md",
)


def _read_fragment(name: str) -> str:
    return (
        importlib.resources.files("repograph.guide.fragments")
        .joinpath(name)
        .read_text(encoding="utf-8")
        .strip()
    )


def _embedding_model_note(repo_root: Path | None) -> str:
    """Optional repo config line — no sqlite, no file bodies, no .env reads (D-17)."""
    from repograph.config.load import config_path, load_config
    from repograph.semantic.config import DEFAULT_EMBEDDING_MODEL, resolve_embedding_model

    if repo_root is None:
        return ""

    if not config_path(repo_root).is_file():
        return ""

    try:
        config = load_config(repo_root)
        model = resolve_embedding_model(config)
    except (OSError, ValueError, Exception):
        model = DEFAULT_EMBEDDING_MODEL

    return f"\n\n## Repo embedding model\n\nResolved from config/env (no DB opened): `{model}`\n"


def assemble_agent_guide(*, repo_root: Path | None = None) -> str:
    """Return full UTF-8 markdown playbook for agents."""
    parts = [_read_fragment(name) for name in FRAGMENT_ORDER]
    parts.append(render_command_appendix())
    text = "\n\n".join(parts)
    text += _embedding_model_note(repo_root)
    return text.rstrip() + "\n"
