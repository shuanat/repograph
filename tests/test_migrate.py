"""Tests for store schema v1/v2/v3 and migrate()."""

from __future__ import annotations

import importlib.resources
import sqlite3

from repograph.store.migrate import migrate

_V2_TABLES = frozenset(
    {
        "scan_meta",
        "entries",
        "issues",
        "duplicate_groups",
        "duplicate_members",
        "annotations",
        "vocab",
        "entry_tags",
        "entry_links",
    }
)

_V3_TABLES = frozenset(
    {
        "changes_staging",
        "change_events",
        "change_narratives",
    }
)


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def test_schema_tables(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    migrate(db, repo_root=tmp_path)
    conn = sqlite3.connect(db)
    try:
        assert _V2_TABLES.issubset(_tables(conn))
    finally:
        conn.close()


def test_user_version(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    migrate(db)
    conn = sqlite3.connect(db)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 5
    finally:
        conn.close()


def test_migrate_creates_db(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    assert not db.exists()
    migrate(db, repo_root=tmp_path)
    assert db.is_file()


def test_migrate_idempotent(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    migrate(db)
    migrate(db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    finally:
        conn.close()


def test_migrate_creates_parent(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    migrate(db)
    assert (tmp_path / ".repograph").is_dir()


def test_migrate_closes_connection(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    migrate(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute("SELECT 1").fetchone()
    finally:
        conn.close()


def test_migrate_v2_fresh(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    migrate(db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert _V2_TABLES.issubset(_tables(conn))
    finally:
        conn.close()


def test_migrate_v2_upgrade(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    schema_v1 = (
        importlib.resources.files("repograph.store")
        .joinpath("schema.sql")
        .read_text(encoding="utf-8")
    )
    conn = sqlite3.connect(db)
    try:
        conn.executescript(schema_v1)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    finally:
        conn.close()

    migrate(db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert "entries" in _tables(conn)
    finally:
        conn.close()


def test_migrate_v2_idempotent(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    migrate(db)
    migrate(db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    finally:
        conn.close()


def test_migrate_v3_tables(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    migrate(db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert _V3_TABLES.issubset(_tables(conn))
    finally:
        conn.close()


def test_migrate_v3_scan_meta_column(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    migrate(db)
    conn = sqlite3.connect(db)
    try:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(scan_meta)")
        }
        assert "last_changes_finalize_at" in columns
    finally:
        conn.close()


def test_migrate_v3_upgrade_from_v2(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    schema_v1 = (
        importlib.resources.files("repograph.store")
        .joinpath("schema.sql")
        .read_text(encoding="utf-8")
    )
    schema_v2 = (
        importlib.resources.files("repograph.store")
        .joinpath("schema_v2.sql")
        .read_text(encoding="utf-8")
    )
    conn = sqlite3.connect(db)
    try:
        conn.executescript(schema_v1)
        conn.executescript(schema_v2)
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    finally:
        conn.close()

    migrate(db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert _V3_TABLES.issubset(_tables(conn))
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(scan_meta)")
        }
        assert "last_changes_finalize_at" in columns
    finally:
        conn.close()


def test_migrate_v4_views_exist(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    migrate(db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        views = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            )
        }
        assert "v_label_queue" in views
        assert "v_effective" in views
        assert "v_label_queue_actionable" in views
        statuses = {
            row[0]
            for row in conn.execute(
                "SELECT code FROM vocab WHERE kind = 'label_status'"
            )
        }
        assert statuses >= {"pending", "labeled", "failed", "stale"}
    finally:
        conn.close()


def test_no_views_v2(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    schema_v1 = (
        importlib.resources.files("repograph.store")
        .joinpath("schema.sql")
        .read_text(encoding="utf-8")
    )
    schema_v2 = (
        importlib.resources.files("repograph.store")
        .joinpath("schema_v2.sql")
        .read_text(encoding="utf-8")
    )
    conn = sqlite3.connect(db)
    try:
        conn.executescript(schema_v1)
        conn.executescript(schema_v2)
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    finally:
        conn.close()

    conn = sqlite3.connect(db)
    try:
        views = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            )
        }
        assert "v_label_queue" not in views
        assert "v_effective" not in views
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    finally:
        conn.close()


def test_migrate_v5_semantic_objects_exists(tmp_path) -> None:
    db = tmp_path / ".repograph" / "db.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    schema_v1 = (
        importlib.resources.files("repograph.store")
        .joinpath("schema.sql")
        .read_text(encoding="utf-8")
    )
    schema_v2 = (
        importlib.resources.files("repograph.store")
        .joinpath("schema_v2.sql")
        .read_text(encoding="utf-8")
    )
    schema_v3 = (
        importlib.resources.files("repograph.store")
        .joinpath("schema_v3.sql")
        .read_text(encoding="utf-8")
    )
    schema_v4 = (
        importlib.resources.files("repograph.store")
        .joinpath("schema_v4.sql")
        .read_text(encoding="utf-8")
    )
    conn = sqlite3.connect(db)
    try:
        conn.executescript(schema_v1)
        conn.executescript(schema_v2)
        conn.executescript(schema_v3)
        conn.executescript(schema_v4)
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    finally:
        conn.close()

    migrate(db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert "semantic_objects" in _tables(conn)
        views = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            )
        }
        assert "v_sem_issue_clusters" in views
    finally:
        conn.close()
