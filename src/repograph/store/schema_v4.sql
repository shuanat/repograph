-- Phase 5: label queue views + label_status vocab bootstrap (D-03, D-11)

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
            OR EXISTS (SELECT 1 FROM issues i WHERE i.path_norm = q.path_norm)
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

INSERT OR IGNORE INTO vocab (kind, code, label_ru, sort_order) VALUES
  ('label_status', 'pending', 'Pending', 10),
  ('label_status', 'labeled', 'Labeled', 20),
  ('label_status', 'failed', 'Failed', 30),
  ('label_status', 'stale', 'Stale', 40);
