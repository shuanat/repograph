# Product vision — agent-ready repository map

Draft for turning `tools/project-inventory` into a reusable kit for Cursor and similar AI agents.  
**Not** positioning as a «restructure-only» tool; large refactors are one strong use case among others.

## One-liner

**Local structured map of a repository for AI agents** — paths, domains, health issues, optional semantic labels — **without** storing file contents or pulling secrets into the prompt.

## Problem

Large mono-repos (infra, platform, docs-as-code, scripts) are hard for humans and agents:

- Context windows do not fit «the whole tree».
- Semantic search answers _where is X_, not _how is the repo organized_ or _what is systematically wrong_.
- Docs drift from code; sensitive paths are easy to leak into chat logs.
- Ad-hoc `grep` and explorer views do not produce a **stable, reusable** artifact for multi-step agent work.

## What this is

| Layer                | Role                                                                                                            |
| -------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Scan**             | Walk the repo; SQLite DB of entries (file/dir metadata, git status, domain/role hints, sha256 for small files). |
| **Issues**           | Automated checks: broken markdown links, legacy zones, orphan root files, duplicates, etc.                      |
| **Summary**          | Human/agent-readable report (`export_summary`) with workspace vs `.git` file counts.                            |
| **Label (optional)** | Batches exported for an agent; semantic fields (purpose, `keep`/`move`/…) applied back into the DB.             |

The agent workflow: **scan once → work from summary + targeted batches**, not from raw directory listing.

## What this is not

- Not a replacement for IDE/codebase semantic index or LSP.
- Not RAG over source code (no embeddings of file bodies in v1).
- Not a hosted SaaS or «always-on» cloud catalog (local-first).
- Not tied to a single host (Proxmox/K8s); homelab vocab in `classify.py` today is **instance config**, not product definition.

## Use cases (beyond restructure)

| Scenario                       | Value                                                                              |
| ------------------------------ | ---------------------------------------------------------------------------------- |
| **Onboarding**                 | Domains, top-level layout, where docs vs manifests vs scripts live.                |
| **Feature placement**          | «Where should service X live?» using domains/roles, not guesswork.                 |
| **Documentation health**       | Broken internal links, stale path references.                                      |
| **Security hygiene**           | Flag sensitive paths; exclude from labeling/export.                                |
| **Duplicate / parallel trees** | Same basename or content hash in multiple places.                                  |
| **Agent context budgeting**    | Ship `project-inventory-summary.md` + small JSON batches instead of huge trees.    |
| **Large refactors**            | Label backlog with `move`/`archive` — **optional mode**, not the product category. |

## Fit for Cursor and similar agents

**Today (in-repo prototype):**

- Shell: `scan.py`, `export_summary.py`, `label.py` (+ `autolabel_*` helpers).
- Agent reads `prompts/label-entry.md` and labeled JSON batches.
- Cursor rules/skills can wrap: «run inventory before a big task».

**Product-shaped delivery (target):**

1. **CLI** — `inventory scan`, `inventory summary`, `inventory queue` (any repo).
2. **`inventory.yaml`** — top-level dirs, domains, legacy prefixes, sensitive globs (replaces hardcoded homelab lists).
3. **Cursor Skill** — fixed playbook: scan → read summary → export batch → apply labels.
4. **Optional MCP** — `list_issues`, `next_batch`, `get_entry` so the agent does not touch SQLite directly.

## Differentiation

| Tool class           | Typical question                                                                                    |
| -------------------- | --------------------------------------------------------------------------------------------------- |
| IDE / codebase index | «Find references to symbol X»                                                                       |
| Dependency graph     | «What imports what»                                                                                 |
| **This inventory**   | «What exists, how is it grouped, what is structurally unhealthy, what should the agent tackle next» |

## Current state vs vision

| Area           | Now (`home-network-lab`)                                    | Product MVP                                      |
| -------------- | ----------------------------------------------------------- | ------------------------------------------------ |
| Config         | `classify.py` homelab defaults                              | `inventory.yaml` per repo                        |
| Output         | `project-inventory.db` (gitignored)                         | Same; documented schema                          |
| Issues         | Tuned after restructure (archive skips, directory links, …) | Pluggable rules                                  |
| Labeling       | `v_restructure_backlog` naming                              | Neutral «action backlog» + optional migrate mode |
| Packaging      | Under `tools/project-inventory/`                            | Separate repo or installable package             |
| Agent contract | Ad hoc JSON batches                                         | Versioned batch schema + skill                   |

## Suggested MVP (2–3 focused iterations)

1. **Neutral config** — extract `EXPECTED_TOPLEVEL`, domains, legacy, sensitive patterns into `inventory.yaml`; keep Python as reference loader.
2. **Skill + docs** — one skill: «Inventory before large agent tasks»; three examples (onboarding, doc health, feature placement).
3. **Rescan safety** — preserve or migrate annotations across `scan` (avoid wiping labels silently).
4. **Optional MCP** — only if external users need it; CLI + skill may be enough.

**Defer:** embeddings, web UI, multi-repo org catalog, CI gates (can come later).

## Audience

- Maintainers of **large, heterogeneous** personal or small-team repos.
- Heavy **agent-assisted** editing (Cursor, Claude Code, etc.).
- Less relevant for tiny greenfield repos or repos already enforced by strict monorepo tooling.

## Name candidates

- **Repo Catalog for Agents**
- **Agent-ready repository map**
- **Structured context pack** (technical, accurate)

Avoid names that imply only migration (`restructure`, `mv`, `wave`).

## Success criteria for «product good enough»

- Another repo configures via `inventory.yaml` without forking Python.
- An agent completes a multi-step task using only summary + one batch export (measurable token/context savings is a plus).
- `warn` issues trend toward zero after intentional doc fixes; `info` issues are explainable.
- No secrets or full private keys in DB exports by default.

## Reference in this repo

Born from inventorying and restructuring `home-network-lab` (see `internal-docs/plans/REPO_STRUCTURE_TARGET.md`). That project remains the **reference implementation**, not the **product definition**.

---

_Status: idea / draft — implementation track separate from homelab restructure PRs._
