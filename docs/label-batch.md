# Label batch contract

Repograph label batches are **separate** from the change journal (`repograph changes finalize`). They update **annotations** (purpose, belongs_to, lifecycle, etc.) for structural labeling, not change-event narratives.

## Workflow

1. **Declare vocab** — `repograph.yaml` `vocab:` section and/or `repograph label vocab-apply -f vocab.json`
2. **Scan** — `repograph scan` (populates `entries`)
3. **Export** — `repograph label export --limit 25` → JSON with `project_vocab` + `items`
4. **Agent** — external LLM using `repograph label print-prompt` guidance
5. **Apply** — `repograph label apply-batch -f batch.json` (optional `--dry-run`, `--export`)

## Export envelope

```json
{
  "project_vocab": [
    {
      "kind": "lifecycle",
      "code": "active",
      "label": "Active",
      "sort_order": 10
    }
  ],
  "items": [
    {
      "path_norm": "src",
      "entry_kind": "directory",
      "depth": 1,
      "name": "src",
      "child_sample": ["lib/"],
      "issues": [],
      "parent_effective": null
    }
  ]
}
```

Default queue: **actionable** (`v_label_queue_actionable`). Use `--full-queue` for the full pending queue.

## Apply payload

Only this shape is accepted:

```json
{
  "items": [
    {
      "path_norm": "src",
      "purpose": "Application source tree.",
      "belongs_to": "app",
      "folder_kind": "source",
      "lifecycle": "active",
      "operational_status": "in_use",
      "action_planned": "keep",
      "applies_to_descendants": 1,
      "label_status": "labeled"
    }
  ]
}
```

- **One transaction** — any validation error rolls back the entire batch.
- **`--dry-run`** — validates without committing.
- **Sensitive / absent paths** — rejected with exit code 1.

## CLI reference

| Command              | Purpose                                           |
| -------------------- | ------------------------------------------------- |
| `label vocab-apply`  | Merge vocab JSON into SQLite                      |
| `label vocab-list`   | Dump vocab (use when export caps `project_vocab`) |
| `label export`       | Agent batch JSON                                  |
| `label queue`        | Human/agent queue listing                         |
| `label apply-batch`  | Persist annotations                               |
| `label print-prompt` | Packaged LLM instructions                         |

Schema requires **user_version ≥ 4** (label views).
