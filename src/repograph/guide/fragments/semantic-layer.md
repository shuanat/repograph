## Semantic layer

```bash
repograph semantic rebuild
repograph semantic query "authentication domain" --limit 5
```

- Local **FastEmbed** / ONNX embeddings (no PyTorch in CLI).
- Override model via `.repograph/repograph.yaml` `semantic.embedding_model` or env **`REPOGRAPH_EMBEDDING_MODEL`**.
- **`FASTEMBED_CACHE_PATH`** — directory with pre-downloaded ONNX models (offline/air-gapped).
- **`semantic query`** prints **JSON** on stdout (sensitive paths excluded).

Pass **`--no-semantic-rebuild`** on **`changes finalize`** and **`label apply-batch`** in CI to avoid model download.

Query/rebuild JSON fields: `repograph semantic --help` (schemas not inlined).

Details: `repograph semantic rebuild --help`, `repograph semantic query --help`.
