"""Discover git changes and upsert changes_staging."""

from __future__ import annotations

import contextlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from repograph.changes.git_util import is_git_repo, iter_staged_candidates
from repograph.changes.staging import (
    delete_staging_path,
    prune_staging_except,
    staging_count,
    upsert_staging,
)
from repograph.config.load import load_config, pathspec_for_config
from repograph.config.model import RepographConfig
from repograph.constants import DB_SQLITE, REPOGRAPH_DIR
from repograph.paths import is_dot_git, is_under_git_objects, resolve_repo_root, should_skip
from repograph.scan.classify import BINARY_EXTENSIONS, parse_extension
from repograph.scan.walk import load_gitignore_spec
from repograph.store.migrate import migrate


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class IngestResult:
    staged_count: int = 0
    touched_count: int = 0
    warnings: list[str] = field(default_factory=list)


def should_ingest_path(
    path_norm: str,
    name: str,
    config: RepographConfig,
    repo_root: Path,
) -> bool:
    """True when path should be recorded in changes_staging."""
    if should_skip(path_norm, name):
        return False
    if is_dot_git(path_norm) or is_under_git_objects(path_norm):
        return False
    ext = parse_extension(name)
    if ext and ext.lower() in BINARY_EXTENSIONS:
        return False
    ignore_spec, sensitive_spec = pathspec_for_config(config)
    gitignore_spec = load_gitignore_spec(repo_root, config)
    if (
        gitignore_spec.match_file(path_norm)
        or ignore_spec.match_file(path_norm)
        or sensitive_spec.match_file(path_norm)
    ):
        return False
    return True


def run_ingest(repo_root: Path | str) -> IngestResult:
    """Migrate DB, discover git changes, filter, and coalesce into staging."""
    root = resolve_repo_root(repo_root)
    db_path = root / REPOGRAPH_DIR / DB_SQLITE
    migrate(db_path, repo_root=root)

    if not is_git_repo(root):
        with contextlib.closing(sqlite3.connect(db_path)) as conn:
            remaining = staging_count(conn)
        warnings = ["Not a git repository — skipping changes ingest."]
        if remaining:
            warnings.append(
                f"{remaining} path(s) still in staging from prior ingests."
            )
        return IngestResult(
            staged_count=remaining,
            touched_count=0,
            warnings=warnings,
        )

    config = load_config(root)
    now = utc_now()
    candidates = iter_staged_candidates(root)
    current_paths: set[str] = set()
    touched = 0

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        for row in candidates:
            path_norm = row["path_norm"]
            name = path_norm.rsplit("/", 1)[-1] if path_norm else ""
            if not should_ingest_path(path_norm, name, config, root):
                continue
            old_path_norm = row.get("old_path_norm")
            if old_path_norm:
                delete_staging_path(conn, old_path_norm)
            upsert_staging(
                conn,
                path_norm,
                row["op"],
                old_path_norm=old_path_norm,
                lines_added=int(row.get("lines_added") or 0),
                lines_deleted=int(row.get("lines_deleted") or 0),
                git_status=row.get("git_status"),
                now_iso=now,
            )
            current_paths.add(path_norm)
            touched += 1
        prune_staging_except(conn, current_paths)
        conn.commit()
        after = staging_count(conn)

    return IngestResult(staged_count=after, touched_count=touched, warnings=[])
