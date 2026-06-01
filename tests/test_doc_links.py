"""Product markdown link gate (VER-02, LNK-01/02).

Fails when README.md, AGENTS.md, or any docs/**/*.md contains a markdown
link whose target does not resolve on disk. .planning/** is excluded — those
are GSD/SDLC artifacts that never ship publicly (D-10).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repograph.issues.detectors import broken_md_links_for_file
from repograph.paths import normalize_path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _product_markdown_files() -> list[str]:
    paths: list[str] = []
    for top in ("README.md", "AGENTS.md"):
        if (REPO_ROOT / top).is_file():
            paths.append(top)
    docs_dir = REPO_ROOT / "docs"
    if docs_dir.is_dir():
        for md in sorted(docs_dir.rglob("*.md")):
            paths.append(normalize_path(str(md.relative_to(REPO_ROOT))))
    return paths


@pytest.mark.parametrize("path_norm", _product_markdown_files())
def test_product_markdown_links_resolve(path_norm: str) -> None:
    rows = broken_md_links_for_file(REPO_ROOT, path_norm)
    assert rows == [], f"broken markdown links in {path_norm}: {rows}"
