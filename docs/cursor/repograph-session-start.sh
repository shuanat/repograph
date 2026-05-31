#!/usr/bin/env bash
# Repograph Cursor hook: ingest git changes, then warn-only staging status (D-10).
# Copy to .cursor/hooks/repograph-session-start.sh and chmod +x.
# Does not call semantic rebuild, finalize, or any ONNX download.
set -euo pipefail

# Cursor sends hook context on stdin; v1 ignores it.
cat >/dev/null

ROOT="${REPOGRAPH_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT"

if command -v uv >/dev/null 2>&1; then
  RUN=(uv run repograph)
else
  RUN=(repograph)
fi

"${RUN[@]}" changes ingest
"${RUN[@]}" changes status
# Warn-only: exit 0 when staging is non-empty. Opt-in discipline for CI/hooks:
# "${RUN[@]}" changes status --strict
exit 0
