## Fixture walkthrough (mini-lab)

Practice the full path on the bundled fixture **`tests/fixtures/mini-lab`** (from the repograph repo root):

```bash
cd tests/fixtures/mini-lab
repograph scan
repograph config init
repograph config apply
repograph changes ingest
repograph changes status
repograph changes finalize --file ../../fixtures/changes-finalize.json --no-semantic-rebuild
repograph label vocab-apply -f ../../fixtures/label-vocab.json
repograph label export --limit 5
repograph export
```

Use **`--no-semantic-rebuild`** on finalize/apply-batch in CI to skip ONNX download. See **`README.md`** at the repograph repo root for PowerShell variants.
