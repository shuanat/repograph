"""Structured embed text per semantic object type (D-05)."""

from __future__ import annotations

from typing import Any


def _format_labeled_lines(fields: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in fields.items():
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        lines.append(f"{key}: {text}")
    return "\n".join(lines)


def build_domain_text(prefix: str, label: str) -> str:
    return _format_labeled_lines({"domain": prefix, "label": label})


def build_entry_text(
    *,
    path_norm: str,
    entry_kind: str | None,
    effective_purpose: str | None,
    effective_belongs_to: str | None,
    effective_lifecycle: str | None,
    label_status: str | None,
) -> str:
    return _format_labeled_lines(
        {
            "path_norm": path_norm,
            "entry_kind": entry_kind,
            "effective_purpose": effective_purpose,
            "effective_belongs_to": effective_belongs_to,
            "effective_lifecycle": effective_lifecycle,
            "label_status": label_status,
        }
    )


def build_narrative_text(
    *,
    event_id: int,
    path_norm: str,
    path_summary: str | None,
    title: str | None,
    summary: str | None,
) -> str:
    return _format_labeled_lines(
        {
            "event_id": event_id,
            "path_norm": path_norm,
            "path_summary": path_summary,
            "title": title,
            "summary": summary,
        }
    )


def build_issue_cluster_text(
    *,
    issue_code: str,
    domain_auto: str,
    path_count: int,
    exemplar_paths: list[str],
    severity_sample: str | None,
) -> str:
    exemplar = ", ".join(exemplar_paths) if exemplar_paths else None
    return _format_labeled_lines(
        {
            "issue_code": issue_code,
            "domain": domain_auto,
            "path_count": path_count,
            "exemplar_paths": exemplar,
            "severity_sample": severity_sample,
        }
    )
