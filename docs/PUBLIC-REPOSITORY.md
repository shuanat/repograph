# Public GitHub repository

The **product** ships to [github.com/shuanat/repograph](https://github.com/shuanat/repograph). This development checkout may contain GSD/SDLC artifacts that must **never** be pushed to that remote.

## Never publish

| Path | Reason |
| ---- | ------ |
| `.planning/` | GSD roadmap, phases, plans |
| `.cursor/get-shit-done/` | GSD tooling |
| `.cursor/agents/gsd-*` | GSD subagents |
| `.cursor/skills/gsd-*` | GSD skills |

## Ship command

```powershell
./scripts/ship-public.ps1 -Push
```

Creates orphan branch `repograph-public` and pushes to `main` on GitHub.
