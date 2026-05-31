import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scan import link_target_exists  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "mini-lab"


def test_link_target_file_and_dir():
    root = FIXTURE.resolve()
    assert link_target_exists(root, "README.md")
    assert link_target_exists(root, "mikrotik/configs/")
