# Agent instructions (Repograph repo)

## Repograph on this repo

We use **Repograph** here as the local inventory and change journal.

| What | Where |
| ---- | ----- |
| Playbook | `uv run repograph agent-guide` |
| Config | `.repograph/repograph.yaml` |
| Canonical DB | `.repograph/db.sqlite` (gitignored) |
| Export snapshot | `.repograph/repograph.md` |
| Cursor skill | `.cursor/skills/repograph/SKILL.md` |

Cursor **hooks** (ingest + warn-only status) are enabled via `.cursor/hooks.json`.

**Cursor rule:** `.cursor/rules/repograph-workflow.mdc` (`alwaysApply`) — when and in which order to run Repograph commands.

After substantive work: **ingest → finalize (JSON) → export**. Do not edit `repograph.md` by hand.

## GSD planning (local only)

GSD/SDLC artifacts live in `.planning/` and `.cursor/get-shit-done/` — **not** pushed to the public GitHub repo. See `docs/PUBLIC-REPOSITORY.md`.
