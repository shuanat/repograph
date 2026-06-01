## Error exit codes

| Command | Default | Strict / discipline |
|---------|---------|---------------------|
| **`repograph scan`** | exit **1** on severity `error` | warnings non-fatal |
| **`repograph changes status`** | exit **0** when staging non-empty (WARN) | **`--strict`** → exit **1** |
| **`repograph doctor`** | WARN non-fatal | **`doctor --strict`** → FAIL on WARN |

Use **`changes status --strict`** and **`doctor --strict`** in hooks/CI when you want failures instead of warnings.

Semantic rebuild/query fail clearly when the embedding model is unavailable (see **`FASTEMBED_CACHE_PATH`**).
