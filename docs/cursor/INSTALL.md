# Cursor hooks and skill templates (AGT-02)

Copy-paste examples only — Repograph **never** writes into your `~/.cursor/` directory. Review scripts before enabling (untrusted repos may ship malicious `.cursor/hooks.json`).

## Install (local IDE)

1. Copy `hooks.json.example` → **`.cursor/hooks.json`** at the repository root.
2. Copy hook scripts into **`.cursor/hooks/`**:
   - Unix: `repograph-session-start.sh`, optional `repograph-session-reminder.sh` — `chmod +x`
   - Windows: use `repograph-session-start.ps1` / `repograph-session-reminder.ps1` in `hooks.json` instead of `.sh`
3. Ensure `repograph` is on PATH, or install [uv](https://docs.astral.sh/uv/) so scripts can use `uv run repograph`.

**Monorepos:** set `REPOGRAPH_ROOT` to the package root that contains `.repograph/` (overrides `git rev-parse --show-toplevel`).

## What the minimum hook does (D-10)

On **`sessionStart`** and/or **`beforeSubmitPrompt`**:

1. `repograph changes ingest` — coalesce git edits into staging
2. `repograph changes status` — **warn-only** (exit 0 if staging non-empty)

- **`beforeSubmitPrompt`** — stderr visible before the agent acts (good for staging warnings).
- **`sessionStart`** — fire-and-forget per [Cursor hooks docs](https://cursor.com/docs/agent/hooks); side effects only.

Default is **not** `--strict` (does not block the session). For CI-style discipline, edit the script and uncomment `changes status --strict`.

Session hooks **do not** call `semantic rebuild`, `changes finalize`, or download ONNX models.

## Optional end-of-turn reminder (D-11)

`hooks.json.example` includes an optional **`stop`** hook pointing at `repograph-session-reminder.sh`. It prints a stderr reminder to run **`repograph changes finalize`** (with agent JSON on stdin) and **`repograph export`**.

**v1 hooks never auto-finalize** — finalize requires agent-supplied JSON (Phase 4 contract). Remove the `stop` block from `hooks.json` if you do not want reminders.

## Finalize and semantic flags (D-12)

| Scenario | Suggested flags |
|----------|-----------------|
| Fast agent loop, defer embeddings | `repograph changes finalize --no-semantic-rebuild` |
| Finalize without refreshing markdown | omit `--export`; run `repograph export` later |
| Production / full pipeline | `finalize` with default semantic rebuild when models are installed |

Document `--no-semantic-rebuild` in your team playbook; do not enable semantic rebuild inside session-start hooks.

## Cloud agents

**Cursor cloud agents do not run project hooks** — these templates apply to **local IDE** workflows only.

## Canonical playbook

Run **`repograph agent-guide`** for the full markdown workflow (scan → config → ingest → finalize → export). Copy `repograph-skill.md.example` into `.cursor/skills/` (or your skills path) as a thin pointer to that command.

## File map

| File | Purpose |
|------|---------|
| `hooks.json.example` | Cursor hooks v1: session + optional stop reminder |
| `repograph-session-start.sh` / `.ps1` | ingest + warn-only status |
| `repograph-session-reminder.sh` / `.ps1` | optional finalize/export reminder |
| `repograph-skill.md.example` | Cursor skill wrapper (agent-guide first) |
