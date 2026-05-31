#!/usr/bin/env python3
"""Export file-exception paths for labeling (orphan, legacy, dup, openvas)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from label import DEFAULT_DB_NAME, connect, issues_for_path, parent_effective  # noqa: E402
from label import child_sample  # noqa: E402

EXCEPTION_SQL = """
SELECT DISTINCT e.path_norm
FROM entries e
WHERE e.present = 1 AND e.is_sensitive = 0 AND e.is_dot_git = 0
  AND e.entry_kind = 'file'
  AND (
    EXISTS (
      SELECT 1 FROM issues i
      WHERE i.path_norm = e.path_norm
        AND i.code IN ('OPENVAS_PARALLEL_TREE', 'ORPHAN_ROOT_FILE', 'BROKEN_MD_LINK')
    )
    OR e.legacy_auto = 1
    OR EXISTS (SELECT 1 FROM duplicate_members dm WHERE dm.path_norm = e.path_norm)
    OR (
      e.path_norm NOT LIKE '%/%'
      AND e.name NOT IN ('README.md', '.gitignore', '.gitattributes', 'LICENSE', 'LICENSE.md')
    )
  )
ORDER BY e.path_norm
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path(DEFAULT_DB_NAME))
    parser.add_argument("-o", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    conn = connect(args.db)
    paths = [r[0] for r in conn.execute(EXCEPTION_SQL + f" LIMIT {args.limit}").fetchall()]
    batch = []
    for path_norm in paths:
        e = conn.execute("SELECT * FROM entries WHERE path_norm = ?", (path_norm,)).fetchone()
        if not e:
            continue
        batch.append(
            {
                "path_norm": path_norm,
                "entry_kind": "file",
                "depth": e["depth"],
                "name": e["name"],
                "domain_auto": e["domain_auto"],
                "role_auto": e["role_auto"],
                "legacy_auto": e["legacy_auto"],
                "extension": e["extension"],
                "issues": issues_for_path(conn, path_norm),
                "parent_effective": parent_effective(conn, path_norm),
            }
        )
    conn.close()
    args.o.write_text(json.dumps(batch, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(batch)} exceptions to {args.o}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
