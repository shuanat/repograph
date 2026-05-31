"""Export markdown and CLI tests (Phase 3, HLT-02)."""

from __future__ import annotations

import importlib.resources
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import seed_annotations
from repograph.cli.main import app
from repograph.constants import REPOGRAPH_DIR, REPOGRAPH_MD
from repograph.export.summary import export_markdown
from repograph.scan.runner import run_scan

runner = CliRunner()


def _db(repo: Path) -> Path:
    return repo / REPOGRAPH_DIR / "db.sqlite"


def _repograph_md(repo: Path) -> Path:
    return repo / REPOGRAPH_DIR / REPOGRAPH_MD


def _markdown(repo: Path) -> str:
    conn = sqlite3.connect(_db(repo))
    try:
        return export_markdown(conn, repo)
    finally:
        conn.close()


def test_export_markdown_meta_section(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    scanned_at = sqlite3.connect(_db(mini_lab_copy)).execute(
        "SELECT scanned_at FROM scan_meta WHERE id=1"
    ).fetchone()[0]
    md = _markdown(mini_lab_copy)
    assert "## Meta" in md
    assert scanned_at in md


def test_export_health_broken_link(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    md = _markdown(mini_lab_copy)
    assert "## Health" in md
    assert "BROKEN_MD_LINK" in md
    assert "docs/broken-link.md" in md


def test_export_empty_annotations_line(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    md = _markdown(mini_lab_copy)
    assert "## Annotations" in md
    assert "No annotations yet" in md


def test_export_includes_annotation_rows(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        seed_annotations(
            conn,
            [
                {
                    "path_norm": "alpha/readme.md",
                    "purpose": "entry point doc",
                    "label_status": "labeled",
                }
            ],
        )
    finally:
        conn.close()
    md = _markdown(mini_lab_copy)
    assert "alpha/readme.md" in md
    assert "entry point doc" in md


def test_export_missing_db_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(app, ["export", str(tmp_path)])
    assert result.exit_code == 1


def test_export_schema_v1_exits_1(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db = repo / REPOGRAPH_DIR / "db.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    schema_v1 = (
        importlib.resources.files("repograph.store")
        .joinpath("schema.sql")
        .read_text(encoding="utf-8")
    )
    conn = sqlite3.connect(db)
    try:
        conn.executescript(schema_v1)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    finally:
        conn.close()

    result = runner.invoke(app, ["export", str(repo)])
    assert result.exit_code == 1
    assert "Schema version 1 is too old" in result.stdout
    assert "need 2+" in result.stdout


def test_export_writes_repograph_md(mini_lab_copy: Path) -> None:
    assert runner.invoke(app, ["scan", str(mini_lab_copy)]).exit_code == 0
    result = runner.invoke(app, ["export", str(mini_lab_copy)])
    assert result.exit_code == 0
    assert "Export written:" in result.stdout
    out = _repograph_md(mini_lab_copy)
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert text.strip()
    assert "## Meta" in text


def test_export_custom_output(mini_lab_copy: Path, tmp_path: Path) -> None:
    runner.invoke(app, ["scan", str(mini_lab_copy)])
    custom = tmp_path / "custom-summary.md"
    result = runner.invoke(
        app, ["export", str(mini_lab_copy), "--output", str(custom)]
    )
    assert result.exit_code == 0
    assert custom.is_file()
    assert "## Meta" in custom.read_text(encoding="utf-8")


def test_export_after_seed(mini_lab_copy: Path) -> None:
    runner.invoke(app, ["scan", str(mini_lab_copy)])
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        seed_annotations(
            conn,
            [
                {
                    "path_norm": "beta/readme.md",
                    "purpose": "beta doc",
                    "label_status": "labeled",
                }
            ],
        )
    finally:
        conn.close()
    runner.invoke(app, ["export", str(mini_lab_copy)])
    text = _repograph_md(mini_lab_copy).read_text(encoding="utf-8")
    assert "beta/readme.md" in text or "beta doc" in text


def test_scan_refresh_export_e2e(mini_lab_copy: Path) -> None:
    runner.invoke(app, ["scan", str(mini_lab_copy)])
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        seed_annotations(
            conn,
            [
                {
                    "path_norm": "alpha/readme.md",
                    "purpose": "e2e purpose",
                    "label_status": "labeled",
                }
            ],
        )
    finally:
        conn.close()
    assert runner.invoke(app, ["refresh", str(mini_lab_copy)]).exit_code == 0
    runner.invoke(app, ["export", str(mini_lab_copy)])
    text = _repograph_md(mini_lab_copy).read_text(encoding="utf-8")
    assert "e2e purpose" in text or "alpha/readme.md" in text


def test_export_cli_help() -> None:
    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0
    assert "output" in result.stdout.lower()


def test_export_structure_escapes_domain_like_metacharacters(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "1%").mkdir(parents=True)
    (repo / "1%" / "only.md").write_text("# one\n", encoding="utf-8")
    (repo / "100").mkdir(parents=True)
    (repo / "100" / "other.md").write_text("# two\n", encoding="utf-8")
    (repo / REPOGRAPH_DIR).mkdir(parents=True)
    (repo / REPOGRAPH_DIR / "repograph.yaml").write_text(
        "domains:\n  '1%': literal percent prefix\n",
        encoding="utf-8",
    )
    run_scan(repo)
    md = _markdown(repo)
    assert "`1%` (1 files)" in md


def test_export_health_includes_info_issues(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        conn.execute(
            """
            INSERT INTO issues (severity, code, path_norm, message)
            VALUES ('info', 'TEST_INFO', NULL, 'informational finding')
            """
        )
        conn.commit()
    finally:
        conn.close()
    md = _markdown(mini_lab_copy)
    assert "### Info" in md
    assert "TEST_INFO" in md
