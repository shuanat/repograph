"""Atomic scan into .repograph/db.sqlite."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from repograph.config.load import ConfigLoadError, load_config, pathspec_for_config
from repograph.constants import REPOGRAPH_DIR
from repograph.issues.detectors import (
    content_duplicate_issues,
    detect_issues,
    sensitive_path_issues,
)
from repograph.issues.post import post_issues
from repograph.paths import (
    SCANNER_VERSION,
    is_dot_git,
    is_under_git_objects,
    long_path,
    parent_path,
    resolve_repo_root,
)
from repograph.scan.classify import (
    domain_auto,
    is_probably_binary,
    parse_extension,
    role_auto,
)
from repograph.scan.walk import walk_repo
from repograph.store.migrate import migrate

MAX_HASH_BYTES = 2 * 1024 * 1024


@dataclass
class ScanResult:
    file_count: int = 0
    dir_count: int = 0
    issue_counts: dict[str, int] = field(default_factory=dict)
    has_error: bool = False


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def git_head_branch(repo_root: Path) -> tuple[str | None, str | None]:
    head = branch = None
    try:
        h = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if h.returncode == 0:
            head = h.stdout.strip()
        b = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if b.returncode == 0:
            branch = b.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return head, branch


def git_check_ignore(repo_root: Path, paths: list[str]) -> set[str]:
    ignored: set[str] = set()
    for path in paths:
        try:
            proc = subprocess.run(
                ["git", "-C", str(repo_root), "check-ignore", "-q", path],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0:
            ignored.add(path)
    return ignored


def git_porcelain(repo_root: Path) -> dict[str, str]:
    status_map: dict[str, str] = {}
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain=v1", "-u"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return status_map
    if proc.returncode != 0:
        return status_map
    from repograph.paths import normalize_path

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


def _seed_entries(conn: sqlite3.Connection, source_db: Path) -> None:
    if not source_db.is_file():
        return
    src = sqlite3.connect(source_db)
    try:
        row = src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entries'"
        ).fetchone()
        if not row:
            return
        columns = [r[1] for r in src.execute("PRAGMA table_info(entries)")]
        col_list = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        rows = src.execute(f"SELECT {col_list} FROM entries").fetchall()
        if rows:
            conn.executemany(
                f"INSERT OR REPLACE INTO entries ({col_list}) VALUES ({placeholders})",
                rows,
            )
    finally:
        src.close()


def _seed_annotations(conn: sqlite3.Connection, source_db: Path) -> None:
    if not source_db.is_file():
        return
    src = sqlite3.connect(source_db)
    try:
        row = src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='annotations'"
        ).fetchone()
        if not row:
            return
        columns = [r[1] for r in src.execute("PRAGMA table_info(annotations)")]
        col_list = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        rows = src.execute(f"SELECT {col_list} FROM annotations").fetchall()
        if rows:
            conn.executemany(
                f"INSERT OR REPLACE INTO annotations ({col_list}) VALUES ({placeholders})",
                rows,
            )
    finally:
        src.close()


def _mark_stale_annotations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE annotations SET label_status = 'stale'
        WHERE label_status = 'labeled'
        AND path_norm IN (SELECT path_norm FROM entries WHERE present = 0)
        """
    )
    conn.execute(
        """
        UPDATE annotations SET label_status = 'stale'
        WHERE label_status = 'labeled'
        AND path_norm IN (
            SELECT a.path_norm
            FROM annotations a
            JOIN entries e ON e.path_norm = a.path_norm
            JOIN pre_sha p ON p.path_norm = a.path_norm
            WHERE e.present = 1
            AND p.sha256 IS NOT NULL
            AND e.sha256 IS NOT NULL
            AND p.sha256 != e.sha256
        )
        """
    )


def build_duplicates(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM duplicate_members")
    conn.execute("DELETE FROM duplicate_groups")
    rows = conn.execute(
        """
        SELECT sha256, COUNT(*)
        FROM entries
        WHERE sha256 IS NOT NULL AND present = 1
        GROUP BY sha256
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for sha, count in rows:
        cur = conn.execute(
            """
            INSERT INTO duplicate_groups (group_type, sha256, member_count)
            VALUES ('content', ?, ?)
            """,
            (sha, count),
        )
        gid = cur.lastrowid
        members = conn.execute(
            "SELECT path_norm FROM entries WHERE sha256 = ? AND present = 1",
            (sha,),
        ).fetchall()
        conn.executemany(
            "INSERT INTO duplicate_members (group_id, path_norm) VALUES (?, ?)",
            [(gid, member[0]) for member in members],
        )


def run_scan(repo_root: Path, *, preserve_annotations: bool = False) -> ScanResult:
    repo_root = resolve_repo_root(repo_root)
    repograph_dir = repo_root / REPOGRAPH_DIR
    db_path = repograph_dir / "db.sqlite"
    tmp_path = repograph_dir / "db.sqlite.tmp"

    repograph_dir.mkdir(parents=True, exist_ok=True)
    if tmp_path.exists():
        tmp_path.unlink()

    migrate(tmp_path, repo_root=repo_root)

    conn = sqlite3.connect(tmp_path)
    conn.row_factory = sqlite3.Row
    result = ScanResult()
    try:
        _seed_entries(conn, db_path)
        if preserve_annotations:
            _seed_annotations(conn, db_path)
        try:
            config = load_config(repo_root)
        except (ValueError, ValidationError) as exc:
            raise ConfigLoadError(str(exc)) from exc
        _, sensitive_spec = pathspec_for_config(config)
        now = utc_now()
        raw_entries, walk_errors = walk_repo(repo_root, config)
        paths = [e["path_norm"] for e in raw_entries]
        ignored = git_check_ignore(repo_root, paths)
        git_status = git_porcelain(repo_root)
        head, branch = git_head_branch(repo_root)

        if preserve_annotations:
            conn.execute(
                "CREATE TEMP TABLE pre_sha(path_norm TEXT PRIMARY KEY, sha256 TEXT)"
            )
            conn.execute(
                """
                INSERT INTO pre_sha
                SELECT path_norm, sha256 FROM entries WHERE present = 1
                """
            )

        conn.execute("UPDATE entries SET present = 0")

        file_count = dir_count = 0
        total_bytes = 0
        sensitive_count = 0
        scan_skipped = len(walk_errors)
        err_map = dict(walk_errors)

        for entry in raw_entries:
            path_norm = entry["path_norm"]
            kind = entry["entry_kind"]
            name = entry["name"]
            depth = path_norm.count("/")
            pp = parent_path(path_norm)
            dot = is_dot_git(path_norm)
            sens = 1 if sensitive_spec.match_file(path_norm) else 0
            if sens:
                sensitive_count += 1
            entry["is_sensitive"] = sens
            ig = 1 if path_norm in ignored else 0
            gs = None if dot else git_status.get(path_norm)
            ext = parse_extension(name) if kind == "file" else None
            dom = domain_auto(path_norm, config.domains)
            rauto = role_auto(path_norm, kind, ext)

            size_bytes = None
            mtime_utc = None
            sha = None
            is_bin = 0

            if kind == "file":
                file_count += 1
                fp = long_path(repo_root / path_norm.replace("/", os.sep))
                if path_norm in err_map:
                    entry["scan_error"] = err_map[path_norm]
                elif fp.is_file():
                    try:
                        st = fp.stat()
                        size_bytes = st.st_size
                        total_bytes += size_bytes
                        if not dot:
                            mtime_utc = datetime.fromtimestamp(
                                st.st_mtime, tz=timezone.utc
                            ).replace(microsecond=0).isoformat()
                        is_bin = is_probably_binary(ext, size_bytes)
                        if (
                            not sens
                            and not is_bin
                            and not is_under_git_objects(path_norm)
                            and size_bytes <= MAX_HASH_BYTES
                        ):
                            sha = sha256_file(fp)
                    except OSError as exc:
                        entry["scan_error"] = str(exc)
                        scan_skipped += 1
                else:
                    entry["scan_error"] = "file not found"
            else:
                dir_count += 1

            conn.execute(
                """
                INSERT INTO entries (
                    path_norm, entry_kind, parent_path_norm, depth, name, present,
                    size_bytes, extension, mtime_utc, sha256, is_binary,
                    is_gitignored, is_dot_git, is_sensitive, git_status,
                    domain_auto, role_auto, legacy_auto, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
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
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    path_norm,
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
                    now,
                    now,
                ),
            )

        include_layout = bool(config.expected_toplevel)
        issue_rows = detect_issues(
            raw_entries,
            repo_root,
            walk_errors,
            config,
            include_layout=include_layout,
        )
        issue_rows.extend(sensitive_path_issues(raw_entries))
        build_duplicates(conn)
        issue_rows.extend(content_duplicate_issues(conn))
        post_issues(conn, issue_rows)

        if preserve_annotations:
            _mark_stale_annotations(conn)

        severities = [row[0] for row in issue_rows]
        result.issue_counts = {
            "error": severities.count("error"),
            "warn": severities.count("warn"),
            "info": severities.count("info"),
        }
        result.has_error = result.issue_counts.get("error", 0) > 0

        conn.execute(
            """
            INSERT INTO scan_meta (
                id, scanned_at, repo_root, git_head, git_branch,
                scanner_version, schema_version, file_count, dir_count, total_bytes,
                scan_skipped_count, sensitive_file_count
            ) VALUES (1, ?, ?, ?, ?, ?, 2, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                scanned_at=excluded.scanned_at,
                repo_root=excluded.repo_root,
                git_head=excluded.git_head,
                git_branch=excluded.git_branch,
                scanner_version=excluded.scanner_version,
                schema_version=excluded.schema_version,
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
        result.file_count = file_count
        result.dir_count = dir_count
    finally:
        conn.close()

    try:
        tmp_path.replace(db_path)
    except OSError as exc:
        raise SystemExit(1) from exc
    return result
