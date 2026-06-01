# Repograph workflow

This is the human-readable companion to the generated agent playbook
(`uv run repograph agent-guide`). It explains what Repograph does and the order
you normally run commands in. For installation and a feature overview, start at
the root [README.md](../README.md).

## What Repograph is for

Repograph builds a **metadata-first map** of a repository: its structure, health
issues, semantic labels, and a narrative of how files change over time. It stores
that metadata — never your file contents — in a local SQLite database at
`.repograph/db.sqlite`. Agents read this map instead of grepping the whole tree.

Two artifacts matter:

- `.repograph/db.sqlite` is the **canonical store**. Everything is derived from it.
- `.repograph/repograph.md` is a **regenerated snapshot** for quick reading. Never
  edit it by hand — run `repograph export` to refresh it.

Configuration (domains, ignore rules, expected top-level layout, semantic model)
lives in `.repograph/repograph.yaml`.

## First-time setup

Run these once when you start using Repograph in a repo:

```powershell
uv run repograph doctor        # check the environment (add --strict in CI)
uv run repograph scan          # build the database from a cold start
uv run repograph config init   # write a starter repograph.yaml
# edit .repograph/repograph.yaml as needed
uv run repograph config apply  # apply config, then rescan
uv run repograph scan
```

`scan` exits non-zero only when an issue has severity `error`; warnings are
reported but never block.

## Daily agent loop

Once the database exists, a typical working session looks like this:

1. Read `.repograph/repograph.md` (or run `repograph agent-guide`) for context.
2. Record edits into staging: `repograph changes ingest`.
3. Check what is staged: `repograph changes status` (warn-only by default;
   add `--strict` to fail when staging is non-empty).
4. Do your work — edit code, run label batches, write narratives.
5. Commit the staged changes and narratives: `repograph changes finalize`
   (pass agent-supplied JSON via `--file`).
6. Refresh the snapshot: `repograph export`.

In tight loops, pass `--no-semantic-rebuild` to `finalize` so it does not
re-embed on every commit.

## Change journal vs. label batches

These are two different things and it is easy to confuse them:

- The **change journal** tracks *how files change*. You ingest git edits into
  staging, optionally write narratives describing them, then finalize them into
  permanent events. This is the `ingest → prepare → finalize` flow.
- A **label batch** is a *bulk annotation* operation. You declare a label
  vocabulary, export a queue of entries to label as JSON, and apply the agent's
  labels back in a single transaction. The JSON contract is documented in
  [label-batch.md](label-batch.md) and is separate from the finalize JSON.

## Semantic search

Repograph can embed domains, labeled entries, narratives, and issue clusters into
the database so you can search by meaning:

```powershell
uv run repograph semantic rebuild
uv run repograph semantic query "authentication domain" --limit 5
```

Embeddings use [FastEmbed](https://github.com/qdrant/fastembed) (local ONNX,
default model `BAAI/bge-small-en-v1.5`). In CI, pass `--no-semantic-rebuild` on
`finalize` and `label apply-batch` so runners do not download models.

## Cursor hooks

You can wire Repograph into Cursor so it runs `changes ingest` and `changes status`
when a session starts. The hooks are warn-only by default and never download
models. Setup is copy-paste and documented in [cursor/INSTALL.md](cursor/INSTALL.md).

## When to run `repograph agent-guide`

Run `uv run repograph agent-guide` once per agent session to print the canonical,
token-budgeted playbook. It is the generated source of truth for command order;
this document is the longer-form explanation for humans. Deep per-command detail
stays in `repograph <cmd> --help`.
