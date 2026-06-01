## Label batches

```bash
repograph label vocab-apply -f path/to/vocab.json
repograph label export --limit 20
repograph label apply-batch -f path/to/batch.json
repograph label print-prompt
```

- Export/apply use **JSON on stdout/stdin** contracts — do not guess field names.
- Full batch schema: **`docs/label-batch.md`** (repo root; not inlined here).
- **`label print-prompt`** — packaged prompt for external LLMs.

Successful **`label apply-batch`** (non–dry-run) runs **`semantic rebuild`** unless **`--no-semantic-rebuild`**.

Details: `repograph label --help`.
