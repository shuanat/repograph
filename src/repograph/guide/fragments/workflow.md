## Canonical agent workflow

Follow this order unless you have a deliberate reason to skip a step:

1. **`repograph doctor`** — once per machine/repo setup (`doctor --strict` for CI discipline).
2. **`repograph scan`** (cold DB) or **`repograph refresh`** (preserve annotations).
3. **`repograph config init`** → edit `.repograph/repograph.yaml` → **`repograph config apply`**.
4. **`repograph label vocab-apply`** when using project label vocab.
5. **`repograph changes ingest`** — coalesce git edits into staging.
6. **`repograph changes status`** — warn if staging non-empty (default exit 0; use **`--strict`** to fail).
7. **Agent work** — label export/apply-batch, edits, prepare narratives (`changes prepare`).
8. **`repograph changes finalize`** — commit staging + narratives (see **`--no-semantic-rebuild`**, **`--no-export`**).
9. **`repograph semantic rebuild`** — first run, after model change, or rely on auto-rebuild after finalize/apply-batch.
10. **`repograph semantic query "..."`** — ranked meanings (JSON on stdout).
11. **`repograph export`** — refresh `.repograph/repograph.md` as a cheap read-only snapshot.
