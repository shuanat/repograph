"""Label queue iteration with whitelisted view names."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

VIEW_ACTIONABLE = "v_label_queue_actionable"
VIEW_FULL = "v_label_queue"
ALLOWED_VIEWS = frozenset({VIEW_ACTIONABLE, VIEW_FULL})


@dataclass
class QueueFilters:
    limit: int = 25
    depth: int | None = None
    depth_max: int | None = None
    kind: str | None = None
    domain: str | None = None
    has_issues: bool = False
    full_queue: bool = False

    @property
    def view_name(self) -> str:
        return VIEW_FULL if self.full_queue else VIEW_ACTIONABLE


def iter_queue_paths(
    conn: sqlite3.Connection,
    filters: QueueFilters,
) -> list[str]:
    if filters.limit < 1:
        msg = f"limit must be >= 1, got {filters.limit}"
        raise ValueError(msg)

    view = filters.view_name
    if view not in ALLOWED_VIEWS:
        msg = f"invalid view: {view}"
        raise ValueError(msg)

    sql = f"SELECT path_norm FROM {view} WHERE 1=1"
    params: list[object] = []

    if filters.depth is not None:
        sql += " AND depth = ?"
        params.append(filters.depth)
    if filters.depth_max is not None:
        sql += " AND depth <= ?"
        params.append(filters.depth_max)
    if filters.kind:
        sql += " AND entry_kind = ?"
        params.append(filters.kind)
    if filters.domain:
        sql += " AND domain_auto = ?"
        params.append(filters.domain)
    if filters.has_issues:
        sql += (
            " AND EXISTS (SELECT 1 FROM issues i WHERE i.path_norm = path_norm)"
        )

    sql += " ORDER BY depth, entry_kind DESC, path_norm LIMIT ?"
    params.append(filters.limit)

    return [row[0] for row in conn.execute(sql, params).fetchall()]
