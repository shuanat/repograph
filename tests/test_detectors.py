"""Issue detector unit tests."""

from __future__ import annotations

from pathlib import Path

from repograph.config.model import RepographConfig
from repograph.issues.detectors import detect_issues


def test_duplicate_basename_skips_init_py(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "__init__.py").write_text("")
    (tmp_path / "b" / "__init__.py").write_text("")
    entries = [
        {
            "path_norm": "a/__init__.py",
            "entry_kind": "file",
            "name": "__init__.py",
        },
        {
            "path_norm": "b/__init__.py",
            "entry_kind": "file",
            "name": "__init__.py",
        },
    ]
    rows = detect_issues(entries, tmp_path, [], RepographConfig(), include_layout=False)
    assert not any(code == "DUPLICATE_BASENAME" for _, code, _, _ in rows)


def test_duplicate_basename_skips_readme(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    entries = [
        {"path_norm": "README.md", "entry_kind": "file", "name": "README.md"},
        {"path_norm": "docs/README.md", "entry_kind": "file", "name": "README.md"},
    ]
    rows = detect_issues(entries, tmp_path, [], RepographConfig(), include_layout=False)
    assert not any(code == "DUPLICATE_BASENAME" for _, code, _, _ in rows)
