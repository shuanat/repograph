# LLM labeling: Repograph batch

You receive JSON from `repograph label export` with `project_vocab` and `items`. Return one object per item in the **same order** using only codes from `project_vocab`.

## Rules

1. Use **only** vocab codes listed in `project_vocab`. Invalid codes fail `apply-batch`.
2. Do **not** label sensitive paths (they are excluded from export).
3. **Directories:** set `folder_kind`, `belongs_to`, `lifecycle`, `operational_status`, `action_planned`, `purpose`, `applies_to_descendants: 1` unless heterogeneous.
4. **Files:** label when meaning differs from parent; otherwise minimal fields or `action_planned: "none"`.
5. `action_planned`: default `keep` unless confident about move/consolidate/delete/archive.
6. `label_status`: always `"labeled"` on success.

## Required fields (directory)

`path_norm`, `purpose`, `belongs_to`, `folder_kind`, `lifecycle`, `operational_status`, `action_planned`, `applies_to_descendants`, `label_status`

## Required fields (file)

`path_norm`, `purpose`, `belongs_to`, `file_kind`, `lifecycle`, `action_planned`, `label_status`

## Output

JSON object: `{"items": [ ... ]}` — no markdown fence.

See `docs/label-batch.md` for the full contract (distinct from `changes finalize` JSON).
