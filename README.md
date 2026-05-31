# Repograph

**CLI + agent playbook** for a local, metadata-first repository map: structure, health issues, semantic labels, change narratives, and ONNX-backed project meanings — built for Cursor and similar agents.

- **Product context:** [.planning/PROJECT.md](.planning/PROJECT.md)
- **GSD roadmap:** [.planning/ROADMAP.md](.planning/ROADMAP.md)
- **Archived reference prototype:** [archive/reference-prototype/](archive/reference-prototype/)

## Status

Phase 2: `repograph scan` writes metadata to `.repograph/db.sqlite`; `config init` / `config apply` manage neutral `repograph.yaml`. Phase 3 adds **`repograph export`** (regenerates `.repograph/repograph.md` from SQLite) and **`repograph refresh`** (rescan that preserves annotations). Changes journal and semantic search ship in later phases. **Phase 6** adds semantic search via **[FastEmbed](https://github.com/qdrant/fastembed)** (local ONNX embeddings, not PyTorch in the CLI).

## Quickstart

**Prerequisites:** Python 3.11+ (CI uses 3.12). [uv](https://docs.astral.sh/uv/) is recommended.

Clone the **`repograph`** repository, then from the project root:

### Install (uv — primary)

```powershell
uv sync --locked
```

This installs locked dependencies and the editable `repograph` console script into `.venv`. You do not need a separate `pip install -e .` on this path.

### Install (pip — alternative)

If you are not using uv, create and activate a virtual environment, then:

```powershell
pip install -e .
```

### Run

```powershell
uv run repograph --help
uv run repograph doctor
```

After activating `.venv`, you can run `repograph --help` and `repograph doctor` directly.

Optional: set `REPOGRAPH_ONNX_MODEL` to a local `.onnx` file path for an extra doctor PASS row (load + shape check only; no inference until Phase 6). Production embeddings will use **FastEmbed** — see `.planning/research/STACK.md`.

### Scan and config (Phase 2)

From a target repository root (try the bundled fixture):

```powershell
cd tests\fixtures\mini-lab
uv run repograph scan
uv run repograph config init
# optional: edit .repograph\repograph.yaml
uv run repograph config apply
uv run repograph scan
```

Artifacts: **`.repograph/db.sqlite`** (canonical metadata; no file bodies) and **`.repograph/repograph.yaml`**. The scan command exits **1** if any issue has severity `error`; warnings are reported but non-fatal.

### Export & refresh (Phase 3)

After the first scan (and optional config apply), use **refresh** when annotations exist and you need an updated tree without losing them; use **scan** for a cold database or first run.

```powershell
cd tests\fixtures\mini-lab
uv run repograph scan
uv run repograph config init
uv run repograph config apply
uv run repograph refresh
uv run repograph export
```

- **`repograph refresh`** — rescan metadata into `.repograph/db.sqlite` while keeping annotation rows.
- **`repograph export`** — write **`.repograph/repograph.md`** from SQLite (optional `--output PATH`). Markdown is regenerated on every export; **SQLite remains canonical** (D-04).

### Change journal (Phase 4)

After scan, record git edits into staging and check hook-friendly status:

```powershell
cd tests\fixtures\mini-lab
uv run repograph scan
uv run repograph changes ingest
uv run repograph changes status
```

**Editor hook** (save / post-commit) — call ingest so agents see coalesced paths:

```powershell
uv run repograph changes ingest
```

**Pre-commit** (warn-only; does not block by default):

```yaml
- repo: local
  hooks:
    - id: repograph-changes-status
      name: repograph changes status
      entry: uv run repograph changes status
      language: system
      pass_filenames: false
```

Use **`repograph changes status --strict`** when you want a non-zero exit if staging is non-empty (same idea as `doctor --strict`). Default CI uses warn-only status, not `--strict`.

Prepare/finalize flow: `changes prepare` → agent JSON → `changes finalize` (optional `--export` to refresh `.repograph/repograph.md`).

### Label batches (Phase 5)

Declare project vocab, export an actionable queue as JSON, apply agent labels in one transaction. Contract: [docs/label-batch.md](docs/label-batch.md) (separate from change-journal finalize JSON).

```powershell
cd tests\fixtures\mini-lab
uv run repograph scan
uv run repograph config init
uv run repograph config apply
uv run repograph label vocab-apply -f ..\..\fixtures\label-vocab.json
uv run repograph label export --limit 5
uv run repograph label apply-batch -f ..\..\fixtures\label-batch-apply.json --export
```

Successful `apply-batch` (non–dry-run) and `changes finalize` automatically run **`repograph semantic rebuild`** unless you pass **`--no-semantic-rebuild`** (use that flag in CI and fast tests).

### Semantic layer (Phase 6)

Local semantic search uses **[FastEmbed](https://github.com/qdrant/fastembed)** (ONNX). Default embedding model: **`BAAI/bge-small-en-v1.5`**.

Override via `repograph.yaml`:

```yaml
semantic:
  embedding_model: BAAI/bge-small-en-v1.5
```

Or environment variable **`REPOGRAPH_EMBEDDING_MODEL`**.

```powershell
cd tests\fixtures\mini-lab
uv run repograph scan
uv run repograph config init
uv run repograph config apply
uv run repograph semantic rebuild
uv run repograph semantic query "authentication domain" --limit 5
```

- **`repograph semantic rebuild`** — embed domains, labeled entries, narratives, and issue clusters into `.repograph/db.sqlite`.
- **`repograph semantic query`** — JSON results ranked by cosine similarity (sensitive paths excluded).

**Cache:** set **`FASTEMBED_CACHE_PATH`** to a directory where ONNX models are pre-downloaded (offline/air-gapped). **`repograph doctor`** reports cache status as WARN when the model is missing; **`semantic rebuild`** / **`semantic query`** fail with a clear error until the model is available.

**Automation:** pass **`--no-semantic-rebuild`** on `changes finalize` and `label apply-batch` in CI so runners do not fetch models.

### Agent workflow (Phase 7)

For Cursor and similar agents, print the full playbook once per session:

```powershell
uv run repograph agent-guide
```

Paste stdout into agent context (or use **`--output PATH`** to write a file). The guide is token-budgeted; deep detail stays in **`repograph <cmd> --help`** and this README.

- **Optional Cursor hooks** — copy-paste templates under [docs/cursor/](docs/cursor/README.md): session start runs **`changes ingest`** then **`changes status`** (warn-not-block by default; **`--strict`** is opt-in).
- **First end-to-end cycle** — use [tests/fixtures/mini-lab](tests/fixtures/mini-lab): `scan` → `config init` / `apply` → optional `label vocab-apply` → `changes ingest` → `changes status` → agent work → `changes finalize` (pass **`--no-semantic-rebuild`** in CI) → `export`.
- **Canonical store** — **`.repograph/db.sqlite`** holds metadata; **`.repograph/repograph.md`** is regenerated by **`export`**.
- **Label batches** — JSON contract: [docs/label-batch.md](docs/label-batch.md) (separate from change-journal finalize JSON).

### Test

```powershell
uv run pytest -q
```

## GSD (Get Shit Done)

```powershell
npx @opengsd/gsd-core@latest --cursor --local
```

Workflow: discuss → plan → execute → verify. Config: [.planning/config.json](.planning/config.json).

## Rename checkout folder (optional)

If your clone is still named `project-inventory`:

```powershell
cd G:\GitHub
Rename-Item project-inventory repograph
```

After adding a GitHub remote: `gh repo rename repograph` (or rename in GitHub Settings → General).
