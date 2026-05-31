"""Tests for repograph changes CLI (scaffold and schema gates)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from repograph.changes.finalize import FinalizeError, run_finalize
from repograph.changes.ingest import run_ingest
from repograph.changes.models import ChangeEventIn, FinalizePayload
from repograph.changes.prepare import render_prepare_brief
from repograph.constants import REPOGRAPH_DIR
from repograph.scan.runner import run_scan
from repograph.store.migrate import migrate

FINALIZE_FIXTURE = Path(__file__).parent / "fixtures" / "changes-finalize.json"


def _run_repograph(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "repograph", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _db(repo: Path) -> Path:
    return repo / REPOGRAPH_DIR / "db.sqlite"


def test_changes_help_lists_subcommands() -> None:
    result = _run_repograph("changes", "--help")
    assert result.returncode == 0
    out = result.stdout
    for name in ("ingest", "prepare", "finalize", "status", "list", "show"):
        assert name in out


def test_ingest_rename_removes_old_staging_path(mini_lab_git: Path) -> None:
    run_scan(mini_lab_git)
    foo = mini_lab_git / "alpha" / "readme.md"
    foo.write_text("rename me\n", encoding="utf-8")
    run_ingest(mini_lab_git)
    subprocess.run(
        ["git", "mv", "alpha/readme.md", "alpha/renamed-readme.md"],
        cwd=mini_lab_git,
        check=True,
        capture_output=True,
    )
    run_ingest(mini_lab_git)
    conn = sqlite3.connect(_db(mini_lab_git))
    try:
        rows = conn.execute(
            "SELECT path_norm FROM changes_staging ORDER BY path_norm"
        ).fetchall()
        assert rows == [("alpha/renamed-readme.md",)]
    finally:
        conn.close()


def test_finalize_payload_dedupes_paths() -> None:
    event = ChangeEventIn(
        title="t",
        summary="s",
        paths=["alpha/readme.md", "alpha/readme.md"],
    )
    assert event.paths == ["alpha/readme.md"]


def test_ingest_coalesce_same_path(mini_lab_git: Path) -> None:
    run_scan(mini_lab_git)
    readme = mini_lab_git / "alpha" / "readme.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    run_ingest(mini_lab_git)
    run_ingest(mini_lab_git)
    conn = sqlite3.connect(_db(mini_lab_git))
    try:
        count = conn.execute("SELECT COUNT(*) FROM changes_staging").fetchone()[0]
        assert count == 1
        row = conn.execute(
            "SELECT path_norm, first_seen_at, last_seen_at FROM changes_staging"
        ).fetchone()
        assert row is not None
        assert row[0] == "alpha/readme.md"
        assert row[1] is not None and row[2] is not None
    finally:
        conn.close()


def test_ingest_skips_repograph_dir(mini_lab_git: Path) -> None:
    run_scan(mini_lab_git)
    marker = mini_lab_git / REPOGRAPH_DIR / "ingest-marker.txt"
    marker.write_text("touch\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", str(marker.relative_to(mini_lab_git))],
        cwd=mini_lab_git,
        check=True,
        capture_output=True,
    )
    run_ingest(mini_lab_git)
    conn = sqlite3.connect(_db(mini_lab_git))
    try:
        rows = conn.execute(
            "SELECT path_norm FROM changes_staging WHERE path_norm LIKE '.repograph/%'"
        ).fetchall()
        assert rows == []
    finally:
        conn.close()


def test_ingest_requires_migrated_db(mini_lab_git: Path) -> None:
    db = _db(mini_lab_git)
    migrate(db, repo_root=mini_lab_git)
    conn = sqlite3.connect(db)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 5
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='changes_staging'"
        ).fetchone()
        assert table is not None
    finally:
        conn.close()
    (mini_lab_git / "beta" / "readme.md").write_text("edit\n", encoding="utf-8")
    result = run_ingest(mini_lab_git)
    assert result.warnings == []
    assert result.staged_count >= 1


def test_ingest_cli_exit_zero(mini_lab_git: Path) -> None:
    run_scan(mini_lab_git)
    (mini_lab_git / "alpha" / "readme.md").write_text("cli\n", encoding="utf-8")
    result = _run_repograph("changes", "ingest", str(mini_lab_git))
    assert result.returncode == 0
    assert "Ingested" in result.stdout


def test_prepare_empty_staging(mini_lab_git: Path) -> None:
    run_scan(mini_lab_git)
    conn = sqlite3.connect(_db(mini_lab_git))
    try:
        brief = render_prepare_brief(conn, mini_lab_git)
        assert "No paths staged" in brief
    finally:
        conn.close()
    result = _run_repograph("changes", "prepare", str(mini_lab_git))
    assert result.returncode == 0
    assert "No paths staged" in result.stdout


def test_prepare_brief_after_ingest(mini_lab_git: Path) -> None:
    run_scan(mini_lab_git)
    (mini_lab_git / "alpha" / "readme.md").write_text("brief\n", encoding="utf-8")
    run_ingest(mini_lab_git)
    result = _run_repograph("changes", "prepare", str(mini_lab_git))
    assert result.returncode == 0
    assert "Repograph change brief" in result.stdout
    assert "alpha/readme.md" in result.stdout
    assert "unknown" in result.stdout or "## alpha" in result.stdout


def _stage_readme(mini_lab_git: Path) -> None:
    run_scan(mini_lab_git)
    (mini_lab_git / "alpha" / "readme.md").write_text("staged\n", encoding="utf-8")
    run_ingest(mini_lab_git)


def test_finalize_coverage_fail(mini_lab_git: Path) -> None:
    _stage_readme(mini_lab_git)
    conn = sqlite3.connect(_db(mini_lab_git))
    try:
        before = conn.execute("SELECT COUNT(*) FROM changes_staging").fetchone()[0]
        assert before == 1
    finally:
        conn.close()

    bad = FinalizePayload.model_validate(
        {
            "events": [
                {
                    "title": "Incomplete",
                    "summary": "Missing staged path.",
                    "paths": ["beta/readme.md"],
                }
            ]
        }
    )
    with pytest.raises(FinalizeError):
        run_finalize(mini_lab_git, bad)

    conn = sqlite3.connect(_db(mini_lab_git))
    try:
        after = conn.execute("SELECT COUNT(*) FROM changes_staging").fetchone()[0]
        events = conn.execute("SELECT COUNT(*) FROM change_events").fetchone()[0]
        assert after == before
        assert events == 0
    finally:
        conn.close()


def test_finalize_success(mini_lab_git: Path) -> None:
    _stage_readme(mini_lab_git)
    payload = FinalizePayload.model_validate(
        json.loads(FINALIZE_FIXTURE.read_text(encoding="utf-8"))
    )
    touched = run_finalize(mini_lab_git, payload)
    assert touched == {"alpha/readme.md"}

    conn = sqlite3.connect(_db(mini_lab_git))
    try:
        staging = conn.execute("SELECT COUNT(*) FROM changes_staging").fetchone()[0]
        events = conn.execute("SELECT COUNT(*) FROM change_events").fetchone()[0]
        narratives = conn.execute("SELECT COUNT(*) FROM change_narratives").fetchone()[0]
        assert staging == 0
        assert events == 1
        assert narratives == 1
        row = conn.execute(
            "SELECT title, summary FROM change_events WHERE id = 1"
        ).fetchone()
        assert row is not None
        assert row[0] == "Update alpha readme"
    finally:
        conn.close()


def test_finalize_cli_with_file(mini_lab_git: Path) -> None:
    _stage_readme(mini_lab_git)
    result = _run_repograph(
        "changes",
        "finalize",
        str(mini_lab_git),
        "--file",
        str(FINALIZE_FIXTURE),
        "--no-semantic-rebuild",
    )
    assert result.returncode == 0
    assert "Finalized" in result.stdout
    conn = sqlite3.connect(_db(mini_lab_git))
    try:
        assert conn.execute("SELECT COUNT(*) FROM changes_staging").fetchone()[0] == 0
    finally:
        conn.close()


def _issue_rows_for_path(db: Path, path_norm: str) -> list[tuple[str, str]]:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT code, message FROM issues WHERE path_norm = ? ORDER BY code",
            (path_norm,),
        ).fetchall()
    finally:
        conn.close()


def test_finalize_incremental_broken_link(mini_lab_git: Path) -> None:
    run_scan(mini_lab_git)
    db = _db(mini_lab_git)
    before = _issue_rows_for_path(db, "docs/broken-link.md")
    assert any(code == "BROKEN_MD_LINK" for code, _ in before)

    broken = mini_lab_git / "docs" / "broken-link.md"
    broken.write_text(
        "# Fixed link\n\nSee [readme](../alpha/readme.md).\n",
        encoding="utf-8",
    )
    run_ingest(mini_lab_git)

    payload = FinalizePayload.model_validate(
        {
            "events": [
                {
                    "title": "Fix docs link",
                    "summary": "Recheck clears broken link after finalize.",
                    "paths": ["docs/broken-link.md"],
                }
            ]
        }
    )
    run_finalize(mini_lab_git, payload)

    after = _issue_rows_for_path(db, "docs/broken-link.md")
    assert not any(code == "BROKEN_MD_LINK" for code, _ in after)

    conn = sqlite3.connect(db)
    try:
        ts = conn.execute(
            "SELECT last_changes_finalize_at FROM scan_meta WHERE id = 1"
        ).fetchone()[0]
        assert ts is not None
        dup = conn.execute(
            "SELECT COUNT(*) FROM issues WHERE code = 'DUPLICATE_BASENAME'"
        ).fetchone()[0]
        assert dup >= 1
    finally:
        conn.close()


def test_finalize_incremental_untouched_path_issues(mini_lab_git: Path) -> None:
    run_scan(mini_lab_git)
    db = _db(mini_lab_git)
    conn = sqlite3.connect(db)
    try:
        dup_before = conn.execute(
            "SELECT message FROM issues WHERE code = 'DUPLICATE_BASENAME' LIMIT 1"
        ).fetchone()
        assert dup_before is not None
    finally:
        conn.close()

    (mini_lab_git / "docs" / "broken-link.md").write_text(
        "# Fixed\n\nSee [readme](../alpha/readme.md).\n",
        encoding="utf-8",
    )
    (mini_lab_git / "alpha" / "readme.md").write_text("touch\n", encoding="utf-8")
    run_ingest(mini_lab_git)

    payload = FinalizePayload.model_validate(
        {
            "events": [
                {
                    "title": "Batch finalize",
                    "summary": "Two paths; global issues unchanged.",
                    "paths": ["docs/broken-link.md", "alpha/readme.md"],
                }
            ]
        }
    )
    run_finalize(mini_lab_git, payload)

    conn = sqlite3.connect(db)
    try:
        dup_after = conn.execute(
            "SELECT message FROM issues WHERE code = 'DUPLICATE_BASENAME' LIMIT 1"
        ).fetchone()
        assert dup_after == dup_before
        assert not conn.execute(
            "SELECT 1 FROM issues WHERE path_norm = ? AND code = 'BROKEN_MD_LINK'",
            ("docs/broken-link.md",),
        ).fetchone()
    finally:
        conn.close()


def test_status_warn_exit_zero(mini_lab_git: Path) -> None:
    _stage_readme(mini_lab_git)
    result = _run_repograph("changes", "status", str(mini_lab_git))
    assert result.returncode == 0
    assert "WARN" in result.stderr or "WARN" in result.stdout


def test_status_strict_exit_one(mini_lab_git: Path) -> None:
    _stage_readme(mini_lab_git)
    result = _run_repograph("changes", "status", "--strict", str(mini_lab_git))
    assert result.returncode == 1


def test_status_empty_exit_zero(mini_lab_git: Path) -> None:
    run_scan(mini_lab_git)
    result = _run_repograph("changes", "status", str(mini_lab_git))
    assert result.returncode == 0
    assert "empty" in result.stdout.lower()


def test_list_show_after_finalize(mini_lab_git: Path) -> None:
    _stage_readme(mini_lab_git)
    payload = FinalizePayload.model_validate(
        json.loads(FINALIZE_FIXTURE.read_text(encoding="utf-8"))
    )
    run_finalize(mini_lab_git, payload)

    listed = _run_repograph("changes", "list", str(mini_lab_git))
    assert listed.returncode == 0
    assert "Update alpha readme" in listed.stdout
    assert "1 path(s)" in listed.stdout

    event_id = int(listed.stdout.strip().split("\n")[0].split("\t")[0])
    shown = _run_repograph("changes", "show", str(event_id), "--path", str(mini_lab_git))
    assert shown.returncode == 0
    assert "Update alpha readme" in shown.stdout
    assert "alpha/readme.md" in shown.stdout
