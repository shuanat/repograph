import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paths import normalize_path, parent_path, should_skip  # noqa: E402


def test_normalize_windows():
    assert normalize_path("a\\b\\c") == "a/b/c"
    assert normalize_path(".\\foo\\..\\bar") == "bar"


def test_parent():
    assert parent_path("a/b") == "a"
    assert parent_path("a") is None


def test_skip_db():
    assert should_skip("project-inventory.db", "project-inventory.db")
