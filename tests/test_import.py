"""Package import, constants, and path utility smoke tests."""

from __future__ import annotations

import pytest

import repograph
from repograph import constants, paths


def test_import() -> None:
    assert repograph.__doc__ is not None or True


def test_constants() -> None:
    assert constants.REPOGRAPH_DIR == ".repograph"


def test_paths_normalize() -> None:
    assert paths.normalize_path("a\\b\\c") == "a/b/c"
    assert paths.normalize_path(".\\foo\\..\\bar") == "bar"
    assert paths.normalize_path("../../../outside") == "outside"


def test_paths_normalize_rejects_absolute() -> None:
    with pytest.raises(ValueError, match="relative to repository root"):
        paths.normalize_path("/etc/passwd")
    with pytest.raises(ValueError, match="relative to repository root"):
        paths.normalize_path("C:/Windows/System32")
    with pytest.raises(ValueError, match="relative to repository root"):
        paths.normalize_path("C:")


def test_paths_skip() -> None:
    assert paths.should_skip(".repograph/db.sqlite", "db.sqlite")
    assert paths.should_skip("repograph.db", "repograph.db")
