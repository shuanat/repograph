PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Scan metadata
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scan_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    scanned_at TEXT NOT NULL,
    repo_root TEXT NOT NULL,
    git_head TEXT,
    git_branch TEXT,
    scanner_version TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    file_count INTEGER DEFAULT 0,
    dir_count INTEGER DEFAULT 0,
    total_bytes INTEGER DEFAULT 0,
    scan_skipped_count INTEGER DEFAULT 0,
    sensitive_file_count INTEGER DEFAULT 0
);
