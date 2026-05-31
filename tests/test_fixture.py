"""Mini-lab fixture presence tests."""

from __future__ import annotations

from conftest import FIXTURE


def test_fixture_is_directory() -> None:
    assert FIXTURE.is_dir()


def test_fixture_has_files() -> None:
    files = list(FIXTURE.rglob("*"))
    assert any(p.is_file() for p in files)
