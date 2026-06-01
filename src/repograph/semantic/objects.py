"""Collect semantic objects from the Repograph DB for embedding."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from repograph.config.model import RepographConfig
from repograph.semantic.text_builders import (
    build_domain_text,
    build_entry_text,
    build_issue_cluster_text,
    build_narrative_text,
)

_OBJECT_KEY_SEP = "\x1f"

_EXEMPLAR_PATHS_SQL = """
SELECT DISTINCT i.path_norm
FROM issues i
INNER JOIN entries e ON e.path_norm = i.path_norm
WHERE i.code = ?
  AND COALESCE(e.domain_auto, '') = ?
  AND e.present = 1
  AND e.is_sensitive = 0
ORDER BY i.path_norm
LIMIT 5
"""

_SEVERITY_SAMPLE_SQL = """
SELECT MIN(i.severity) AS severity_sample
FROM issues i
INNER JOIN entries e ON e.path_norm = i.path_norm
WHERE i.code = ?
  AND COALESCE(e.domain_auto, '') = ?
  AND e.present = 1
  AND e.is_sensitive = 0
"""

_ENTRIES_SQL = """
SELECT ve.path_norm, ve.entry_kind, ve.effective_purpose, ve.effective_belongs_to,
       ve.effective_lifecycle, ve.label_status
FROM v_effective ve
INNER JOIN entries e ON e.path_norm = ve.path_norm
WHERE e.present = 1
  AND e.is_sensitive = 0
  AND ve.label_status = 'labeled'
"""

_NARRATIVES_SQL = """
SELECT cn.event_id, cn.path_norm, cn.path_summary,
       ce.title, ce.summary
FROM change_narratives cn
INNER JOIN change_events ce ON ce.id = cn.event_id
INNER JOIN entries e ON e.path_norm = cn.path_norm
WHERE e.present = 1
  AND e.is_sensitive = 0
"""


@dataclass(frozen=True)
class SemanticObject:
    object_type: str
    object_key: str
    embed_text: str
    path_norm: str | None = None
    event_id: int | None = None


def _collect_domains(config: RepographConfig) -> list[SemanticObject]:
    objects: list[SemanticObject] = []
    for prefix, label in config.domains.items():
        objects.append(
            SemanticObject(
                object_type="domain",
                object_key=prefix,
                embed_text=build_domain_text(prefix, label),
            )
        )
    return objects


def _collect_entries(conn: sqlite3.Connection) -> list[SemanticObject]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(_ENTRIES_SQL).fetchall()
    objects: list[SemanticObject] = []
    for row in rows:
        path_norm = row["path_norm"]
        objects.append(
            SemanticObject(
                object_type="entry",
                object_key=path_norm,
                embed_text=build_entry_text(
                    path_norm=path_norm,
                    entry_kind=row["entry_kind"],
                    effective_purpose=row["effective_purpose"],
                    effective_belongs_to=row["effective_belongs_to"],
                    effective_lifecycle=row["effective_lifecycle"],
                    label_status=row["label_status"],
                ),
                path_norm=path_norm,
            )
        )
    return objects


def _collect_narratives(conn: sqlite3.Connection) -> list[SemanticObject]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(_NARRATIVES_SQL).fetchall()
    objects: list[SemanticObject] = []
    for row in rows:
        event_id = int(row["event_id"])
        path_norm = row["path_norm"]
        objects.append(
            SemanticObject(
                object_type="narrative",
                object_key=f"{event_id}{_OBJECT_KEY_SEP}{path_norm}",
                embed_text=build_narrative_text(
                    event_id=event_id,
                    path_norm=path_norm,
                    path_summary=row["path_summary"],
                    title=row["title"],
                    summary=row["summary"],
                ),
                path_norm=path_norm,
                event_id=event_id,
            )
        )
    return objects


def _collect_issue_clusters(conn: sqlite3.Connection) -> list[SemanticObject]:
    conn.row_factory = sqlite3.Row
    clusters = conn.execute(
        "SELECT issue_code, domain_auto, path_count FROM v_sem_issue_clusters"
    ).fetchall()
    objects: list[SemanticObject] = []
    for cluster in clusters:
        issue_code = cluster["issue_code"]
        domain_auto = cluster["domain_auto"] or ""
        path_rows = conn.execute(
            _EXEMPLAR_PATHS_SQL, (issue_code, domain_auto)
        ).fetchall()
        exemplar_paths = [r["path_norm"] for r in path_rows]
        severity_row = conn.execute(
            _SEVERITY_SAMPLE_SQL, (issue_code, domain_auto)
        ).fetchone()
        severity_sample = (
            severity_row["severity_sample"] if severity_row else None
        )
        object_key = f"{issue_code}{_OBJECT_KEY_SEP}{domain_auto}"
        objects.append(
            SemanticObject(
                object_type="issue_cluster",
                object_key=object_key,
                embed_text=build_issue_cluster_text(
                    issue_code=issue_code,
                    domain_auto=domain_auto,
                    path_count=int(cluster["path_count"]),
                    exemplar_paths=exemplar_paths,
                    severity_sample=severity_sample,
                ),
            )
        )
    return objects


def collect_semantic_objects(
    conn: sqlite3.Connection,
    repo_root: Path,
    config: RepographConfig,
) -> list[SemanticObject]:
    """Merge domain, entry, narrative, and issue_cluster objects for rebuild."""
    _ = repo_root  # reserved for future path-relative lookups
    objects: list[SemanticObject] = []
    objects.extend(_collect_domains(config))
    objects.extend(_collect_entries(conn))
    objects.extend(_collect_narratives(conn))
    objects.extend(_collect_issue_clusters(conn))
    return objects
