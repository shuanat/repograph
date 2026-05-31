#!/usr/bin/env bash
# Optional Cursor hook (D-11): remind to finalize + export when the agent stops.
# Copy to .cursor/hooks/repograph-session-reminder.sh and chmod +x.
# Does not auto-finalize — agent must supply JSON to changes finalize.
set -euo pipefail

cat >/dev/null

echo "Repograph: when work is done, run 'repograph changes finalize' (agent JSON on stdin) and 'repograph export'." >&2
echo "Fast loops: repograph changes finalize --no-semantic-rebuild (and/or omit export until ready)." >&2
echo "v1 hooks never auto-finalize." >&2
exit 0
