# Mini lab fixture

Synthetic repo for Repograph Phase 2 tests.

| Path | Purpose |
|------|---------|
| `docs/broken-link.md` | Broken relative markdown link → `BROKEN_MD_LINK` |
| `alpha/readme.md`, `beta/readme.md` | Same basename in different dirs → `DUPLICATE_BASENAME` |
| `alpha/dup.txt`, `beta/dup.txt` | Identical bytes → `DUPLICATE_CONTENT` |
| `unexpected-dir/` | Extra top-level dir → `UNEXPECTED_TOPLEVEL` (after yaml apply) |
| `.env` | Sensitive glob test |
| `mikrotik/configs/dhcp.md` | Sample nested file |
