"""Repository filesystem walk."""

from __future__ import annotations

import os
from pathlib import Path

from pathspec import PathSpec

from repograph.config.load import pathspec_for_config
from repograph.config.model import RepographConfig
from repograph.paths import normalize_path, parent_path, should_skip


def load_gitignore_spec(repo_root: Path, config: RepographConfig) -> PathSpec:
    lines: list[str] = list(config.ignore)
    gi = repo_root / ".gitignore"
    if gi.is_file():
        lines.extend(gi.read_text(encoding="utf-8", errors="replace").splitlines())
    lines.append(".repograph/**")
    return PathSpec.from_lines("gitwildmatch", lines)


def walk_repo(
    repo_root: Path, config: RepographConfig
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Return (entry dicts with path_norm/kind/name, walk errors)."""
    entries: list[dict] = []
    errors: list[tuple[str, str]] = []
    seen_dirs: set[str] = set()
    ignore_spec, sensitive_spec = pathspec_for_config(config)
    gitignore_spec = load_gitignore_spec(repo_root, config)

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

        kept: list[str] = []
        for d in dirnames:
            child_rel = normalize_path(os.path.join(rel_dir, d) if rel_dir else d)
            if should_skip(child_rel, d):
                continue
            if gitignore_spec.match_file(child_rel) or ignore_spec.match_file(child_rel):
                continue
            kept.append(d)
        dirnames[:] = kept

        if rel_dir and not should_skip(rel_dir, Path(rel_dir).name):
            add_dir(rel_dir)

        for fn in filenames:
            rel = normalize_path(os.path.join(rel_dir, fn) if rel_dir else fn)
            if should_skip(rel, fn):
                continue
            if gitignore_spec.match_file(rel) or ignore_spec.match_file(rel):
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
                    "_sensitive_spec": sensitive_spec,
                }
            )

    by_path: dict[str, dict] = {}
    for entry in entries:
        by_path[entry["path_norm"]] = entry
    return list(by_path.values()), errors
