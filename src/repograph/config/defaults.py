"""Built-in config defaults when no repograph.yaml is applied."""

from __future__ import annotations

SENSITIVE_GLOBS: list[str] = [
    "*.env",
    "*.env.*",
    "**/.env",
    "**/*credentials*",
    "**/*secret*",
]
