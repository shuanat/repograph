import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from classify import domain_auto, legacy_auto, role_auto  # noqa: E402


def test_domain():
    assert domain_auto("kubernetes/manifests/platform/vault/x.yaml") == "kubernetes"
    assert domain_auto("mikrotik/scripts/x.rsc") == "mikrotik"


def test_legacy():
    assert legacy_auto("kubernetes/archive/foo.yaml") == 1
    assert legacy_auto("mikrotik/archive/x") == 0
    assert legacy_auto("archive/old-reports/x.md") == 0
    assert legacy_auto("archive") == 0


def test_role_file():
    assert role_auto("mikrotik/scripts/x.rsc", "file", ".rsc") == "script"
