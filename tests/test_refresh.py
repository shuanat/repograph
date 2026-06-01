"""Refresh scan and CLI tests (Phase 3, SCN-04)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import seed_annotations
from repograph.cli.main import app
from repograph.scan.runner import run_scan

runner = CliRunner()


def _db(repo: Path) -> Path:
    return repo / ".repograph" / "db.sqlite"


def _annotation_row(conn: sqlite3.Connection, path_norm: str) -> tuple | None:
    return conn.execute(
        """
        SELECT path_norm, purpose, action_planned, label_status
        FROM annotations WHERE path_norm = ?
        """,
        (path_norm,),
    ).fetchone()


def test_refresh_preserves_seeded_annotation(mini_lab_copy: Path) -> None:
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

    run_scan(mini_lab_copy, preserve_annotations=True)
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        row = _annotation_row(conn, "alpha/readme.md")
        assert row is not None
        assert row[0] == "alpha/readme.md"
        assert row[1] == "entry point doc"
        assert row[3] == "labeled"
    finally:
        conn.close()


def test_refresh_stale_on_removed_path(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        seed_annotations(
            conn,
            [
                {
                    "path_norm": "alpha/readme.md",
                    "purpose": "will go stale",
                    "label_status": "labeled",
                }
            ],
        )
    finally:
        conn.close()

    (mini_lab_copy / "alpha" / "readme.md").unlink()
    run_scan(mini_lab_copy, preserve_annotations=True)
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        row = _annotation_row(conn, "alpha/readme.md")
        assert row is not None
        assert row[3] == "stale"
    finally:
        conn.close()


def test_refresh_stale_on_sha_change(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        seed_annotations(
            conn,
            [
                {
                    "path_norm": "beta/readme.md",
                    "action_planned": "review",
                    "label_status": "labeled",
                }
            ],
        )
    finally:
        conn.close()

    readme = mini_lab_copy / "beta" / "readme.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    run_scan(mini_lab_copy, preserve_annotations=True)
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        row = _annotation_row(conn, "beta/readme.md")
        assert row is not None
        assert row[2] == "review"
        assert row[3] == "stale"
    finally:
        conn.close()


def test_scan_does_not_seed_annotations(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        seed_annotations(
            conn,
            [{"path_norm": "alpha/readme.md", "purpose": "only in live db"}],
        )
    finally:
        conn.close()

    run_scan(mini_lab_copy)
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        count = conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_refresh_cli_preserves_seeded_annotations(mini_lab_copy: Path) -> None:
    assert runner.invoke(app, ["scan", str(mini_lab_copy)]).exit_code == 0
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        seed_annotations(
            conn,
            [
                {
                    "path_norm": "alpha/readme.md",
                    "purpose": "cli preserved",
                    "label_status": "labeled",
                },
                {
                    "path_norm": "beta/readme.md",
                    "action_planned": "keep labeled",
                    "label_status": "labeled",
                },
            ],
        )
    finally:
        conn.close()

    result = runner.invoke(app, ["refresh", str(mini_lab_copy)])
    assert result.exit_code == 0
    assert "Refresh complete" in result.stdout

    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        alpha = _annotation_row(conn, "alpha/readme.md")
        beta = _annotation_row(conn, "beta/readme.md")
        assert alpha is not None and alpha[1] == "cli preserved" and alpha[3] == "labeled"
        assert beta is not None and beta[2] == "keep labeled" and beta[3] == "labeled"
    finally:
        conn.close()


def test_refresh_cli_stale_on_removed_path(mini_lab_copy: Path) -> None:
    runner.invoke(app, ["scan", str(mini_lab_copy)])
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        seed_annotations(
            conn,
            [
                {
                    "path_norm": "alpha/readme.md",
                    "purpose": "cli stale",
                    "label_status": "labeled",
                }
            ],
        )
    finally:
        conn.close()

    (mini_lab_copy / "alpha" / "readme.md").unlink()
    assert runner.invoke(app, ["refresh", str(mini_lab_copy)]).exit_code == 0
    conn = sqlite3.connect(_db(mini_lab_copy))
    try:
        row = _annotation_row(conn, "alpha/readme.md")
        assert row is not None and row[3] == "stale"
    finally:
        conn.close()


def test_refresh_exit_warn_only(mini_lab_copy: Path) -> None:
    runner.invoke(app, ["scan", str(mini_lab_copy)])
    result = runner.invoke(app, ["refresh", str(mini_lab_copy)])
    assert result.exit_code == 0


def test_refresh_exit_error(mini_lab_copy: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(_root: Path, *, preserve_annotations: bool = False) -> object:
        from repograph.scan.runner import ScanResult

        assert preserve_annotations is True
        return ScanResult(
            has_error=True,
            issue_counts={"error": 1, "warn": 0, "info": 0},
        )

    monkeypatch.setattr("repograph.cli.refresh_cmd.run_scan", _fail)
    result = runner.invoke(app, ["refresh", str(mini_lab_copy)])
    assert result.exit_code == 1


def test_refresh_cli_help() -> None:
    result = runner.invoke(app, ["refresh", "--help"])
    assert result.exit_code == 0
    assert "annotation" in result.stdout.lower()
