"""Incremental path-local issue recheck after change finalize (HLT-03)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repograph.config.load import pathspec_for_config
from repograph.config.model import RepographConfig
from repograph.issues.detectors import broken_md_links_for_file, sensitive_path_issues
from repograph.issues.post import IssueRow, replace_issues_for_paths


def _sensitive_rows_for_path(path_norm: str, config: RepographConfig) -> list[IssueRow]:
    _, sensitive_spec = pathspec_for_config(config)
    if not sensitive_spec.match_file(path_norm):
        return []
    return sensitive_path_issues(
        [{"path_norm": path_norm, "is_sensitive": True}],
    )


def recheck_issues_for_paths(
    conn: sqlite3.Connection,
    repo_root: Path,
    path_norms: set[str],
    config: RepographConfig,
) -> None:
    """Re-run BROKEN_MD_LINK and SENSITIVE_PATH for touched paths only (D-23–D-24)."""
    if not path_norms:
        return
    rows: list[IssueRow] = []
    for path_norm in sorted(path_norms):
        rows.extend(broken_md_links_for_file(repo_root, path_norm))
        rows.extend(_sensitive_rows_for_path(path_norm, config))
    replace_issues_for_paths(conn, path_norms, rows)
