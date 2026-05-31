"""CLI help surface contract tests."""

from __future__ import annotations

import re
import subprocess
import sys


def _run_repograph(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "repograph", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_help_exit_zero() -> None:
    result = _run_repograph("--help")
    assert result.returncode == 0


def test_help_lists_doctor() -> None:
    result = _run_repograph("--help")
    assert "doctor" in result.stdout


def test_help_lists_scan_and_config() -> None:
    result = _run_repograph("--help")
    assert "scan" in result.stdout
    assert "config" in result.stdout
    assert "export" in result.stdout
    assert "refresh" in result.stdout


def test_help_no_future_stub_commands() -> None:
    result = _run_repograph("--help")
    out = result.stdout
    for stub in ():
        assert not re.search(rf"^\s*{stub}\s*$", out, re.MULTILINE), (
            f"stub command {stub!r} should not appear as a top-level command"
        )


def test_help_lists_semantic() -> None:
    result = _run_repograph("--help")
    assert result.returncode == 0
    assert "semantic" in result.stdout


def test_semantic_help_lists_rebuild_query() -> None:
    result = _run_repograph("semantic", "--help")
    assert result.returncode == 0
    out = result.stdout
    assert "rebuild" in out
    assert "query" in out


def test_help_lists_changes() -> None:
    result = _run_repograph("--help")
    assert result.returncode == 0
    assert "changes" in result.stdout
    sub = _run_repograph("changes", "--help")
    assert sub.returncode == 0
    for name in ("ingest", "status"):
        assert name in sub.stdout


def test_help_lists_label() -> None:
    result = _run_repograph("--help")
    assert result.returncode == 0
    assert "label" in result.stdout
    sub = _run_repograph("label", "--help")
    assert sub.returncode == 0
    for name in ("export", "apply-batch", "queue", "vocab-apply"):
        assert name in sub.stdout


def test_export_help() -> None:
    result = _run_repograph("export", "--help")
    assert result.returncode == 0
    assert "--output" in result.stdout


def test_refresh_help() -> None:
    result = _run_repograph("refresh", "--help")
    assert result.returncode == 0
    assert "annotation" in result.stdout.lower()


def test_doctor_help() -> None:
    result = _run_repograph("doctor", "--help")
    assert result.returncode == 0
    assert "--strict" in result.stdout


def test_config_help() -> None:
    result = _run_repograph("config", "--help")
    assert result.returncode == 0
    for sub in ("init", "apply", "validate"):
        assert sub in result.stdout


def test_help_lists_agent_guide() -> None:
    result = _run_repograph("--help")
    assert result.returncode == 0
    assert "agent-guide" in result.stdout
    sub = _run_repograph("agent-guide", "--help")
    assert sub.returncode == 0
    out = sub.stdout.lower()
    assert "stdout" in out or "playbook" in out
    assert "--output" in sub.stdout
