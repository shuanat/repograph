"""Draft repograph.yaml from scan results."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

from repograph.config.defaults import SENSITIVE_GLOBS
from repograph.config.model import RepographConfig, SemanticConfig
from repograph.semantic.config import DEFAULT_EMBEDDING_MODEL
from repograph.constants import REPOGRAPH_DIR


def build_draft_config(conn: sqlite3.Connection) -> RepographConfig:
    tops = conn.execute(
        """
        SELECT path_norm FROM entries
        WHERE entry_kind = 'directory' AND depth = 0 AND present = 1
        ORDER BY path_norm
        """
    ).fetchall()
    top_names = [row[0] for row in tops if row[0]]
    domains = {f"{name}/": name for name in top_names if name}
    return RepographConfig(
        domains=domains,
        ignore=[f"{REPOGRAPH_DIR}/**"],
        sensitive_globs=list(SENSITIVE_GLOBS),
        expected_toplevel=top_names,
        semantic=SemanticConfig(embedding_model=DEFAULT_EMBEDDING_MODEL),
    )


def write_draft_yaml(repo_root: Path, config: RepographConfig) -> Path:
    out_dir = repo_root / REPOGRAPH_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "repograph.yaml"
    payload = config.model_dump(mode="json")
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path
