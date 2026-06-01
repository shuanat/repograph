PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Phase 4: change journal (v3)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS changes_staging (
    path_norm TEXT PRIMARY KEY,
    op TEXT NOT NULL CHECK (op IN ('add', 'modify', 'delete', 'rename')),
    old_path_norm TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    lines_added INTEGER DEFAULT 0,
    lines_deleted INTEGER DEFAULT 0,
    git_status TEXT
);

CREATE TABLE IF NOT EXISTS change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    finalized_at TEXT NOT NULL,
    git_head TEXT,
    git_branch TEXT
);

CREATE TABLE IF NOT EXISTS change_narratives (
    event_id INTEGER NOT NULL REFERENCES change_events(id) ON DELETE CASCADE,
    path_norm TEXT NOT NULL,
    path_summary TEXT,
    PRIMARY KEY (event_id, path_norm)
);

CREATE INDEX IF NOT EXISTS idx_change_events_finalized
    ON change_events(finalized_at);

CREATE INDEX IF NOT EXISTS idx_change_narratives_path
    ON change_narratives(path_norm);

ALTER TABLE scan_meta ADD COLUMN last_changes_finalize_at TEXT;
