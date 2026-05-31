-- Phase 6: semantic_objects + issue cluster view (D-08, D-18)

CREATE TABLE IF NOT EXISTS semantic_objects (
    object_type TEXT NOT NULL
        CHECK (object_type IN ('domain', 'entry', 'narrative', 'issue_cluster')),
    object_key TEXT NOT NULL,
    embedding BLOB NOT NULL,
    model_id TEXT NOT NULL,
    dim INTEGER NOT NULL,
    embedded_at TEXT NOT NULL,
    source_hash TEXT,
    PRIMARY KEY (object_type, object_key)
);

CREATE INDEX IF NOT EXISTS idx_semantic_objects_model
    ON semantic_objects(model_id);

CREATE VIEW IF NOT EXISTS v_sem_issue_clusters AS
SELECT
    i.code AS issue_code,
    COALESCE(e.domain_auto, '') AS domain_auto,
    COUNT(DISTINCT i.path_norm) AS path_count
FROM issues i
INNER JOIN entries e ON e.path_norm = i.path_norm
WHERE i.path_norm IS NOT NULL
  AND e.present = 1
  AND e.is_sensitive = 0
GROUP BY i.code, COALESCE(e.domain_auto, '');
