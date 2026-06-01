# Repograph

**CLI + agent playbook** for a local, metadata-first repository map: structure, health issues, semantic labels, change narratives, and ONNX-backed project meanings — built for Cursor and similar agents.

## Features (v1.0)

- **Scan & config** — metadata in `.repograph/db.sqlite`; neutral `repograph.yaml` via `config init` / `apply`
- **Export & refresh** — `repograph.md` from SQLite; rescan preserves annotations
- **Change journal** — ingest → prepare → finalize (JSON) → permanent events + narratives
- **Label batches** — export/apply JSON annotations ([docs/label-batch.md](docs/label-batch.md))
- **Semantic layer** — **[FastEmbed](https://github.com/qdrant/fastembed)** (local ONNX) rebuild + `semantic query`
- **Agent playbook** — `repograph agent-guide` + [docs/cursor/](docs/cursor/) hook templates

## Documentation

- [docs/README.md](docs/README.md) — documentation index (workflow, label batches, hooks)
- [AGENTS.md](AGENTS.md) — agent entry point for working in this repo
- [CONTRIBUTING.md](CONTRIBUTING.md) — local setup, tests, and contribution rules
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — community standards

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

Optional: set `REPOGRAPH_ONNX_MODEL` to a local `.onnx` file path for an extra doctor check (load + shape only). Semantic commands use **FastEmbed** (default `BAAI/bge-small-en-v1.5`).

### Scan and config

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

### Export & refresh

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

### Change journal

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

### Label batches

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

### Semantic layer

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

### Agent workflow

For Cursor and similar agents, print the full playbook once per session:

```powershell
uv run repograph agent-guide
```

Paste stdout into agent context (or use **`--output PATH`** to write a file). The guide is token-budgeted; deep detail stays in **`repograph <cmd> --help`** and this README.

- **Full workflow (humans)** — [docs/WORKFLOW.md](docs/WORKFLOW.md): setup, daily loop, change journal vs. label batches, semantic search, hooks.
- **Optional Cursor hooks** — copy-paste templates under [docs/cursor/](docs/cursor/INSTALL.md): session start runs **`changes ingest`** then **`changes status`** (warn-not-block by default; **`--strict`** is opt-in).
- **First end-to-end cycle** — use [tests/fixtures/mini-lab](tests/fixtures/mini-lab): `scan` → `config init` / `apply` → optional `label vocab-apply` → `changes ingest` → `changes status` → agent work → `changes finalize` (pass **`--no-semantic-rebuild`** in CI) → `export`.
- **Canonical store** — **`.repograph/db.sqlite`** holds metadata; **`.repograph/repograph.md`** is regenerated by **`export`**.
- **Label batches** — JSON contract: [docs/label-batch.md](docs/label-batch.md) (separate from change-journal finalize JSON).

### Test

```powershell
uv run pytest -q
```

### Using Repograph on this repository

The bundled **[mini-lab](tests/fixtures/mini-lab)** fixture includes a committed `repograph.yaml` for trying the full CLI cycle. Optional **[Cursor hooks](docs/cursor/INSTALL.md)** and [AGENTS.md](AGENTS.md) support agent workflows in your own checkout.

## Rename checkout folder (optional)

If your clone is still named `project-inventory`:

```powershell
cd G:\GitHub
Rename-Item project-inventory repograph
```

Public repo: [github.com/shuanat/repograph](https://github.com/shuanat/repograph).
