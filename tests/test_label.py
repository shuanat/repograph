"""Tests for label batch CLI and batches package."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from repograph.batches.vocab import ApplyError, merge_vocab, validate_enum
from repograph.batches.models import VocabRow
from repograph.constants import DB_SQLITE, REPOGRAPH_DIR
from repograph.store.migrate import migrate
from conftest import seed_annotations

FIXTURES = Path(__file__).parent / "fixtures"
VOCAB_FIXTURE = FIXTURES / "label-vocab.json"
APPLY_FIXTURE = FIXTURES / "label-batch-apply.json"


def _run_repograph(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "repograph", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _scan_and_vocab(root: Path) -> None:
    assert _run_repograph(root, "scan").returncode == 0
    assert _run_repograph(root, "config", "init").returncode == 0
    assert _run_repograph(root, "config", "apply").returncode == 0
    assert _run_repograph(
        root, "label", "vocab-apply", "-f", str(VOCAB_FIXTURE)
    ).returncode == 0


def test_label_help_lists_subcommands() -> None:
    result = _run_repograph(Path.cwd(), "label", "--help")
    assert result.returncode == 0
    for name in ("export", "apply-batch", "queue", "vocab-apply"):
        assert name in result.stdout


def test_help_lists_label_group() -> None:
    result = _run_repograph(Path.cwd(), "--help")
    assert result.returncode == 0
    assert "label" in result.stdout


def test_vocab_merge_and_validate_enum(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    migrate(db)
    conn = sqlite3.connect(db)
    try:
        merge_vocab(
            conn,
            [VocabRow(kind="lifecycle", code="active", label="Active")],
        )
        conn.commit()
        validate_enum("lifecycle", "active", conn)
        with pytest.raises(ApplyError):
            validate_enum("lifecycle", "bogus", conn)
    finally:
        conn.close()


def test_vocab_apply_cli(mini_lab_git: Path) -> None:
    _scan_and_vocab(mini_lab_git)
    result = _run_repograph(mini_lab_git, "label", "vocab-list", "--json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    kinds = {row["kind"] for row in data}
    assert "belongs_to" in kinds


def test_belongs_to_domain_key_passes(mini_lab_git: Path) -> None:
    from repograph.batches.vocab import validate_belongs_to
    from repograph.config.load import load_config

    _scan_and_vocab(mini_lab_git)
    db = mini_lab_git / REPOGRAPH_DIR / DB_SQLITE
    config = load_config(mini_lab_git)
    conn = sqlite3.connect(db)
    try:
        if config.domains:
            key = next(iter(config.domains))
            validate_belongs_to(key, config, conn)
    finally:
        conn.close()


def test_export_has_project_vocab_and_items(mini_lab_git: Path) -> None:
    _scan_and_vocab(mini_lab_git)
    result = _run_repograph(mini_lab_git, "label", "export", "--limit", "5")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "project_vocab" in data
    assert "items" in data
    assert isinstance(data["project_vocab"], list)
    assert isinstance(data["items"], list)


def test_export_skips_sensitive(mini_lab_git: Path) -> None:
    _scan_and_vocab(mini_lab_git)
    result = _run_repograph(mini_lab_git, "label", "export", "--limit", "50")
    data = json.loads(result.stdout)
    paths = {item["path_norm"] for item in data["items"]}
    assert not any(".env" in p for p in paths)


def test_label_queue_json(mini_lab_git: Path) -> None:
    _scan_and_vocab(mini_lab_git)
    result = _run_repograph(
        mini_lab_git, "label", "queue", "--json", "--limit", "3"
    )
    assert result.returncode == 0
    rows = json.loads(result.stdout)
    assert isinstance(rows, list)
    if rows:
        assert "path_norm" in rows[0]


def test_has_issues_filter(mini_lab_git: Path) -> None:
    _scan_and_vocab(mini_lab_git)
    all_result = _run_repograph(
        mini_lab_git, "label", "export", "--limit", "50", "--full-queue"
    )
    filtered = _run_repograph(
        mini_lab_git,
        "label",
        "export",
        "--limit",
        "50",
        "--full-queue",
        "--has-issues",
    )
    all_data = json.loads(all_result.stdout)
    filt_data = json.loads(filtered.stdout)
    assert len(filt_data["items"]) <= len(all_data["items"])
    if filt_data["items"]:
        assert any(item.get("issues") for item in filt_data["items"])


def test_actionable_excludes_file_under_labeled_parent(mini_lab_git: Path) -> None:
    _scan_and_vocab(mini_lab_git)
    db = mini_lab_git / REPOGRAPH_DIR / DB_SQLITE
    conn = sqlite3.connect(db)
    try:
        parent = conn.execute(
            """
            SELECT path_norm FROM entries
            WHERE entry_kind = 'directory' AND present = 1 AND depth = 1
            LIMIT 1
            """
        ).fetchone()
        assert parent
        parent_path = parent[0]
        seed_annotations(
            conn,
            [
                {
                    "path_norm": parent_path,
                    "purpose": "Labeled parent",
                    "action_planned": "keep",
                    "label_status": "labeled",
                }
            ],
        )
        conn.execute(
            """
            UPDATE annotations SET applies_to_descendants = 1
            WHERE path_norm = ?
            """,
            (parent_path,),
        )
        conn.commit()
        child = conn.execute(
            """
            SELECT path_norm FROM entries
            WHERE parent_path_norm = ? AND entry_kind = 'file' AND present = 1
            LIMIT 1
            """,
            (parent_path,),
        ).fetchone()
        if not child:
            pytest.skip("no child file under test parent")
        child_path = child[0]
        actionable = {
            r[0]
            for r in conn.execute(
                "SELECT path_norm FROM v_label_queue_actionable"
            ).fetchall()
        }
        assert child_path not in actionable
    finally:
        conn.close()


def test_apply_happy_path(mini_lab_git: Path) -> None:
    _scan_and_vocab(mini_lab_git)
    result = _run_repograph(
        mini_lab_git,
        "label",
        "apply-batch",
        "-f",
        str(APPLY_FIXTURE),
        "--model",
        "test",
        "--prompt-version",
        "1",
        "--no-semantic-rebuild",
    )
    assert result.returncode == 0
    db = mini_lab_git / REPOGRAPH_DIR / DB_SQLITE
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT purpose, label_status FROM annotations WHERE path_norm = 'README.md'"
        ).fetchone()
        assert row
        assert row[0]
        assert row[1] == "labeled"
    finally:
        conn.close()


def test_apply_bad_vocab_rollback(mini_lab_git: Path) -> None:
    _scan_and_vocab(mini_lab_git)
    bad = {
        "items": [
            {
                "path_norm": "README.md",
                "purpose": "x",
                "belongs_to": "app",
                "file_kind": "readme",
                "lifecycle": "active",
                "operational_status": "in_use",
                "action_planned": "keep",
                "label_status": "not_a_real_status",
            }
        ]
    }
    bad_path = mini_lab_git / "bad-batch.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    result = _run_repograph(
        mini_lab_git,
        "label",
        "apply-batch",
        "-f",
        str(bad_path),
    )
    assert result.returncode == 1
    conn = sqlite3.connect(mini_lab_git / REPOGRAPH_DIR / DB_SQLITE)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM annotations WHERE path_norm = 'README.md'"
        ).fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_dry_run_leaves_db_unchanged(mini_lab_git: Path) -> None:
    _scan_and_vocab(mini_lab_git)
    result = _run_repograph(
        mini_lab_git,
        "label",
        "apply-batch",
        "-f",
        str(APPLY_FIXTURE),
        "--dry-run",
    )
    assert result.returncode == 0
    conn = sqlite3.connect(mini_lab_git / REPOGRAPH_DIR / DB_SQLITE)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM annotations WHERE path_norm = 'README.md'"
        ).fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_docs_label_batch_exists() -> None:
    doc = Path(__file__).resolve().parents[1] / "docs" / "label-batch.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "changes finalize" in text.lower()
    assert "project_vocab" in text


def test_label_e2e_export_after_apply(mini_lab_git: Path) -> None:
    _scan_and_vocab(mini_lab_git)
    assert (
        _run_repograph(
            mini_lab_git,
            "label",
            "apply-batch",
            "-f",
            str(APPLY_FIXTURE),
            "--export",
            "--no-semantic-rebuild",
            "--model",
            "test",
            "--prompt-version",
            "1",
        ).returncode
        == 0
    )
    md = mini_lab_git / REPOGRAPH_DIR / "repograph.md"
    assert md.is_file()
    assert "overview" in md.read_text(encoding="utf-8").lower()
