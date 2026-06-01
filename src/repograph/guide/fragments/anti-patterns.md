## Anti-patterns

- **Grep-the-tree** for structure/health instead of **`export`** or **`semantic query`**.
- **Hand-editing** `.repograph/repograph.md` — changes are overwritten on export; update SQLite via scan/label/finalize.
- **Inlining** batch or semantic JSON schemas in agent prompts — use **`docs/label-batch.md`** and command **`--help`**.
- **Assuming** staging blocks commits — default **`changes status`** is warn-only; opt into **`--strict`** explicitly.
