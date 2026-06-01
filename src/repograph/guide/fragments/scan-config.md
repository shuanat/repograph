## Scan & config

```bash
repograph scan
repograph refresh
repograph config init
repograph config apply
```

- **`scan`** — build or replace `.repograph/db.sqlite` (metadata only; no file bodies).
- **`refresh`** — rescan while keeping annotation rows.
- **`config init`** / **`config apply`** — manage `.repograph/repograph.yaml` (ignore/sensitive globs, semantic model id).

**`scan`** exits **1** when any issue has severity `error`; warnings are non-fatal.

Details: `repograph scan --help`, `repograph config --help`.
