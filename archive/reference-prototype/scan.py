#!/usr/bin/env python3
"""Phase 1: scan repository into project-inventory SQLite database."""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pathspec import PathSpec

from classify import (
    EXPECTED_TOPLEVEL,
    MARKDOWN_LINK_RE,
    OPTIONAL_TOPLEVEL,
    SENSITIVE_GLOB_PATTERNS,
    domain_auto,
    is_orphan_root_file,
    is_probably_binary,
    legacy_auto,
    openvas_parallel_candidate,
    parse_extension,
    role_auto,
)
from paths import (
    SCANNER_VERSION,
    is_dot_git,
    is_under_git_objects,
    long_path,
    normalize_path,
    parent_path,
    resolve_repo_root,
    should_skip,
)
from vocab_data import VOCAB_ROWS

MAX_HASH_BYTES = 2 * 1024 * 1024
LARGE_FILE_BYTES = 1024 * 1024
TOOL_DIR = Path(__file__).resolve().parent
DEFAULT_DB = "project-inventory.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_gitignore_spec(repo_root: Path) -> PathSpec:
    gi = repo_root / ".gitignore"
    lines: list[str] = list(SENSITIVE_GLOB_PATTERNS)
    if gi.is_file():
        lines.extend(gi.read_text(encoding="utf-8", errors="replace").splitlines())
    return PathSpec.from_lines("gitwildmatch", lines)


def git_check_ignore(repo_root: Path, paths: list[str]) -> set[str]:
    if not paths:
        return set()
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "-q", "--stdin"],
            input="\n".join(paths),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if proc.returncode == 0:
        return set(paths)
    # git returns 0 if any ignored, 1 if none - with stdin mixed, check per path
    ignored: set[str] = set()
    for p in paths:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "-q", p],
            capture_output=True,
        )
        if r.returncode == 0:
            ignored.add(p)
    return ignored


def git_porcelain(repo_root: Path) -> dict[str, str]:
    status_map: dict[str, str] = {}
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain=v1", "-u", "--ignored"],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired):
        return status_map
    if proc.returncode != 0:
        return status_map
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = normalize_path(path)
        if xy[0] == "!" or xy[1] == "!":
            status_map[path] = "ignored"
        elif xy[0] == "?" or xy[1] == "?":
            status_map[path] = "untracked"
        elif xy[0] == "D" or xy[1] == "D":
            status_map[path] = "deleted"
        else:
            status_map[path] = "tracked"
    return status_map


def git_head_branch(repo_root: Path) -> tuple[str | None, str | None]:
    head = branch = None
    try:
        h = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if h.returncode == 0:
            head = h.stdout.strip()
        b = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if b.returncode == 0:
            branch = b.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return head, branch


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def init_db(conn: sqlite3.Connection, schema_path: Path) -> None:
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.executemany(
        "INSERT OR IGNORE INTO vocab (kind, code, label_ru, sort_order) VALUES (?, ?, ?, ?)",
        VOCAB_ROWS,
    )


def walk_repo(repo_root: Path) -> tuple[list[dict], list[tuple[str, str]]]:
    """Returns (entries, scan_errors)."""
    entries: list[dict] = []
    errors: list[tuple[str, str]] = []
    seen_dirs: set[str] = set()

    def add_dir(path_norm: str) -> None:
        if path_norm in seen_dirs:
            return
        seen_dirs.add(path_norm)
        entries.append(
            {
                "path_norm": path_norm,
                "entry_kind": "directory",
                "name": path_norm.rsplit("/", 1)[-1] if path_norm else "",
            }
        )
        pp = parent_path(path_norm)
        if pp is not None:
            add_dir(pp)

    def onerror(err: OSError) -> None:
        errors.append((normalize_path(str(err.filename or "")), str(err)))

    for dirpath, dirnames, filenames in os.walk(
        repo_root, topdown=True, onerror=onerror, followlinks=False
    ):
        dirnames.sort()
        filenames.sort()
        rel_dir = normalize_path(os.path.relpath(dirpath, repo_root))
        if rel_dir == ".":
            rel_dir = ""

        # prune skip dirs in-place
        kept: list[str] = []
        for d in dirnames:
            child_rel = normalize_path(os.path.join(rel_dir, d) if rel_dir else d)
            if should_skip(child_rel, d):
                continue
            kept.append(d)
        dirnames[:] = kept

        if rel_dir and not should_skip(rel_dir, Path(rel_dir).name):
            add_dir(rel_dir)

        for fn in filenames:
            rel = normalize_path(os.path.join(rel_dir, fn) if rel_dir else fn)
            if should_skip(rel, fn):
                continue
            add_dir(rel_dir if rel_dir else "")
            pp = parent_path(rel)
            if pp:
                add_dir(pp)
            entries.append(
                {
                    "path_norm": rel,
                    "entry_kind": "file",
                    "name": fn,
                }
            )

    # dedupe by path
    by_path: dict[str, dict] = {}
    for e in entries:
        by_path[e["path_norm"]] = e
    return list(by_path.values()), errors


def mark_sensitive(path_norm: str, spec: PathSpec) -> int:
    return 1 if spec.match_file(path_norm) else 0


def link_target_exists(repo_root: Path, rel: str) -> bool:
    """True if markdown link target resolves to a file or directory in repo."""
    p = repo_root / rel.replace("/", os.sep)
    if p.exists():
        return True
    if rel.endswith("/"):
        readme = p / "README.md"
        return readme.is_file()
    if p.is_dir():
        return True
    readme = Path(str(p) + "/README.md")
    return readme.is_file()


def post_issues(
    conn: sqlite3.Connection,
    entries: list[dict],
    repo_root: Path,
    errors: list[tuple[str, str]],
) -> None:
    conn.execute("DELETE FROM issues")
    now_issues: list[tuple[str, str, str | None, str]] = []

    tops = {e["path_norm"] for e in entries if e["entry_kind"] == "directory" and "/" not in e["path_norm"]}
    for expected in EXPECTED_TOPLEVEL:
        if expected not in tops and expected not in OPTIONAL_TOPLEVEL:
            now_issues.append(
                ("info", "README_TOPLEVEL_MISSING", expected, f"Expected top-level directory missing: {expected}")
            )
    for top in tops:
        if not top.strip():
            continue
        if top not in EXPECTED_TOPLEVEL and top not in OPTIONAL_TOPLEVEL and not top.startswith("."):
            now_issues.append(
                ("info", "README_TOPLEVEL_EXTRA", top, f"Extra top-level directory: {top}")
            )

    for e in entries:
        p = e["path_norm"]
        if e["entry_kind"] == "file" and is_orphan_root_file(p, "file"):
            now_issues.append(("warn", "ORPHAN_ROOT_FILE", p, "File at repo root not in standard set"))
        if legacy_auto(p):
            now_issues.append(("info", "LEGACY_PROXMOX_K8S" if p.startswith("proxmox/configs/k8s") else "LEGACY_PATH", p, "Legacy path"))
        if e.get("scan_error"):
            now_issues.append(("error", "SCAN_SKIPPED", p, e["scan_error"]))

    # openvas parallel basenames
    by_base: dict[str, list[str]] = defaultdict(list)
    for e in entries:
        if e["entry_kind"] == "file" and openvas_parallel_candidate(e["path_norm"]):
            by_base[e["name"]].append(e["path_norm"])
    for base, paths in by_base.items():
        if len(paths) > 1:
            now_issues.append(
                (
                    "warn",
                    "OPENVAS_PARALLEL_TREE",
                    paths[0],
                    f"Basename {base} appears {len(paths)} times under openvas/",
                )
            )

    # markdown links
    for e in entries:
        if e["entry_kind"] != "file" or not e["path_norm"].endswith(".md"):
            continue
        if e.get("is_sensitive"):
            continue
        pn = e["path_norm"]
        if pn.startswith("archive/") or "/archive/" in pn:
            continue
        fp = repo_root / pn.replace("/", os.sep)
        if not fp.is_file():
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        base_dir = fp.parent
        for match in MARKDOWN_LINK_RE.finditer(text):
            target = match.group(1).split("#")[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (base_dir / target).resolve()
            try:
                rel = normalize_path(str(resolved.relative_to(repo_root.resolve())))
            except ValueError:
                now_issues.append(
                    ("info", "BROKEN_MD_LINK", e["path_norm"], f"Off-repo link: {target}")
                )
                continue
            if not link_target_exists(repo_root, rel):
                now_issues.append(
                    ("warn", "BROKEN_MD_LINK", e["path_norm"], f"Broken link to {target}")
                )

    for sev, code, path, msg in errors:
        now_issues.append(("error", "SCAN_SKIPPED", path or None, msg))

    conn.executemany(
        "INSERT INTO issues (severity, code, path_norm, message) VALUES (?, ?, ?, ?)",
        now_issues,
    )


def build_duplicates(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM duplicate_members")
    conn.execute("DELETE FROM duplicate_groups")
    rows = conn.execute(
        """
        SELECT sha256, GROUP_CONCAT(path_norm), COUNT(*)
        FROM entries
        WHERE sha256 IS NOT NULL AND present = 1
        GROUP BY sha256
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for sha, _paths, cnt in rows:
        cur = conn.execute(
            "INSERT INTO duplicate_groups (group_type, sha256, member_count) VALUES ('content', ?, ?)",
            (sha, cnt),
        )
        gid = cur.lastrowid
        members = conn.execute(
            "SELECT path_norm FROM entries WHERE sha256 = ?", (sha,)
        ).fetchall()
        conn.executemany(
            "INSERT INTO duplicate_members (group_id, path_norm) VALUES (?, ?)",
            [(gid, m[0]) for m in members],
        )


def run_scan(repo_root: Path, db_path: Path) -> None:
    schema_path = TOOL_DIR / "schema.sql"
    tmp_db = Path(str(db_path) + ".tmp")

    if tmp_db.exists():
        tmp_db.unlink()

    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    final_files = final_dirs = 0
    try:
        init_db(conn, schema_path)
        now = utc_now()
        raw_entries, walk_errors = walk_repo(repo_root)
        paths = [e["path_norm"] for e in raw_entries]
        ignored = git_check_ignore(repo_root, paths)
        git_status = git_porcelain(repo_root)
        spec = load_gitignore_spec(repo_root)
        head, branch = git_head_branch(repo_root)

        file_count = dir_count = 0
        total_bytes = 0
        sensitive_count = 0
        scan_skipped = len(walk_errors)
        stats = {"files": 0, "dirs": 0}

        # mark all not present first if rescan
        conn.execute("UPDATE entries SET present = 0")

        for err_path, err_msg in walk_errors:
            pass

        err_map = {p: m for p, m in walk_errors}

        for e in raw_entries:
            p = e["path_norm"]
            kind = e["entry_kind"]
            name = e["name"]
            depth = p.count("/")
            pp = parent_path(p)
            dot = is_dot_git(p)
            sens = mark_sensitive(p, spec)
            if sens:
                sensitive_count += 1
            ig = 1 if p in ignored or spec.match_file(p) else 0
            gs = None if dot else git_status.get(p)
            dom = domain_auto(p)
            ext = parse_extension(name) if kind == "file" else None
            rauto = role_auto(p, kind, ext)
            leg = legacy_auto(p)

            size_bytes = None
            mtime_utc = None
            sha = None
            is_bin = 0

            if kind == "file":
                file_count += 1
                stats["files"] = file_count
                fp = long_path(repo_root / p.replace("/", os.sep))
                if p in err_map:
                    e["scan_error"] = err_map[p]
                elif fp.is_file():
                    try:
                        st = fp.stat()
                        size_bytes = st.st_size
                        total_bytes += size_bytes
                        if not dot:
                            mtime_utc = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).replace(
                                microsecond=0
                            ).isoformat()
                        is_bin = is_probably_binary(ext, size_bytes)
                        if (
                            not sens
                            and not is_bin
                            and not is_under_git_objects(p)
                            and size_bytes <= MAX_HASH_BYTES
                        ):
                            sha = sha256_file(fp)
                    except OSError as ex:
                        e["scan_error"] = str(ex)
                        scan_skipped += 1
                else:
                    e["scan_error"] = "file not found"
            else:
                dir_count += 1
                stats["dirs"] = dir_count

            conn.execute(
                """
                INSERT INTO entries (
                    path_norm, entry_kind, parent_path_norm, depth, name, present,
                    size_bytes, extension, mtime_utc, sha256, is_binary,
                    is_gitignored, is_dot_git, is_sensitive, git_status,
                    domain_auto, role_auto, legacy_auto, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path_norm) DO UPDATE SET
                    entry_kind=excluded.entry_kind,
                    parent_path_norm=excluded.parent_path_norm,
                    depth=excluded.depth,
                    name=excluded.name,
                    present=1,
                    size_bytes=excluded.size_bytes,
                    extension=excluded.extension,
                    mtime_utc=excluded.mtime_utc,
                    sha256=excluded.sha256,
                    is_binary=excluded.is_binary,
                    is_gitignored=excluded.is_gitignored,
                    is_dot_git=excluded.is_dot_git,
                    is_sensitive=excluded.is_sensitive,
                    git_status=excluded.git_status,
                    domain_auto=excluded.domain_auto,
                    role_auto=excluded.role_auto,
                    legacy_auto=excluded.legacy_auto,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    p,
                    kind,
                    pp,
                    depth,
                    name,
                    size_bytes,
                    ext,
                    mtime_utc,
                    sha,
                    is_bin,
                    ig,
                    1 if dot else 0,
                    sens,
                    gs,
                    dom,
                    rauto,
                    leg,
                    now,
                    now,
                ),
            )

        # stale annotations
        conn.execute(
            """
            UPDATE annotations SET label_status = 'stale'
            WHERE path_norm IN (SELECT path_norm FROM entries WHERE present = 0)
            AND label_status != 'stale'
            """
        )

        post_issues(conn, raw_entries, repo_root, walk_errors)
        build_duplicates(conn)

        conn.execute(
            """
            INSERT INTO scan_meta (id, scanned_at, repo_root, git_head, git_branch,
                scanner_version, schema_version, file_count, dir_count, total_bytes,
                scan_skipped_count, sensitive_file_count)
            VALUES (1, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                scanned_at=excluded.scanned_at,
                repo_root=excluded.repo_root,
                git_head=excluded.git_head,
                git_branch=excluded.git_branch,
                scanner_version=excluded.scanner_version,
                file_count=excluded.file_count,
                dir_count=excluded.dir_count,
                total_bytes=excluded.total_bytes,
                scan_skipped_count=excluded.scan_skipped_count,
                sensitive_file_count=excluded.sensitive_file_count
            """,
            (
                now,
                str(repo_root),
                head,
                branch,
                SCANNER_VERSION,
                file_count,
                dir_count,
                total_bytes,
                scan_skipped,
                sensitive_count,
            ),
        )
        conn.commit()
        final_files, final_dirs = file_count, dir_count
    finally:
        conn.close()

    if db_path.exists():
        db_path.unlink()
    tmp_db.replace(db_path)
    print(f"Scan complete: {db_path} ({final_files} files, {final_dirs} dirs)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan repo into project-inventory.db")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output DB path (default: <root>/project-inventory.db)",
    )
    args = parser.parse_args()
    repo_root = resolve_repo_root(args.root)
    db_path = args.out or (repo_root / DEFAULT_DB)
    if not repo_root.is_dir():
        print(f"Not a directory: {repo_root}", file=sys.stderr)
        return 1
    run_scan(repo_root, db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
