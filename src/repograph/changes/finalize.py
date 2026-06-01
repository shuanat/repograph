"""Persist finalized change events from agent JSON."""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from repograph.changes.git_util import git_branch, git_head
from repograph.changes.ingest import utc_now
from repograph.changes.models import FinalizePayload
from repograph.changes.staging import staged_path_set
from repograph.config.load import load_config
from repograph.constants import DB_SQLITE, REPOGRAPH_DIR
from repograph.issues.incremental import recheck_issues_for_paths
from repograph.paths import resolve_repo_root
from repograph.store.migrate import migrate


class FinalizeError(Exception):
    """Coverage or validation failure; staging must remain unchanged."""


class FinalizeExportError(Exception):
    """Finalize persisted but post-commit export failed."""


def run_finalize(
    repo_root: Path | str,
    payload: FinalizePayload,
    *,
    export: bool = False,
) -> set[str]:
    """Validate coverage, persist events/narratives, clear staging (D-13, D-14).

    Returns the set of path_norm values written. Raises FinalizeError on coverage mismatch.
    """
    root = resolve_repo_root(repo_root)
    db_path = root / REPOGRAPH_DIR / DB_SQLITE
    migrate(db_path, repo_root=root)

    covered: set[str] = set()
    for event in payload.events:
        covered.update(event.paths)

    config = load_config(root)

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        staged = staged_path_set(conn)
        if covered != staged:
            raise FinalizeError(
                f"finalize coverage mismatch: staged={len(staged)} paths, "
                f"claimed={len(covered)} paths"
            )

        now = utc_now()
        head = git_head(root)
        branch = git_branch(root)
        touched: set[str] = set()

        try:
            for event in payload.events:
                cur = conn.execute(
                    """
                    INSERT INTO change_events (
                        title, summary, finalized_at, git_head, git_branch
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (event.title, event.summary, now, head, branch),
                )
                event_id = cur.lastrowid
                for path_norm in event.paths:
                    conn.execute(
                        """
                        INSERT INTO change_narratives (event_id, path_norm, path_summary)
                        VALUES (?, ?, NULL)
                        """,
                        (event_id, path_norm),
                    )
                    touched.add(path_norm)

            conn.execute("DELETE FROM changes_staging")
            recheck_issues_for_paths(conn, root, touched, config)
            conn.execute(
                """
                UPDATE scan_meta
                SET last_changes_finalize_at = ?
                WHERE id = 1
                """,
                (now,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    if export:
        from repograph.cli import export_cmd

        try:
            export_cmd.run(root)
        except Exception as exc:
            raise FinalizeExportError(
                "Finalize persisted to the database, but export failed. "
                "Re-run `repograph export` to refresh artifacts."
            ) from exc

    return touched
