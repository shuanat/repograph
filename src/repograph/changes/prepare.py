"""Markdown brief of staged changes for agent consumption."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repograph.changes.git_util import git_head
from repograph.changes.staging import staging_count


def _fetch_staged_rows(conn: sqlite3.Connection) -> list[tuple[str, str, int, int, str]]:
    rows = conn.execute(
        """
        SELECT
            s.path_norm,
            s.op,
            COALESCE(s.lines_added, 0),
            COALESCE(s.lines_deleted, 0),
            COALESCE(e.domain_auto, 'unknown') AS domain_auto
        FROM changes_staging s
        LEFT JOIN entries e ON e.path_norm = s.path_norm
        ORDER BY domain_auto, s.path_norm
        """
    ).fetchall()
    return [(str(r[0]), str(r[1]), int(r[2]), int(r[3]), str(r[4])) for r in rows]


def render_prepare_brief(conn: sqlite3.Connection, repo_root: Path) -> str:
    """Build markdown brief grouped by domain_auto (D-09, D-10)."""
    count = staging_count(conn)
    if count == 0:
        return "No paths staged. Run `repograph changes ingest` after editing files."

    lines: list[str] = ["# Repograph change brief", ""]
    lines.append(f"Staged: {count} path(s)")
    head = git_head(repo_root)
    if head:
        short = head[:7] if len(head) >= 7 else head
        lines.append(f"HEAD: `{short}`")
    lines.append("")

    by_domain: dict[str, list[tuple[str, str, int, int]]] = {}
    for path_norm, op, added, deleted, domain in _fetch_staged_rows(conn):
        by_domain.setdefault(domain, []).append((path_norm, op, added, deleted))

    for domain in sorted(by_domain):
        lines.append(f"## {domain}")
        for path_norm, op, added, deleted in by_domain[domain]:
            stat = f"(+{added}/-{deleted})" if added or deleted else ""
            suffix = f" {stat}" if stat else ""
            lines.append(f"- `{op}` `{path_norm}`{suffix}")
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)
