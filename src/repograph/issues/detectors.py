"""Neutral structural issue detectors (HLT-01)."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

from repograph.config.model import RepographConfig
from repograph.issues.post import IssueRow
from repograph.paths import normalize_path

MARKDOWN_LINK_RE = re.compile(r"\]\(([^)#\s]+)\)")

MAX_HASH_BYTES = 2 * 1024 * 1024


def link_target_exists(repo_root: Path, rel: str) -> bool:
    p = repo_root / rel.replace("/", os.sep)
    if p.exists():
        return True
    if p.is_dir():
        return True
    readme = p / "README.md"
    return readme.is_file()


def detect_issues(
    entries: list[dict],
    repo_root: Path,
    walk_errors: list[tuple[str, str]],
    config: RepographConfig,
    *,
    include_layout: bool = False,
) -> list[IssueRow]:
    rows: list[IssueRow] = []

    if include_layout and config.expected_toplevel:
        allowed = set(config.expected_toplevel)
        tops = {
            e["path_norm"]
            for e in entries
            if e["entry_kind"] == "directory" and "/" not in e["path_norm"]
        }
        for top in tops:
            if top and top not in allowed and not top.startswith("."):
                rows.append(
                    (
                        "warn",
                        "UNEXPECTED_TOPLEVEL",
                        top,
                        f"Top-level directory not in expected_toplevel: {top}",
                    )
                )

    by_name: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        if entry["entry_kind"] != "file":
            continue
        by_name[entry["name"]].append(entry["path_norm"])
    for name, paths in by_name.items():
        if len(paths) > 1:
            rows.append(
                (
                    "warn",
                    "DUPLICATE_BASENAME",
                    paths[0],
                    f"Basename {name!r} appears at {len(paths)} paths",
                )
            )

    for entry in entries:
        if entry.get("scan_error"):
            rows.append(
                ("error", "SCAN_SKIPPED", entry["path_norm"], entry["scan_error"])
            )

    for entry in entries:
        if entry["entry_kind"] != "file" or entry.get("is_sensitive"):
            continue
        rows.extend(broken_md_links_for_file(repo_root, entry["path_norm"]))

    for path, msg in walk_errors:
        rows.append(("error", "SCAN_SKIPPED", path or None, msg))

    return rows


def broken_md_links_for_file(repo_root: Path, path_norm: str) -> list[IssueRow]:
    """Path-local BROKEN_MD_LINK rows for one markdown file (HLT-03)."""
    if not path_norm.endswith(".md"):
        return []
    fp = repo_root / path_norm.replace("/", os.sep)
    if not fp.is_file():
        return []
    rows: list[IssueRow] = []
    try:
        text = fp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    base_dir = fp.parent
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (base_dir / target).resolve()
        try:
            rel = normalize_path(str(resolved.relative_to(repo_root.resolve())))
        except ValueError:
            rows.append(
                (
                    "warn",
                    "BROKEN_MD_LINK",
                    path_norm,
                    f"Off-repo link: {target}",
                )
            )
            continue
        if not link_target_exists(repo_root, rel):
            rows.append(
                (
                    "warn",
                    "BROKEN_MD_LINK",
                    path_norm,
                    f"Broken link to {target}",
                )
            )
    return rows


def sensitive_path_issues(entries: list[dict]) -> list[IssueRow]:
    rows: list[IssueRow] = []
    for entry in entries:
        if entry.get("is_sensitive"):
            rows.append(
                (
                    "info",
                    "SENSITIVE_PATH",
                    entry["path_norm"],
                    "Path matches sensitive_globs",
                )
            )
    return rows


def content_duplicate_issues(conn) -> list[IssueRow]:
    """One DUPLICATE_CONTENT issue per duplicate group."""
    rows: list[IssueRow] = []
    groups = conn.execute(
        """
        SELECT id, sha256, member_count
        FROM duplicate_groups
        WHERE member_count > 1
        """
    ).fetchall()
    for gid, sha, count in groups:
        sample = conn.execute(
            "SELECT path_norm FROM duplicate_members WHERE group_id = ? LIMIT 1",
            (gid,),
        ).fetchone()
        path = sample[0] if sample else None
        rows.append(
            (
                "info",
                "DUPLICATE_CONTENT",
                path,
                f"Duplicate content hash {sha[:12]}… ({count} files)",
            )
        )
    return rows
