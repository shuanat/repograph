import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from label import apply_one  # noqa: E402
from scan import run_scan  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "mini-lab"


def test_apply_batch(tmp_path):
    db = tmp_path / "test.db"
    run_scan(FIXTURE.resolve(), db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    apply_one(
        conn,
        {
            "path_norm": "mikrotik",
            "purpose": "MikroTik router artifacts.",
            "belongs_to": "mikrotik",
            "folder_kind": "domain_root",
            "lifecycle": "active",
            "operational_status": "in_use",
            "action_planned": "keep",
            "applies_to_descendants": 1,
            "label_status": "labeled",
        },
        "test",
        "v1",
    )
    conn.commit()
    row = conn.execute(
        "SELECT effective_purpose FROM v_effective WHERE path_norm='mikrotik/configs/dhcp.md'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "MikroTik router artifacts."
