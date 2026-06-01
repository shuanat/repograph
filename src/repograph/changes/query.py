"""Query finalized change events."""

from __future__ import annotations

import sqlite3


def list_events(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    path: str | None = None,
    limit: int = 50,
) -> list[tuple[int, str, str, int]]:
    """Return rows: id, finalized_at, title, path_count."""
    clauses: list[str] = []
    params: list[object] = []

    if since:
        clauses.append("e.finalized_at >= ?")
        params.append(since)
    if path:
        clauses.append(
            """
            EXISTS (
                SELECT 1 FROM change_narratives n
                WHERE n.event_id = e.id AND n.path_norm = ?
            )
            """
        )
        params.append(path)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    rows = conn.execute(
        f"""
        SELECT
            e.id,
            e.finalized_at,
            e.title,
            COUNT(n.path_norm) AS path_count
        FROM change_events e
        LEFT JOIN change_narratives n ON n.event_id = e.id
        {where}
        GROUP BY e.id
        ORDER BY e.finalized_at DESC, e.id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [(int(r[0]), str(r[1]), str(r[2]), int(r[3])) for r in rows]


def show_event(conn: sqlite3.Connection, event_id: int) -> str | None:
    """Markdown detail for one event, or None if missing."""
    row = conn.execute(
        """
        SELECT title, summary, finalized_at, git_head, git_branch
        FROM change_events
        WHERE id = ?
        """,
        (event_id,),
    ).fetchone()
    if row is None:
        return None

    title, summary, finalized_at, git_head, git_branch = row
    paths = [
        r[0]
        for r in conn.execute(
            """
            SELECT path_norm FROM change_narratives
            WHERE event_id = ?
            ORDER BY path_norm
            """,
            (event_id,),
        ).fetchall()
    ]

    lines = [
        f"# {title}",
        "",
        f"**Finalized:** {finalized_at}",
    ]
    if git_head:
        lines.append(f"**HEAD:** `{git_head[:7]}`")
    if git_branch:
        lines.append(f"**Branch:** `{git_branch}`")
    lines.extend(["", "## Summary", "", summary, "", "## Paths"])
    for path_norm in paths:
        lines.append(f"- `{path_norm}`")
    return "\n".join(lines)
