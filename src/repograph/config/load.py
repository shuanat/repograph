"""Load repograph.yaml from .repograph/."""

from __future__ import annotations

from pathlib import Path

import yaml
from pathspec import PathSpec

from repograph.config.defaults import SENSITIVE_GLOBS
from repograph.config.model import RepographConfig
from repograph.constants import REPOGRAPH_DIR


class ConfigLoadError(Exception):
    """Applied repograph.yaml exists but is invalid."""


def config_path(repo_root: Path) -> Path:
    return repo_root / REPOGRAPH_DIR / "repograph.yaml"


def load_config(repo_root: Path) -> RepographConfig:
    """Load applied yaml or return built-in defaults only."""
    path = config_path(repo_root)
    if not path.is_file():
        return RepographConfig()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "repograph.yaml must be a mapping"
        raise ValueError(msg)
    return RepographConfig.model_validate(data)


def pathspec_for_config(config: RepographConfig) -> tuple[PathSpec, PathSpec]:
    """Ignore and sensitive pathspec matchers."""
    ignore_lines = list(config.ignore) + [f"{REPOGRAPH_DIR}/**"]
    ignore_spec = PathSpec.from_lines("gitwildmatch", ignore_lines)
    sensitive_spec = PathSpec.from_lines(
        "gitwildmatch",
        list(config.sensitive_globs) or list(SENSITIVE_GLOBS),
    )
    return ignore_spec, sensitive_spec
