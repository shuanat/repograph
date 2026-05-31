## Quick start

Repograph is a **local CLI** for repository metadata, change staging, label batches, and semantic search. Canonical data lives in **`.repograph/db.sqlite`**; **`.repograph/repograph.md`** is a derived snapshot.

From a repository root:

```bash
repograph doctor
repograph scan
repograph config init
# edit .repograph/repograph.yaml
repograph config apply
repograph export
```

Use **`repograph agent-guide`** (this document) for the full agent workflow. Deep detail: `repograph <cmd> --help` and [README.md](README.md).
