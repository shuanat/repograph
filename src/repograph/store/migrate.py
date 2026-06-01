"""Idempotent SQLite schema migration for Repograph store."""

from __future__ import annotations

import contextlib
import importlib.resources
import sqlite3
from pathlib import Path

_SCHEMA_VERSION = 5
_V4_VERSION = 4
_V3_VERSION = 3
_V1_VERSION = 1
_V2_VERSION = 2


def _load_schema(name: str) -> str:
    path = importlib.resources.files("repograph.store") / name
    return path.read_text(encoding="utf-8")


def migrate(db_path: Path, repo_root: Path | None = None) -> None:
    """Create or upgrade db_path to schema v5.

    Creates parent directories as needed. Safe to call multiple times.
    repo_root is reserved for future scan_meta seeding; unused in v1/v5.
    """
    _ = repo_root
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        if current >= _SCHEMA_VERSION:
            return

        if current < _V1_VERSION:
            conn.executescript(_load_schema("schema.sql"))
            conn.execute(f"PRAGMA user_version = {_V1_VERSION}")

        if conn.execute("PRAGMA user_version").fetchone()[0] < _V2_VERSION:
            conn.executescript(_load_schema("schema_v2.sql"))
            conn.execute(f"PRAGMA user_version = {_V2_VERSION}")

        if conn.execute("PRAGMA user_version").fetchone()[0] < _V3_VERSION:
            conn.executescript(_load_schema("schema_v3.sql"))
            conn.execute(f"PRAGMA user_version = {_V3_VERSION}")

        if conn.execute("PRAGMA user_version").fetchone()[0] < _V4_VERSION:
            conn.executescript(_load_schema("schema_v4.sql"))
            conn.execute(f"PRAGMA user_version = {_V4_VERSION}")

        if conn.execute("PRAGMA user_version").fetchone()[0] < _SCHEMA_VERSION:
            conn.executescript(_load_schema("schema_v5.sql"))
            conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

        conn.commit()
