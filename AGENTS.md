# Agent instructions (Repograph repo)

This repository dogfoods [Repograph](README.md). Prefer metadata over blind tree grep.

## Canonical artifacts

| Artifact | Role |
| -------- | ---- |
| `.repograph/db.sqlite` | Canonical metadata (structure, issues, labels, journal) |
| `.repograph/repograph.md` | Derived snapshot — regenerate with `uv run repograph export` |
| `.repograph/repograph.yaml` | Domains, ignore, `expected_toplevel`, semantic model |

Run from repo root: `uv run repograph …` (or activate `.venv`).

## Session workflow

1. `uv run repograph agent-guide` — playbook (once per session if needed).
2. Read `.repograph/repograph.md` — structure, health issues, domains.
3. After meaningful edits under `src/`, `tests/`, `docs/`:
   - `changes ingest` → `changes prepare` → `changes finalize` → `export`.
4. Config or layout changes: `config apply` → `refresh` → `export`.
5. Semantic search: `semantic rebuild` then `semantic query "…" . --limit 5`.

Cursor hooks (if enabled) run **ingest + status** on session start — watch stderr; default is warn-only.

## Docs

- Full workflow (humans): [docs/WORKFLOW.md](docs/WORKFLOW.md)
- Generated playbook: `repograph agent-guide`
- CLI help: `repograph <cmd> --help`
- Label batches: [docs/label-batch.md](docs/label-batch.md)
- Cursor templates: [docs/cursor/INSTALL.md](docs/cursor/INSTALL.md)
- Contributor setup: [CONTRIBUTING.md](CONTRIBUTING.md)

Detailed rules: `.cursor/rules/repograph-workflow.mdc`.
