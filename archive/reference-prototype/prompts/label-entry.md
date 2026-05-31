# LLM labeling: project-inventory batch

You receive a JSON array of paths from `label.py export`. For each item, return one object in the **same order** with semantic fields for restructuring.

## Rules

1. Use **only** vocab codes (see `label.py vocab`). Invalid codes fail import.
2. Do **not** label sensitive paths (not in batch).
3. **Directories:** set `folder_kind`, `belongs_to`, `lifecycle`, `operational_status`, `action_planned`, `purpose`, `applies_to_descendants: 1` unless the folder is heterogeneous.
4. **Files:** label only when meaning differs from parent (duplicates, legacy singles, root orphans). Otherwise omit from output or set `action_planned: "none"` and minimal fields.
5. `action_planned`: default `keep`. Use `move`/`consolidate`/`delete`/`archive` only when confident.
6. For duplicates / openvas parallel tree: set `duplicate_kind`, `canonical_path_norm`, `keep_reason`.
7. High-risk paths (firewall, prod manifests, cron): `risk_level: "high"`, `restructure_wave: "blocked"` if unsure.
8. `label_status`: always `"labeled"` on success.

## Required fields (directory)

`path_norm`, `purpose`, `belongs_to`, `folder_kind`, `lifecycle`, `operational_status`, `action_planned`, `applies_to_descendants`, `label_status`

## Required fields (file exception)

`path_norm`, `purpose`, `belongs_to`, `file_kind`, `lifecycle`, `action_planned`, `label_status`

## If action is move/merge/delete/archive

Also: `target_path_norm` or `canonical_path_norm`, `risk_level`, `restructure_wave`

## Optional

`structure_zone`, `repo_fit`, `git_policy`, `tags` (array of strings), `notes`, `restructure_notes`, `priority`, `effort`, `action_confidence`, `move_group_id`, `runtime_touchpoints`, `blocks_restructure`

## Output

JSON array only, no markdown fence. Example:

```json
[
  {
    "path_norm": "kubernetes",
    "purpose": "Kubernetes cluster manifests, dashboards, docs, and automation.",
    "belongs_to": "kubernetes",
    "folder_kind": "domain_root",
    "lifecycle": "active",
    "operational_status": "in_use",
    "structure_zone": "infra_kubernetes",
    "action_planned": "keep",
    "applies_to_descendants": 1,
    "repo_fit": "in_scope",
    "label_status": "labeled"
  }
]
```
