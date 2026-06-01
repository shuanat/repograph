PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Vocabulary (empty in Phase 2 — seed data deferred to Phase 5)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vocab (
    kind TEXT NOT NULL,
    code TEXT NOT NULL,
    label_ru TEXT,
    sort_order INTEGER DEFAULT 0,
    PRIMARY KEY (kind, code)
);

-- ---------------------------------------------------------------------------
-- Phase 1: filesystem entries
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entries (
    path_norm TEXT PRIMARY KEY,
    entry_kind TEXT NOT NULL CHECK (entry_kind IN ('file', 'directory')),
    parent_path_norm TEXT,
    depth INTEGER NOT NULL,
    name TEXT NOT NULL,
    present INTEGER NOT NULL DEFAULT 1,
    size_bytes INTEGER,
    extension TEXT,
    mtime_utc TEXT,
    sha256 TEXT,
    is_binary INTEGER DEFAULT 0,
    is_gitignored INTEGER DEFAULT 0,
    is_dot_git INTEGER DEFAULT 0,
    is_sensitive INTEGER DEFAULT 0,
    git_status TEXT,
    domain_auto TEXT,
    role_auto TEXT,
    legacy_auto INTEGER DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entries_parent ON entries(parent_path_norm);
CREATE INDEX IF NOT EXISTS idx_entries_depth ON entries(depth);
CREATE INDEX IF NOT EXISTS idx_entries_domain ON entries(domain_auto);
CREATE INDEX IF NOT EXISTS idx_entries_present ON entries(present);

-- ---------------------------------------------------------------------------
-- Phase 2: LLM annotations (empty DDL — populated in Phase 5+)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS annotations (
    path_norm TEXT PRIMARY KEY REFERENCES entries(path_norm),
    purpose TEXT,
    belongs_to TEXT,
    folder_kind TEXT,
    file_kind TEXT,
    lifecycle TEXT,
    operational_status TEXT,
    content_summary TEXT,
    structure_zone TEXT,
    target_path_norm TEXT,
    target_name TEXT,
    target_belongs_to TEXT,
    action_planned TEXT,
    restructure_wave TEXT,
    priority TEXT,
    effort TEXT,
    action_confidence TEXT,
    canonical_path_norm TEXT,
    duplicate_kind TEXT DEFAULT 'none',
    keep_reason TEXT,
    risk_level TEXT,
    blocks_restructure TEXT,
    runtime_touchpoints TEXT,
    move_group_id TEXT,
    repo_fit TEXT,
    git_policy TEXT,
    applies_to_descendants INTEGER DEFAULT 0,
    notes TEXT,
    restructure_notes TEXT,
    label_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (label_status IN ('pending', 'labeled', 'failed', 'stale')),
    source TEXT,
    model TEXT,
    prompt_version TEXT,
    labeled_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_annotations_status ON annotations(label_status);
CREATE INDEX IF NOT EXISTS idx_annotations_action ON annotations(action_planned);

CREATE TABLE IF NOT EXISTS entry_tags (
    path_norm TEXT NOT NULL REFERENCES entries(path_norm),
    tag TEXT NOT NULL,
    PRIMARY KEY (path_norm, tag)
);

CREATE TABLE IF NOT EXISTS entry_links (
    from_path TEXT NOT NULL REFERENCES entries(path_norm),
    to_path TEXT NOT NULL REFERENCES entries(path_norm),
    link_type TEXT NOT NULL,
    PRIMARY KEY (from_path, to_path, link_type)
);

-- ---------------------------------------------------------------------------
-- Scan-derived issues and duplicates
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    severity TEXT NOT NULL,
    code TEXT NOT NULL,
    path_norm TEXT,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_type TEXT NOT NULL DEFAULT 'content',
    sha256 TEXT NOT NULL UNIQUE,
    member_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS duplicate_members (
    group_id INTEGER NOT NULL REFERENCES duplicate_groups(id),
    path_norm TEXT NOT NULL REFERENCES entries(path_norm),
    PRIMARY KEY (group_id, path_norm)
);
