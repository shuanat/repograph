#!/usr/bin/env python3
"""Write project-inventory-summary.md from scan_meta and aggregates."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB = "project-inventory.db"


def file_breakdown(conn: sqlite3.Connection) -> dict[str, int]:
    """Counts from entries; see README — file_count in scan_meta includes .git/."""
    row = conn.execute(
        """
        SELECT
          SUM(CASE WHEN entry_kind = 'file' AND present = 1 THEN 1 ELSE 0 END),
          SUM(CASE WHEN entry_kind = 'file' AND present = 1 AND is_dot_git = 1 THEN 1 ELSE 0 END),
          SUM(CASE WHEN entry_kind = 'file' AND present = 1 AND is_dot_git = 0 THEN 1 ELSE 0 END),
          SUM(
            CASE WHEN entry_kind = 'file' AND present = 1 AND is_dot_git = 0
              AND (git_status IS NULL OR git_status = 'tracked') THEN 1 ELSE 0 END
          ),
          SUM(
            CASE WHEN entry_kind = 'file' AND present = 1 AND is_dot_git = 0
              AND git_status = 'ignored' THEN 1 ELSE 0 END
          ),
          SUM(
            CASE WHEN entry_kind = 'file' AND present = 1 AND is_dot_git = 0
              AND git_status = 'untracked' THEN 1 ELSE 0 END
          ),
          SUM(
            CASE WHEN entry_kind = 'file' AND present = 1 AND is_dot_git = 0
              AND git_status = 'deleted' THEN 1 ELSE 0 END
          )
        FROM entries
        """
    ).fetchone()
    keys = (
        "files_on_disk",
        "files_dot_git",
        "files_workspace",
        "files_git_tracked",
        "files_gitignored_on_disk",
        "files_untracked",
        "files_git_deleted",
    )
    return dict(zip(keys, (int(v or 0) for v in row)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path(DEFAULT_DB))
    parser.add_argument("-o", type=Path, default=Path("project-inventory-summary.md"))
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    meta = conn.execute("SELECT * FROM scan_meta WHERE id=1").fetchone()
    cols = [d[0] for d in conn.execute("SELECT * FROM scan_meta LIMIT 0").description]
    m = dict(zip(cols, meta)) if meta else {}
    fb = file_breakdown(conn)
    lines = [
        "# Project inventory summary",
        "",
        f"- Scanned: {m.get('scanned_at', '?')}",
        f"- Git: {m.get('git_branch', '?')} @ {str(m.get('git_head', ''))[:12]}",
        f"- Dirs (on disk): {m.get('dir_count', 0)}",
        f"- Total size (bytes): {m.get('total_bytes', 0)}",
        f"- Sensitive paths: {m.get('sensitive_file_count', 0)}",
        f"- Scan skipped: {m.get('scan_skipped_count', 0)}",
        "",
        "## File counts",
        "",
        f"- Files on disk (all): **{fb['files_on_disk']}** "
        f"(scan_meta.file_count: {m.get('file_count', 0)})",
        f"- In `.git/`: **{fb['files_dot_git']}**",
        f"- Workspace (outside `.git/`): **{fb['files_workspace']}**",
        f"  - Git-tracked: **{fb['files_git_tracked']}**",
        f"  - Gitignored on disk: **{fb['files_gitignored_on_disk']}**",
        f"  - Untracked: **{fb['files_untracked']}**",
    ]
    if fb["files_git_deleted"]:
        lines.append(f"  - Git deleted (still on disk): **{fb['files_git_deleted']}**")
    lines.extend(
        [
            "",
            "Domain table below counts **workspace** files only (excludes `.git/`).",
            "",
            "## By domain (present)",
            "",
            "| domain | files | dirs |",
            "| --- | ---: | ---: |",
        ]
    )
    for row in conn.execute(
        """
        SELECT domain_auto,
               SUM(CASE WHEN entry_kind='file' THEN 1 ELSE 0 END),
               SUM(CASE WHEN entry_kind='directory' THEN 1 ELSE 0 END)
        FROM entries WHERE present=1 AND is_dot_git=0
        GROUP BY domain_auto ORDER BY 3+2 DESC
        """
    ):
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} |")
    lines.extend(["", "## Labels (labeled count)", ""])
    for row in conn.execute(
        """
        SELECT COALESCE(belongs_to,'(none)'), COUNT(*)
        FROM annotations WHERE label_status='labeled'
        GROUP BY belongs_to ORDER BY 2 DESC
        """
    ):
        lines.append(f"- {row[0]}: {row[1]}")
    lines.extend(["", "## Restructure backlog (count)", ""])
    n = conn.execute("SELECT COUNT(*) FROM v_restructure_backlog").fetchone()[0]
    lines.append(f"- Entries with action != keep: **{n}**")
    lines.extend(["", "## Open issues (warn / error)", ""])
    for row in conn.execute(
        """
        SELECT code, COUNT(*) FROM issues
        WHERE severity IN ('warn', 'error')
        GROUP BY code ORDER BY 2 DESC LIMIT 15
        """
    ):
        lines.append(f"- {row[0]}: {row[1]}")
    info_n = conn.execute(
        "SELECT COUNT(*) FROM issues WHERE severity = 'info'"
    ).fetchone()[0]
    if info_n:
        lines.extend(
            [
                "",
                "## Open issues (info only)",
                "",
                f"- Total info issues: **{info_n}** (off-repo links, optional top-level dirs, …)",
            ]
        )
        for row in conn.execute(
            """
            SELECT code, COUNT(*) FROM issues
            WHERE severity = 'info'
            GROUP BY code ORDER BY 2 DESC LIMIT 10
            """
        ):
            lines.append(f"- {row[0]}: {row[1]}")
    conn.close()
    args.o.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.o}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
