#!/usr/bin/env python3
"""Label content-duplicate file groups with canonical_path_norm."""

from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from label import apply_one, connect, utc_now  # noqa: E402


def main() -> int:
    conn = connect(Path("project-inventory.db"))
    rows = conn.execute(
        """
        SELECT dm.path_norm, e.sha256, dg.member_count, e.domain_auto
        FROM duplicate_members dm
        JOIN duplicate_groups dg ON dg.id = dm.group_id
        JOIN entries e ON e.path_norm = dm.path_norm
        LEFT JOIN annotations a ON a.path_norm = dm.path_norm
        WHERE e.is_sensitive = 0
          AND (a.duplicate_kind IS NULL OR a.duplicate_kind = 'none')
        ORDER BY dg.sha256, dm.path_norm
        """
    ).fetchall()
    by_sha: dict[str, list] = defaultdict(list)
    for r in rows:
        by_sha[r["sha256"]].append(dict(r))

    count = 0
    for sha, members in by_sha.items():
        paths = [m["path_norm"] for m in members]
        # canonical: shortest path, prefer non-archive
        def rank(p: str) -> tuple:
            return (
                "archive" in p,
                p.count("/"),
                len(p),
                p,
            )

        canonical = min(paths, key=rank)
        for p in paths:
            item = {
                "path_norm": p,
                "purpose": f"Content duplicate (sha256 {sha[:12]}…); {len(paths)} copies.",
                "belongs_to": "unknown",
                "file_kind": "other",
                "lifecycle": "duplicate" if p != canonical else "active",
                "action_planned": "delete" if p != canonical else "keep",
                "duplicate_kind": "exact_copy",
                "canonical_path_norm": canonical,
                "keep_reason": "Shortest non-archive path in duplicate group." if p != canonical else None,
                "restructure_wave": "wave0_safe",
                "risk_level": "low",
                "label_status": "labeled",
                "entry_kind": "file",
            }
            if p == canonical:
                item["lifecycle"] = "active"
                item["action_planned"] = "keep"
                item["duplicate_kind"] = "none"
                item["canonical_path_norm"] = None
            apply_one(conn, item, "composer-2.5", "dup-v1")
            count += 1
    conn.commit()
    conn.close()
    print(f"Labeled {count} duplicate member paths in {len(by_sha)} groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
