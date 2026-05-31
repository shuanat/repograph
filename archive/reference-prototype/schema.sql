PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

-- ---------------------------------------------------------------------------
-- Vocabulary (allowed codes for LLM annotations)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vocab (
    kind TEXT NOT NULL,
    code TEXT NOT NULL,
    label_ru TEXT,
    sort_order INTEGER DEFAULT 0,
    PRIMARY KEY (kind, code)
);

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
-- Phase 2: LLM annotations
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

-- ---------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_label_queue AS
SELECT
    e.path_norm,
    e.entry_kind,
    e.depth,
    e.name,
    e.domain_auto,
    e.role_auto,
    e.legacy_auto,
    COALESCE(a.label_status, 'pending') AS label_status
FROM entries e
LEFT JOIN annotations a ON a.path_norm = e.path_norm
WHERE e.present = 1
  AND e.is_sensitive = 0
  AND e.is_dot_git = 0
  AND (a.label_status IS NULL OR a.label_status IN ('pending', 'failed'))
ORDER BY e.depth, e.entry_kind DESC, e.path_norm;

-- Actionable subset: all unlabeled directories; files only when not covered by
-- parent applies_to_descendants or when legacy/issue/duplicate/orphan applies.
CREATE VIEW IF NOT EXISTS v_label_queue_actionable AS
SELECT
    q.path_norm,
    q.entry_kind,
    q.depth,
    q.name,
    q.domain_auto,
    q.role_auto,
    q.legacy_auto,
    q.label_status
FROM v_label_queue q
JOIN entries e ON e.path_norm = q.path_norm
LEFT JOIN v_effective ve ON ve.path_norm = q.path_norm
WHERE q.entry_kind = 'directory'
   OR (
        q.entry_kind = 'file'
        AND (
            ve.inherited_from IS NULL
            OR e.legacy_auto = 1
            OR EXISTS (
                SELECT 1 FROM issues i
                WHERE i.path_norm = q.path_norm
                  AND (
                      i.code IN (
                          'OPENVAS_PARALLEL_TREE',
                          'ORPHAN_ROOT_FILE',
                          'BROKEN_MD_LINK'
                      )
                      OR i.code LIKE 'LEGACY%'
                  )
            )
            OR EXISTS (
                SELECT 1 FROM duplicate_members dm WHERE dm.path_norm = q.path_norm
            )
            OR NOT EXISTS (
                SELECT 1 FROM annotations pa
                WHERE pa.path_norm = e.parent_path_norm
                  AND pa.label_status = 'labeled'
                  AND pa.applies_to_descendants = 1
            )
        )
    );

CREATE VIEW IF NOT EXISTS v_effective AS
WITH RECURSIVE ancestors AS (
    SELECT
        e.path_norm,
        e.parent_path_norm,
        e.path_norm AS current_path,
        0 AS lvl
    FROM entries e
    UNION ALL
    SELECT
        a.path_norm,
        p.parent_path_norm,
        p.path_norm,
        a.lvl + 1
    FROM ancestors a
    JOIN entries p ON p.path_norm = a.parent_path_norm
    WHERE a.parent_path_norm IS NOT NULL AND a.lvl < 50
),
inherited AS (
    SELECT
        anc.path_norm AS child_path,
        ann.path_norm AS inherited_from,
        ann.purpose,
        ann.belongs_to,
        ann.folder_kind,
        ann.file_kind,
        ann.lifecycle,
        ann.operational_status,
        ann.structure_zone,
        ann.action_planned,
        anc.lvl,
        ROW_NUMBER() OVER (
            PARTITION BY anc.path_norm
            ORDER BY anc.lvl ASC
        ) AS rn
    FROM ancestors anc
    JOIN annotations ann ON ann.path_norm = anc.current_path
    WHERE ann.applies_to_descendants = 1
      AND ann.label_status = 'labeled'
      AND ann.purpose IS NOT NULL
      AND anc.lvl > 0
)
SELECT
    e.*,
    a.purpose AS purpose_explicit,
    a.belongs_to AS belongs_to_explicit,
    a.folder_kind,
    a.file_kind,
    a.lifecycle AS lifecycle_explicit,
    a.operational_status AS operational_status_explicit,
    a.structure_zone AS structure_zone_explicit,
    a.action_planned AS action_planned_explicit,
    a.label_status,
    i.inherited_from,
    COALESCE(a.purpose, i.purpose) AS effective_purpose,
    COALESCE(a.belongs_to, i.belongs_to) AS effective_belongs_to,
    COALESCE(a.lifecycle, i.lifecycle) AS effective_lifecycle,
    COALESCE(a.operational_status, i.operational_status) AS effective_operational_status,
    COALESCE(a.structure_zone, i.structure_zone) AS effective_structure_zone,
    COALESCE(a.action_planned, i.action_planned) AS effective_action_planned
FROM entries e
LEFT JOIN annotations a ON a.path_norm = e.path_norm
LEFT JOIN inherited i ON i.child_path = e.path_norm AND i.rn = 1;

CREATE VIEW IF NOT EXISTS v_restructure_backlog AS
SELECT
    a.path_norm,
    e.entry_kind,
    ve.effective_purpose,
    ve.effective_belongs_to,
    a.action_planned,
    a.target_path_norm,
    a.restructure_wave,
    a.priority,
    a.risk_level,
    a.effort,
    a.canonical_path_norm,
    a.move_group_id,
    a.restructure_notes
FROM annotations a
JOIN entries e ON e.path_norm = a.path_norm
JOIN v_effective ve ON ve.path_norm = a.path_norm
WHERE a.label_status = 'labeled'
  AND a.action_planned NOT IN ('keep', 'none')
  AND a.action_planned IS NOT NULL
ORDER BY
    CASE a.restructure_wave
        WHEN 'wave0_safe' THEN 0
        WHEN 'wave1_scripts' THEN 1
        WHEN 'wave2_manifests' THEN 2
        WHEN 'wave3_deployed' THEN 3
        WHEN 'blocked' THEN 9
        ELSE 5
    END,
    a.priority,
    a.path_norm;

CREATE VIEW IF NOT EXISTS v_move_groups AS
SELECT move_group_id, COUNT(*) AS member_count, GROUP_CONCAT(path_norm, '; ') AS paths
FROM annotations
WHERE move_group_id IS NOT NULL AND label_status = 'labeled'
GROUP BY move_group_id;

CREATE VIEW IF NOT EXISTS v_duplicates_unresolved AS
SELECT path_norm, duplicate_kind, canonical_path_norm
FROM annotations
WHERE duplicate_kind IS NOT NULL
  AND duplicate_kind != 'none'
  AND (canonical_path_norm IS NULL OR canonical_path_norm = '')
  AND label_status = 'labeled';

CREATE VIEW IF NOT EXISTS v_blocked AS
SELECT ve.path_norm, a.restructure_wave, a.risk_level, a.blocks_restructure
FROM v_effective ve
JOIN annotations a ON a.path_norm = ve.path_norm
WHERE a.label_status = 'labeled'
  AND (a.restructure_wave = 'blocked' OR a.risk_level = 'high');

CREATE VIEW IF NOT EXISTS v_out_of_scope AS
SELECT path_norm, repo_fit, git_policy, purpose, action_planned
FROM annotations
WHERE label_status = 'labeled'
  AND repo_fit IN ('out_of_scope', 'relocate_out', 'candidate_remove');

CREATE VIEW IF NOT EXISTS v_by_domain AS
SELECT domain_auto, entry_kind, COUNT(*) AS cnt, SUM(COALESCE(size_bytes, 0)) AS total_bytes
FROM entries
WHERE present = 1
GROUP BY domain_auto, entry_kind;
