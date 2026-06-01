"""Config CLI tests (Phase 2)."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from conftest import FIXTURE
from repograph.cli.main import app
from repograph.config.load import config_path
from repograph.config.model import RepographConfig
from repograph.scan.runner import run_scan

runner = CliRunner()


@pytest.fixture
def mini_lab_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "mini-lab"
    shutil.copytree(FIXTURE, dest)
    return dest


def test_config_apply_invalid(mini_lab_copy: Path, tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("domains: not-a-map\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["config", "apply", str(mini_lab_copy), "--file", str(bad)],
    )
    assert result.exit_code == 1
    assert not config_path(mini_lab_copy).exists() or (
        config_path(mini_lab_copy).read_text(encoding="utf-8") != bad.read_text(encoding="utf-8")
    )


def test_domain_prefix_rejects_dotdot() -> None:
    with pytest.raises(ValueError, match="\\.\\."):
        RepographConfig(domains={"../evil/": "x"})


def test_pathspec_compile() -> None:
    RepographConfig(ignore=["*.md"], sensitive_globs=["**/.env"])


def test_config_init(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    result = runner.invoke(app, ["config", "init", str(mini_lab_copy)])
    assert result.exit_code == 0
    cfg = config_path(mini_lab_copy)
    assert cfg.is_file()
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert "domains" in data
    assert "expected_toplevel" in data
    assert "semantic" in data
    assert data["semantic"]["embedding_model"] == "BAAI/bge-small-en-v1.5"


def test_config_init_requires_scan(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "init", str(tmp_path)])
    assert result.exit_code == 1


def test_config_validate_ok(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    runner.invoke(app, ["config", "init", str(mini_lab_copy)])
    result = runner.invoke(app, ["config", "validate", str(mini_lab_copy)])
    assert result.exit_code == 0


def test_unexpected_toplevel(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    runner.invoke(app, ["config", "init", str(mini_lab_copy)])
    cfg = config_path(mini_lab_copy)
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    data["expected_toplevel"] = [
        name for name in data["expected_toplevel"] if name != "unexpected-dir"
    ]
    cfg.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    runner.invoke(app, ["config", "apply", str(mini_lab_copy)])
    run_scan(mini_lab_copy)
    conn = sqlite3.connect(mini_lab_copy / ".repograph" / "db.sqlite")
    try:
        codes = {r[0] for r in conn.execute("SELECT code FROM issues")}
        assert "UNEXPECTED_TOPLEVEL" in codes
    finally:
        conn.close()


def test_sensitive_env(mini_lab_copy: Path) -> None:
    run_scan(mini_lab_copy)
    runner.invoke(app, ["config", "init", str(mini_lab_copy)])
    runner.invoke(app, ["config", "apply", str(mini_lab_copy)])
    run_scan(mini_lab_copy)
    conn = sqlite3.connect(mini_lab_copy / ".repograph" / "db.sqlite")
    try:
        row = conn.execute(
            "SELECT is_sensitive FROM entries WHERE path_norm = '.env'"
        ).fetchone()
        assert row is not None
        assert row[0] == 1
        codes = {r[0] for r in conn.execute("SELECT code FROM issues")}
        assert "SENSITIVE_PATH" in codes
    finally:
        conn.close()


def test_config_flow_e2e(mini_lab_copy: Path) -> None:
    assert runner.invoke(app, ["scan", str(mini_lab_copy)]).exit_code == 0
    assert runner.invoke(app, ["config", "init", str(mini_lab_copy)]).exit_code == 0
    cfg = config_path(mini_lab_copy)
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    data["expected_toplevel"] = [
        n for n in data["expected_toplevel"] if n != "unexpected-dir"
    ]
    cfg.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    assert runner.invoke(app, ["config", "apply", str(mini_lab_copy)]).exit_code == 0
    assert runner.invoke(app, ["scan", str(mini_lab_copy)]).exit_code == 0
