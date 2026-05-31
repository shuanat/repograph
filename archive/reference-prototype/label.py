#!/usr/bin/env python3
"""Phase 2: queue, export, and apply LLM annotation batches."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from vocab_data import VOCAB_ROWS

TOOL_DIR = Path(__file__).resolve().parent
DEFAULT_DB_NAME = "project-inventory.db"

ANNOTATION_FIELDS = [
    "purpose",
    "belongs_to",
    "folder_kind",
    "file_kind",
    "lifecycle",
    "operational_status",
    "content_summary",
    "structure_zone",
    "target_path_norm",
    "target_name",
    "target_belongs_to",
    "action_planned",
    "restructure_wave",
    "priority",
    "effort",
    "action_confidence",
    "canonical_path_norm",
    "duplicate_kind",
    "keep_reason",
    "risk_level",
    "blocks_restructure",
    "runtime_touchpoints",
    "move_group_id",
    "repo_fit",
    "git_policy",
    "applies_to_descendants",
    "notes",
    "restructure_notes",
    "label_status",
]

VOCAB_BY_KIND: dict[str, set[str]] = {}
for kind, code, _label, _order in VOCAB_ROWS:
    VOCAB_BY_KIND.setdefault(kind, set()).add(code)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


ACTIONABLE_VIEW_DDL = """
CREATE VIEW IF NOT EXISTS v_label_queue_actionable AS
SELECT
    q.path_norm,
    q.entry_kind,
    q.depth,
    q.name,
    q.domain_auto,
    q.role_auto,
    q.legacy_auto,
    q.label_status
FROM v_label_queue q
JOIN entries e ON e.path_norm = q.path_norm
LEFT JOIN v_effective ve ON ve.path_norm = q.path_norm
WHERE q.entry_kind = 'directory'
   OR (
        q.entry_kind = 'file'
        AND (
            ve.inherited_from IS NULL
            OR e.legacy_auto = 1
            OR EXISTS (
                SELECT 1 FROM issues i
                WHERE i.path_norm = q.path_norm
                  AND (
                      i.code IN (
                          'OPENVAS_PARALLEL_TREE',
                          'ORPHAN_ROOT_FILE',
                          'BROKEN_MD_LINK'
                      )
                      OR i.code LIKE 'LEGACY%'
                  )
            )
            OR EXISTS (
                SELECT 1 FROM duplicate_members dm WHERE dm.path_norm = q.path_norm
            )
            OR NOT EXISTS (
                SELECT 1 FROM annotations pa
                WHERE pa.path_norm = e.parent_path_norm
                  AND pa.label_status = 'labeled'
                  AND pa.applies_to_descendants = 1
            )
        )
    );
"""


def ensure_actionable_view(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_label_queue_actionable'"
    ).fetchone()
    if not row:
        conn.execute(ACTIONABLE_VIEW_DDL)
        conn.commit()


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        print(f"Database not found: {db_path}. Run scan.py first.", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_actionable_view(conn)
    return conn


def queue_table(actionable: bool) -> str:
    return "v_label_queue_actionable" if actionable else "v_label_queue"


def validate_vocab(field: str, value: str | None) -> str | None:
    if value is None:
        return None
    kind_map = {
        "belongs_to": "belongs_to",
        "folder_kind": "folder_kind",
        "file_kind": "file_kind",
        "lifecycle": "lifecycle",
        "operational_status": "operational_status",
        "structure_zone": "structure_zone",
        "action_planned": "action_planned",
        "restructure_wave": "restructure_wave",
        "priority": "priority",
        "effort": "effort",
        "action_confidence": "action_confidence",
        "duplicate_kind": "duplicate_kind",
        "risk_level": "risk_level",
        "repo_fit": "repo_fit",
        "git_policy": "git_policy",
        "label_status": "label_status",
        "target_belongs_to": "belongs_to",
    }
    kind = kind_map.get(field)
    if kind and value not in VOCAB_BY_KIND.get(kind, set()):
        raise ValueError(f"Invalid {field}={value!r}, not in vocab")
    return value


def child_sample(conn: sqlite3.Connection, path_norm: str, limit: int = 12) -> list[str]:
    prefix = path_norm + "/" if path_norm else ""
    rows = conn.execute(
        """
        SELECT name, entry_kind FROM entries
        WHERE present = 1 AND parent_path_norm = ?
        ORDER BY entry_kind DESC, name
        LIMIT ?
        """,
        (path_norm if path_norm else None, limit),
    ).fetchall()
    if not rows and path_norm == "":
        rows = conn.execute(
            """
            SELECT name, entry_kind FROM entries
            WHERE present = 1 AND parent_path_norm IS NULL AND path_norm != ''
            ORDER BY entry_kind DESC, name
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        suffix = "/" if r["entry_kind"] == "directory" else ""
        out.append(r["name"] + suffix)
    return out


def issues_for_path(conn: sqlite3.Connection, path_norm: str) -> list[str]:
    rows = conn.execute(
        "SELECT code, message FROM issues WHERE path_norm = ?", (path_norm,)
    ).fetchall()
    return [f"{r['code']}: {r['message']}" for r in rows]


def parent_effective(conn: sqlite3.Connection, path_norm: str) -> dict | None:
    from paths import parent_path

    pp = parent_path(path_norm)
    if not pp:
        return None
    row = conn.execute(
        """
        SELECT effective_purpose AS purpose, effective_belongs_to AS belongs_to,
               effective_lifecycle AS lifecycle
        FROM v_effective WHERE path_norm = ?
        """,
        (pp,),
    ).fetchone()
    if not row or not row["purpose"]:
        return None
    return dict(row)


def cmd_queue(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    tbl = queue_table(getattr(args, "actionable", False))
    sql = f"""
        SELECT path_norm, entry_kind, depth, domain_auto, role_auto, label_status
        FROM {tbl}
        WHERE 1=1
    """
    params: list = []
    if args.depth is not None:
        sql += " AND depth = ?"
        params.append(args.depth)
    if args.depth_max is not None:
        sql += " AND depth <= ?"
        params.append(args.depth_max)
    if args.kind:
        sql += " AND entry_kind = ?"
        params.append(args.kind)
    sql += " ORDER BY depth, entry_kind DESC, path_norm LIMIT ?"
    params.append(args.limit)
    rows = conn.execute(sql, params).fetchall()
    if args.json:
        print(json.dumps([dict(r) for r in rows], indent=2))
        return
    for r in rows:
        print(f"{r['depth']:2} {r['entry_kind'][:3]} {r['path_norm'] or '.'} [{r['domain_auto']}]")


def cmd_export(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    queue_args = argparse.Namespace(
        depth=args.depth,
        depth_max=args.depth_max,
        kind=args.kind,
        limit=args.limit,
        json=False,
    )
    actionable = getattr(args, "actionable", True)
    tbl = queue_table(actionable)
    sql = f"SELECT path_norm FROM {tbl} WHERE 1=1"
    params: list = []
    if args.depth is not None:
        sql += " AND depth = ?"
        params.append(args.depth)
    if args.depth_max is not None:
        sql += " AND depth <= ?"
        params.append(args.depth_max)
    if args.kind:
        sql += " AND entry_kind = ?"
        params.append(args.kind)
    sql += " ORDER BY depth, entry_kind DESC, path_norm LIMIT ?"
    params.append(args.limit)
    paths = [r[0] for r in conn.execute(sql, params).fetchall()]

    batch = []
    for path_norm in paths:
        e = conn.execute("SELECT * FROM entries WHERE path_norm = ?", (path_norm,)).fetchone()
        if not e or e["is_sensitive"]:
            continue
        item = {
            "path_norm": path_norm,
            "entry_kind": e["entry_kind"],
            "depth": e["depth"],
            "name": e["name"],
            "domain_auto": e["domain_auto"],
            "role_auto": e["role_auto"],
            "legacy_auto": e["legacy_auto"],
            "extension": e["extension"],
            "size_bytes": e["size_bytes"],
            "child_sample": child_sample(conn, path_norm),
            "issues": issues_for_path(conn, path_norm),
            "parent_effective": parent_effective(conn, path_norm),
        }
        if e["entry_kind"] == "file" and args.with_preview:
            repo = conn.execute("SELECT repo_root FROM scan_meta WHERE id=1").fetchone()
            if repo:
                fp = Path(repo["repo_root"]) / path_norm.replace("/", "\\" if sys.platform == "win32" else "/")
                if fp.is_file() and (e["size_bytes"] or 0) <= 65536:
                    try:
                        item["content_preview"] = fp.read_text(encoding="utf-8", errors="replace")[:4000]
                    except OSError:
                        pass
        batch.append(item)

    out = args.output
    text = json.dumps(batch, indent=2, ensure_ascii=False)
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"Wrote {len(batch)} items to {out}")
    else:
        print(text)


def apply_one(
    conn: sqlite3.Connection,
    item: dict,
    model: str,
    prompt_version: str,
    source: str = "llm",
) -> None:
    if "path_norm" not in item:
        raise ValueError("missing path_norm")
    path_norm = item["path_norm"]

    exists = conn.execute(
        "SELECT 1 FROM entries WHERE path_norm = ? AND present = 1", (path_norm,)
    ).fetchone()
    if not exists:
        raise ValueError(f"path not in entries: {path_norm}")

    row = conn.execute(
        "SELECT is_sensitive FROM entries WHERE path_norm = ?", (path_norm,)
    ).fetchone()
    if row and row["is_sensitive"]:
        raise ValueError(f"sensitive path cannot be labeled: {path_norm}")

    tags = item.pop("tags", None)
    links = item.pop("links", None)

    data: dict = {k: item.get(k) for k in ANNOTATION_FIELDS if k in item}
    data["label_status"] = data.get("label_status") or "labeled"
    data["source"] = source
    data["model"] = model
    data["prompt_version"] = prompt_version
    data["labeled_at"] = utc_now()

    if data.get("applies_to_descendants") is None and item.get("entry_kind") == "directory":
        data["applies_to_descendants"] = 1
    elif isinstance(data.get("applies_to_descendants"), bool):
        data["applies_to_descendants"] = 1 if data["applies_to_descendants"] else 0

    for field in ANNOTATION_FIELDS:
        if field in data:
            validate_vocab(field, data[field])

    insert_cols = ["path_norm"] + [c for c in ANNOTATION_FIELDS if c in data] + [
        "source",
        "model",
        "prompt_version",
        "labeled_at",
    ]
    vals = [path_norm] + [data[c] for c in ANNOTATION_FIELDS if c in data] + [
        data["source"],
        data["model"],
        data["prompt_version"],
        data["labeled_at"],
    ]
    placeholders = ", ".join("?" for _ in insert_cols)
    col_names = ", ".join(insert_cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in insert_cols if c != "path_norm")

    conn.execute(
        f"INSERT INTO annotations ({col_names}) VALUES ({placeholders}) "
        f"ON CONFLICT(path_norm) DO UPDATE SET {updates}",
        vals,
    )

    if tags:
        conn.execute("DELETE FROM entry_tags WHERE path_norm = ?", (path_norm,))
        for tag in tags:
            conn.execute(
                "INSERT OR IGNORE INTO entry_tags (path_norm, tag) VALUES (?, ?)",
                (path_norm, tag),
            )

    if links:
        for link in links:
            conn.execute(
                """
                INSERT OR IGNORE INTO entry_links (from_path, to_path, link_type)
                VALUES (?, ?, ?)
                """,
                (path_norm, link["to_path"], link["link_type"]),
            )


def cmd_apply_batch(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    path = Path(args.batch)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "items" in data:
        items = data["items"]
    elif isinstance(data, list):
        items = data
    else:
        print("Batch must be a JSON array or {items: [...]}", file=sys.stderr)
        sys.exit(1)

    ok = fail = 0
    for item in items:
        try:
            item = dict(item)
            item.setdefault("entry_kind", conn.execute(
                "SELECT entry_kind FROM entries WHERE path_norm=?",
                (item["path_norm"],),
            ).fetchone()[0])
            apply_one(conn, item, args.model, args.prompt_version)
            ok += 1
        except Exception as ex:
            fail += 1
            pn = item.get("path_norm", "?")
            conn.execute(
                """
                INSERT INTO annotations (path_norm, label_status, notes, source, model, prompt_version, labeled_at)
                VALUES (?, 'failed', ?, 'llm', ?, ?, ?)
                ON CONFLICT(path_norm) DO UPDATE SET
                    label_status='failed', notes=excluded.notes, labeled_at=excluded.labeled_at
                """,
                (pn, str(ex), args.model, args.prompt_version, utc_now()),
            )
            print(f"FAIL {pn}: {ex}", file=sys.stderr)
    conn.commit()
    print(f"Applied: {ok} ok, {fail} failed")


def cmd_show(conn: sqlite3.Connection, path: str) -> None:
    e = conn.execute("SELECT * FROM entries WHERE path_norm = ?", (path,)).fetchone()
    a = conn.execute("SELECT * FROM annotations WHERE path_norm = ?", (path,)).fetchone()
    eff = conn.execute("SELECT * FROM v_effective WHERE path_norm = ?", (path,)).fetchone()
    print(json.dumps(
        {
            "entry": dict(e) if e else None,
            "annotation": dict(a) if a else None,
            "effective": {
                k: eff[k]
                for k in (
                    "effective_purpose",
                    "effective_belongs_to",
                    "effective_lifecycle",
                    "inherited_from",
                )
                if eff
            }
            if eff
            else None,
        },
        indent=2,
        ensure_ascii=False,
        default=str,
    ))


def cmd_vocab(kind: str | None) -> None:
    for k, code, label, _ in VOCAB_ROWS:
        if kind and k != kind:
            continue
        print(f"{k}\t{code}\t{label}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Project inventory labeling")
    parser.add_argument("--db", type=Path, default=None, help="Path to SQLite DB")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_queue = sub.add_parser("queue", help="Show label queue")
    p_queue.add_argument("--depth", type=int, default=None)
    p_queue.add_argument("--depth-max", type=int, default=None)
    p_queue.add_argument("--kind", choices=("file", "directory"))
    p_queue.add_argument("--limit", type=int, default=50)
    p_queue.add_argument("--json", action="store_true")
    p_queue.add_argument(
        "--actionable",
        action="store_true",
        help="Use v_label_queue_actionable (skip files covered by parent)",
    )
    p_queue.add_argument(
        "--all",
        action="store_true",
        help="Use full v_label_queue (with --actionable off)",
    )

    p_export = sub.add_parser("export", help="Export batch JSON for LLM")
    p_export.add_argument("-o", "--output", type=Path, default=None)
    p_export.add_argument("--depth", type=int, default=None)
    p_export.add_argument("--depth-max", type=int, default=None)
    p_export.add_argument("--kind", choices=("file", "directory"))
    p_export.add_argument("--limit", type=int, default=30)
    p_export.add_argument("--with-preview", action="store_true")
    p_export.add_argument(
        "--actionable",
        action="store_true",
        default=True,
        help="Export actionable queue only (default: on)",
    )
    p_export.add_argument(
        "--all",
        action="store_true",
        help="Export full queue including inherited files",
    )

    p_apply = sub.add_parser("apply-batch", help="Import labeled JSON batch")
    p_apply.add_argument("batch", type=Path)
    p_apply.add_argument("--model", default="composer-2.5")
    p_apply.add_argument("--prompt-version", default="label-entry-v1")

    p_show = sub.add_parser("show", help="Show entry + annotation")
    p_show.add_argument("path")

    p_vocab = sub.add_parser("vocab", help="List vocab codes")
    p_vocab.add_argument("kind", nargs="?", default=None)

    args = parser.parse_args()
    if args.cmd == "vocab":
        cmd_vocab(args.kind)
        return 0

    if args.cmd in ("queue", "export"):
        if getattr(args, "all", False):
            args.actionable = False
        elif args.cmd == "queue" and not getattr(args, "actionable", False):
            args.actionable = False
        elif args.cmd == "export":
            args.actionable = True

    db_path = args.db
    if db_path is None:
        db_path = Path.cwd() / DEFAULT_DB_NAME
    conn = connect(db_path)
    try:
        if args.cmd == "queue":
            cmd_queue(conn, args)
        elif args.cmd == "export":
            cmd_export(conn, args)
        elif args.cmd == "apply-batch":
            cmd_apply_batch(conn, args)
        elif args.cmd == "show":
            cmd_show(conn, args.path)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
