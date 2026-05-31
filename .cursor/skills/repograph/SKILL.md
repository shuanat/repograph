---
name: repograph
description: Use Repograph on this repo — agent playbook, change journal, semantic query. Run when editing inventory, scan, changes, labels, or semantic layers.
---

# Repograph (this repo)

Canonical data: **`.repograph/db.sqlite`**; snapshot: **`.repograph/repograph.md`** (regenerate only via `export`).

## Start of session

1. Run **`uv run repograph agent-guide`** (or use Cursor hooks for ingest + status).
2. If staging is non-empty, run **`uv run repograph changes prepare`** or finalize.

## After meaningful edits

1. **`uv run repograph changes ingest .`**
2. **`uv run repograph changes finalize .`** with agent JSON (`--no-semantic-rebuild` for fast loops).
3. **`uv run repograph export .`**

## Semantic

- **`uv run repograph semantic query "…" . --limit 5`** when the model is cached.

## Do not

- Hand-edit **`.repograph/repograph.md`**
- Grep the whole tree when **`semantic query`** or **export** suffices
