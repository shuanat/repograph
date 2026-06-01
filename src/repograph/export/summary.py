"""Render repograph.md from a read-only SQLite connection."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repograph.config.load import load_config

_ERROR_SHOW = 20
_ERROR_FETCH = 21
_WARN_SHOW = 50
_WARN_FETCH = 51
_INFO_SHOW = 20
_INFO_FETCH = 21


def export_markdown(conn: sqlite3.Connection, repo_root: Path) -> str:
    """Build markdown summary (Meta, Health, Structure, Annotations).

    Caller must verify ``PRAGMA user_version >= 2`` before calling.
    """
    sections = [
        "# Repograph summary",
        "",
        _meta_section(conn),
        _health_section(conn),
        _structure_section(conn, repo_root),
        _annotations_section(conn),
    ]
    return "\n".join(sections) + "\n"


def _meta_section(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        SELECT scanned_at, git_branch, git_head, file_count, dir_count
        FROM scan_meta WHERE id = 1
        """
    ).fetchone()
    lines = ["## Meta", ""]
    if not row:
        lines.append("- No scan metadata yet.")
        return "\n".join(lines)
    scanned_at, git_branch, git_head, file_count, dir_count = row
    head_display = (git_head or "?")[:12]
    lines.extend(
        [
            f"- Scanned: {scanned_at or '?'}",
            f"- Git: {git_branch or '?'} @ {head_display}",
            f"- Files: {file_count or 0}",
            f"- Dirs: {dir_count or 0}",
        ]
    )
    return "\n".join(lines)


def _escape_like_literal(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _count_domain_prefix_files(conn: sqlite3.Connection, prefix: str) -> int:
    """Count present files under a configured domain prefix (literal, not LIKE wildcards)."""
    dir_prefix = prefix.rstrip("/") + "/"
    escaped_dir = _escape_like_literal(dir_prefix)
    count = conn.execute(
        """
        SELECT COUNT(*) FROM entries
        WHERE present = 1 AND entry_kind = 'file' AND is_dot_git = 0
          AND path_norm LIKE ? ESCAPE '\\'
        """,
        (escaped_dir + "%",),
    ).fetchone()[0]
    if prefix and not prefix.endswith("/"):
        escaped = _escape_like_literal(prefix)
        alt = conn.execute(
            """
            SELECT COUNT(*) FROM entries
            WHERE present = 1 AND entry_kind = 'file' AND is_dot_git = 0
              AND (path_norm = ? OR path_norm LIKE ? ESCAPE '\\')
            """,
            (prefix, escaped + "/%",),
        ).fetchone()[0]
        count = max(count, alt)
    return count


def _format_issue_rows(
    conn: sqlite3.Connection,
    severity: str,
    *,
    show_limit: int,
    fetch_limit: int,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT code, path_norm, message
        FROM issues
        WHERE severity = ?
        ORDER BY id
        LIMIT ?
        """,
        (severity, fetch_limit),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM issues WHERE severity = ?", (severity,)
    ).fetchone()[0]
    lines: list[str] = []
    display = rows[:show_limit]
    for code, path_norm, message in display:
        path_part = path_norm or "(repo)"
        snippet = (message or "")[:120]
        lines.append(f"- `{code}` — `{path_part}` — {snippet}")
    if total > show_limit:
        remaining = total - show_limit
        lines.append(f"- _…and {remaining} more {severity} issue(s)_")
    return lines


def _health_section(conn: sqlite3.Connection) -> str:
    lines = ["## Health", ""]
    errors = _format_issue_rows(
        conn, "error", show_limit=_ERROR_SHOW, fetch_limit=_ERROR_FETCH
    )
    warns = _format_issue_rows(
        conn, "warn", show_limit=_WARN_SHOW, fetch_limit=_WARN_FETCH
    )
    infos = _format_issue_rows(
        conn, "info", show_limit=_INFO_SHOW, fetch_limit=_INFO_FETCH
    )
    if errors:
        lines.append("### Errors")
        lines.append("")
        lines.extend(errors)
        lines.append("")
    if warns:
        lines.append("### Warns")
        lines.append("")
        lines.extend(warns)
        lines.append("")
    if infos:
        lines.append("### Info")
        lines.append("")
        lines.extend(infos)
        lines.append("")
    if not errors and not warns and not infos:
        lines.append("- No warn or error issues.")
    return "\n".join(lines).rstrip()


def _structure_section(conn: sqlite3.Connection, repo_root: Path) -> str:
    config = load_config(repo_root)
    lines = ["## Structure", ""]
    if config.expected_toplevel:
        lines.append(
            "- Expected toplevel: "
            + ", ".join(f"`{name}`" for name in config.expected_toplevel)
        )
        lines.append("")
    if config.domains:
        lines.append("Configured domains:")
        for prefix, description in config.domains.items():
            count = _count_domain_prefix_files(conn, prefix)
            desc = f" — {description}" if description else ""
            lines.append(f"- `{prefix}` ({count} files){desc}")
    else:
        lines.append("Domain file counts (present):")
        for domain, count in conn.execute(
            """
            SELECT domain_auto, COUNT(*)
            FROM entries
            WHERE present = 1 AND entry_kind = 'file' AND is_dot_git = 0
            GROUP BY domain_auto
            ORDER BY 2 DESC
            LIMIT 12
            """
        ):
            lines.append(f"- `{domain}`: {count} files")
    return "\n".join(lines)


def _annotations_section(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """
        SELECT a.path_norm, a.purpose, a.action_planned
        FROM annotations a
        JOIN entries e ON e.path_norm = a.path_norm AND e.present = 1
        WHERE a.label_status IN ('labeled', 'pending')
        ORDER BY a.path_norm
        """
    ).fetchall()
    lines = ["## Annotations", ""]
    if not rows:
        lines.append("No annotations yet")
        return "\n".join(lines)
    for path_norm, purpose, action_planned in rows:
        parts: list[str] = []
        if purpose:
            parts.append(purpose)
        if action_planned:
            parts.append(f"action: {action_planned}")
        detail = "; ".join(parts) if parts else "(no detail)"
        lines.append(f"- `{path_norm}` — {detail}")
    return "\n".join(lines)
