import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scan import run_scan  # noqa: E402


FIXTURE = Path(__file__).parent / "fixtures" / "mini-lab"


def test_scan_mini_lab(tmp_path):
    db = tmp_path / "test.db"
    run_scan(FIXTURE.resolve(), db)
    conn = sqlite3.connect(db)
    files = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE entry_kind='file' AND present=1"
    ).fetchone()[0]
    assert files >= 2
    sens = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE is_sensitive=1"
    ).fetchone()[0]
    assert sens >= 1
    conn.close()
