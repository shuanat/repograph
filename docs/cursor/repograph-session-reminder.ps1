# Optional Cursor hook (D-11): remind to finalize + export when the agent stops.
# Copy to .cursor/hooks/repograph-session-reminder.ps1
# Does not auto-finalize — agent must supply JSON to changes finalize.

$null = [Console]::In.ReadToEnd()

Write-Host "Repograph: when work is done, run 'repograph changes finalize' (agent JSON on stdin) and 'repograph export'." -ForegroundColor Yellow
Write-Host "Fast loops: repograph changes finalize --no-semantic-rebuild (and/or omit export until ready)."
Write-Host "v1 hooks never auto-finalize."
exit 0
