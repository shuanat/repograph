## Doctor & prerequisites

```bash
repograph doctor
repograph doctor --strict
```

- **`doctor`** — Python, SQLite, git, ONNX runtime readiness; semantic cache WARN when models are missing.
- **`doctor --strict`** — treat WARN as failure (hooks/CI discipline; opt-in).

Optional: set **`REPOGRAPH_ONNX_MODEL`** to a local `.onnx` path for an extra PASS row (shape check only).

Details: `repograph doctor --help`.
