"""Scan CLI and pipeline tests (Phase 2)."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import FIXTURE
from repograph.cli.main import app
from repograph.scan.runner import run_scan

runner = CliRunner()


@pytest.fixture
def mini_lab_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "mini-lab"
    shutil.copytree(FIXTURE, dest)
    return dest


def _issue_codes(db: Path) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {row[0] for row in conn.execute("SELECT DISTINCT code FROM issues")}
    finally:
        conn.close()


def test_walk_skips_repograph(tmp_path: Path) -> None:
    from repograph.config.model import RepographConfig
    from repograph.scan.walk import walk_repo

    (tmp_path / ".repograph").mkdir()
    (tmp_path / ".repograph" / "db.sqlite").write_bytes(b"x")
    (tmp_path / "visible.txt").write_text("ok", encoding="utf-8")
    entries, _ = walk_repo(tmp_path, RepographConfig())
    paths = {e["path_norm"] for e in entries}
    assert "visible.txt" in paths
    assert not any(p.startswith(".repograph/") for p in paths)


def test_hash_cap(tmp_path: Path) -> None:
    from repograph.scan.runner import MAX_HASH_BYTES, run_scan

    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * (MAX_HASH_BYTES + 1))
    run_scan(tmp_path)
    conn = sqlite3.connect(tmp_path / ".repograph" / "db.sqlite")
    try:
        sha = conn.execute(
            "SELECT sha256 FROM entries WHERE path_norm = 'big.bin'"
        ).fetchone()[0]
        assert sha is None
    finally:
        conn.close()


def test_domain_auto_unknown(mini_lab_copy: Path) -> None:
    from repograph.scan.classify import domain_auto

    assert domain_auto("alpha/readme.md", {}) == "unknown"


def test_scan_creates_db(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    db = mini_lab_copy / ".repograph" / "db.sqlite"
    assert db.is_file()
    conn = sqlite3.connect(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM entries WHERE present = 1").fetchone()[
            0
        ]
        meta = conn.execute("SELECT id FROM scan_meta WHERE id = 1").fetchone()
        assert count > 0
        assert meta is not None
    finally:
        conn.close()


def test_present_zero(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    victim = mini_lab_copy / "alpha" / "readme.md"
    victim.unlink()
    run_scan(mini_lab_copy)
    conn = sqlite3.connect(mini_lab_copy / ".repograph" / "db.sqlite")
    try:
        row = conn.execute(
            "SELECT present FROM entries WHERE path_norm = 'alpha/readme.md'"
        ).fetchone()
        assert row is not None
        assert row[0] == 0
    finally:
        conn.close()


def test_broken_md_link(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    codes = _issue_codes(mini_lab_copy / ".repograph" / "db.sqlite")
    assert "BROKEN_MD_LINK" in codes


def test_duplicate_basename_on_fixture(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    codes = _issue_codes(mini_lab_copy / ".repograph" / "db.sqlite")
    assert "DUPLICATE_BASENAME" in codes


def test_duplicate_content_on_fixture(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    db = mini_lab_copy / ".repograph" / "db.sqlite"
    codes = _issue_codes(db)
    assert "DUPLICATE_CONTENT" in codes
    conn = sqlite3.connect(db)
    try:
        groups = conn.execute(
            "SELECT COUNT(*) FROM duplicate_groups WHERE member_count > 1"
        ).fetchone()[0]
        assert groups >= 1
    finally:
        conn.close()


def test_scan_exit_warn_only(mini_lab_copy: Path) -> None:
    result = runner.invoke(app, ["scan", str(mini_lab_copy)])
    assert result.exit_code == 0


def test_scan_exit_error(mini_lab_copy: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(_root: Path) -> object:
        from repograph.scan.runner import ScanResult

        return ScanResult(
            has_error=True,
            issue_counts={"error": 1, "warn": 0, "info": 0},
        )

    monkeypatch.setattr("repograph.cli.scan.run_scan", _fail)
    result = runner.invoke(app, ["scan", str(mini_lab_copy)])
    assert result.exit_code == 1


def test_cli_help_scan() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "scan" in result.stdout


def test_scan_cli_invocation(mini_lab_copy: Path) -> None:
    result = runner.invoke(app, ["scan", str(mini_lab_copy)])
    assert result.exit_code == 0
    assert (mini_lab_copy / ".repograph" / "db.sqlite").is_file()
