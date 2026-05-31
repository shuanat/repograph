# Reference prototype (archived)

Homelab-born **Phase 1 scan + Phase 2 label** scripts. Archived **2026-05-31** when the product was re-scoped as a packaged CLI for other users (see `.planning/PROJECT.md`).

**Codebase map** for this tree: `.planning/codebase/*.md` (paths refer to files under this directory).

## Run (historical)

```powershell
cd G:\GitHub\repograph\archive\reference-prototype
pip install -r requirements.txt
cd G:\path\to\target-repo
python ..\..\archive\reference-prototype\scan.py --root .
```

## Contents

| Path                                       | Role                          |
| ------------------------------------------ | ----------------------------- |
| `scan.py`, `schema.sql`                    | Phase 1 SQLite scan           |
| `label.py`, `prompts/`                     | Phase 2 LLM batches           |
| `classify.py`, `paths.py`, `vocab_data.py` | Auto-hints (homelab defaults) |
| `export_*.py`, `autolabel_*.py`            | Summary and heuristics        |
| `tests/fixtures/mini-lab/`                 | E2E fixture repo              |
| `PRODUCT.md`, `ORIGIN.md`                  | Pre-GSD vision notes          |

Do not extend this folder for new product features — implement in the new CLI package (roadmap in `.planning/ROADMAP.md`).
