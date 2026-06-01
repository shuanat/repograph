"""Agent-guide stdout contract tests (D-18)."""

from __future__ import annotations

import importlib.resources
import os
import subprocess
import sys


def _run_repograph(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONUTF8": "1", "NO_COLOR": "1"}
    return subprocess.run(
        [sys.executable, "-m", "repograph", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_agent_guide_stdout() -> None:
    result = _run_repograph("agent-guide")
    assert result.returncode == 0, result.stderr
    out = result.stdout

    for section in (
        "Quick start",
        "Doctor",
        "Scan",
        "Label",
        "Change journal",
        "Semantic",
        "Export",
    ):
        assert section in out, f"missing section {section!r}"

    assert "exit" in out.lower()
    assert "SQLite" in out or "canonical" in out.lower()

    for cmd in (
        "scan",
        "changes ingest",
        "changes finalize",
        "semantic query",
        "export",
        "doctor",
    ):
        assert cmd in out, f"missing command example {cmd!r}"

    assert "mini-lab" in out or "tests/fixtures/mini-lab" in out
    assert "docs/label-batch.md" in out or "label-batch.md" in out
    # Full label-batch JSON schema is linked, not inlined (LBL-03 / D-07).
    for schema_field in ("path_norm", "entry_kind", '"batch_id"'):
        assert schema_field not in out, f"inlined schema field {schema_field!r}"


def test_agent_guide_token_budget() -> None:
    result = _run_repograph("agent-guide")
    assert result.returncode == 0
    assert len(result.stdout) <= 30_000


def test_guide_fragment_packaged() -> None:
    text = (
        importlib.resources.files("repograph.guide.fragments")
        .joinpath("quickstart.md")
        .read_text(encoding="utf-8")
    )
    assert "Quick start" in text
    assert "repograph scan" in text
