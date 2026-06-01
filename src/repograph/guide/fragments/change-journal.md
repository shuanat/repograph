## Change journal

```bash
repograph changes ingest
repograph changes status
repograph changes prepare
repograph changes finalize
```

- **`ingest`** — discover git changes → `changes_staging` (run on save/session hooks).
- **`status`** — report staging; **warn-not-block** by default; **`changes status --strict`** exits 1 when staging non-empty.
- **`prepare`** — markdown brief for the agent.
- **`finalize`** — apply agent JSON; optional **`--export`**; **`--no-semantic-rebuild`** skips post-finalize embed (CI/fast loops).

Auto-rebuild: successful **`changes finalize`** and **`label apply-batch`** call **`semantic rebuild`** unless **`--no-semantic-rebuild`**.

Finalize JSON shape: `repograph changes finalize --help` (not duplicated here).

Details: `repograph changes --help`.
