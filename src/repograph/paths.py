"""Path normalization and scan exclusions."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

SCANNER_VERSION = "1.0.0"

SKIP_NAMES = frozenset(
    {
        "repograph.db",
    }
)

SKIP_SUFFIXES = (
    ".db-wal",
    ".db-shm",
    ".db-journal",
    ".tmp",
    ".tmp-journal",
)


def _is_windows_drive_root(part: str) -> bool:
    return len(part) == 2 and part[1] == ":" and part[0].isalpha()


def normalize_path(rel: str) -> str:
    """Relative POSIX path from repo root."""
    p = PurePosixPath(rel.replace("\\", "/"))
    if p.is_absolute() or (p.parts and _is_windows_drive_root(p.parts[0])):
        raise ValueError("path must be relative to repository root")
    parts: list[str] = []
    for part in p.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def should_skip(rel_norm: str, name: str) -> bool:
    if not name.strip():
        return True
    if name in SKIP_NAMES:
        return True
    if rel_norm == ".repograph" or rel_norm.startswith(".repograph/"):
        return True
    if rel_norm == ".repograph/db.sqlite":
        return True
    for suf in SKIP_SUFFIXES:
        if name.endswith(suf) or rel_norm.endswith(suf):
            return True
    if rel_norm.startswith(".repograph/") and rel_norm.endswith(".tmp"):
        return True
    return False


def parent_path(path_norm: str) -> str | None:
    if "/" not in path_norm:
        return None
    return path_norm.rsplit("/", 1)[0]


def is_dot_git(path_norm: str) -> bool:
    return path_norm == ".git" or path_norm.startswith(".git/")


def is_under_git_objects(path_norm: str) -> bool:
    return path_norm.startswith(".git/objects/")


def resolve_repo_root(root: str | Path) -> Path:
    return Path(root).resolve()


def long_path(path: Path) -> Path:
    """Windows extended path prefix when needed."""
    s = str(path.resolve())
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        if len(s) > 240:
            return Path("\\\\?\\" + s)
    return path
