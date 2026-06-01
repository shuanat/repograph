# Documentation index

This folder holds Repograph's public documentation. The table below lists every
file under `docs/` with its purpose and primary audience.

| Path | Purpose | Audience |
| ---- | ------- | -------- |
| [WORKFLOW.md](WORKFLOW.md) | Human-readable end-to-end workflow: setup, daily loop, change journal, label batches, semantic search, hooks. | human / agent |
| [label-batch.md](label-batch.md) | JSON contract for exporting and applying label batches. | agent / maintainer |
| [cursor/INSTALL.md](cursor/INSTALL.md) | How to install the optional Cursor hooks and skill templates. | human / agent |

For installation, features, and quickstart, see the root [README.md](../README.md).
For the agent entry point, see [AGENTS.md](../AGENTS.md). The generated playbook is
available any time via `uv run repograph agent-guide`.
