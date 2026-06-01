"""Shared pytest fixtures for Repograph tests."""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from repograph.semantic.embedder import FakeEmbedder

FIXTURE = Path(__file__).parent / "fixtures" / "mini-lab"


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def mini_lab_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "mini-lab"
    shutil.copytree(FIXTURE, dest)
    return dest


@pytest.fixture
def mini_lab_git(mini_lab_copy: Path) -> Path:
    """mini-lab copy initialized as a git repo with an initial commit."""
    root = mini_lab_copy
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "repograph-test@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Repograph Test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return root


def seed_annotations(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Insert test annotation rows (D-18); path_norm must exist in entries."""
    for row in rows:
        path_norm = row["path_norm"]
        label_status = row.get("label_status", "labeled")
        purpose = row.get("purpose")
        action_planned = row.get("action_planned")
        if not purpose and not action_planned:
            raise ValueError("each row needs purpose or action_planned")
        conn.execute(
            """
            INSERT INTO annotations (path_norm, purpose, action_planned, label_status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(path_norm) DO UPDATE SET
                purpose = excluded.purpose,
                action_planned = excluded.action_planned,
                label_status = excluded.label_status
            """,
            (path_norm, purpose, action_planned, label_status),
        )
    conn.commit()
