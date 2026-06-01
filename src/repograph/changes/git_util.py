"""Git discovery for changes ingest."""

from __future__ import annotations

import subprocess
from pathlib import Path

from repograph.paths import normalize_path


def is_git_repo(repo_root: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--git-dir"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _map_op(xy: str, raw_path: str) -> str:
    if " -> " in raw_path:
        return "rename"
    x, y = xy[0], xy[1]
    if x == "?" and y == "?":
        return "add"
    if x in "AR" or y in "AR":
        if x == "R" or y == "R":
            return "rename"
        return "add"
    if x == "D" or y == "D":
        return "delete"
    return "modify"


def _parse_porcelain(repo_root: Path) -> list[dict]:
    proc = _run_git(repo_root, "status", "--porcelain=v1", "-u")
    if proc.returncode != 0:
        return []
    candidates: list[dict] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        raw_path = line[3:].strip()
        old_path_norm: str | None = None
        if " -> " in raw_path:
            old_raw, new_raw = raw_path.split(" -> ", 1)
            old_path_norm = normalize_path(old_raw.strip())
            path_norm = normalize_path(new_raw.strip())
        else:
            path_norm = normalize_path(raw_path)
        op = _map_op(xy, raw_path)
        candidates.append(
            {
                "path_norm": path_norm,
                "op": op,
                "old_path_norm": old_path_norm,
                "lines_added": 0,
                "lines_deleted": 0,
                "git_status": xy,
            }
        )
    return candidates


def _parse_numstat(stdout: str, into: dict[str, tuple[int, int]]) -> None:
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_s, deleted_s, path = parts[0], parts[1], parts[2]
        if added_s == "-" or deleted_s == "-":
            continue
        try:
            added, deleted = int(added_s), int(deleted_s)
        except ValueError:
            continue
        path_norm = normalize_path(path)
        prev_a, prev_d = into.get(path_norm, (0, 0))
        into[path_norm] = (prev_a + added, prev_d + deleted)


def _numstat_by_path(repo_root: Path) -> dict[str, tuple[int, int]]:
    stats: dict[str, tuple[int, int]] = {}
    for args in (("diff", "--numstat"), ("diff", "--cached", "--numstat")):
        proc = _run_git(repo_root, *args)
        if proc.returncode == 0:
            _parse_numstat(proc.stdout, stats)
    return stats


def git_head(repo_root: Path) -> str | None:
    proc = _run_git(repo_root, "rev-parse", "HEAD")
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def git_branch(repo_root: Path) -> str | None:
    proc = _run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def iter_staged_candidates(repo_root: Path) -> list[dict]:
    """Git-changed paths with op, stats, and porcelain status."""
    candidates = _parse_porcelain(repo_root)
    stats = _numstat_by_path(repo_root)
    for row in candidates:
        path_norm = row["path_norm"]
        if path_norm in stats:
            added, deleted = stats[path_norm]
            row["lines_added"] = added
            row["lines_deleted"] = deleted
    return candidates
