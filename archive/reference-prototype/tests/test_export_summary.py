import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from export_summary import file_breakdown  # noqa: E402
from scan import run_scan  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "mini-lab"


def test_file_breakdown_sums(tmp_path):
    db = tmp_path / "test.db"
    run_scan(FIXTURE.resolve(), db)
    conn = sqlite3.connect(db)
    fb = file_breakdown(conn)
    conn.close()
    assert fb["files_on_disk"] == fb["files_dot_git"] + fb["files_workspace"]
    assert fb["files_workspace"] == (
        fb["files_git_tracked"]
        + fb["files_gitignored_on_disk"]
        + fb["files_untracked"]
        + fb["files_git_deleted"]
    )
    assert fb["files_on_disk"] >= 2
