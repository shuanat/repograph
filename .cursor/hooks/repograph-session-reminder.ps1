$null = [Console]::In.ReadToEnd()
Write-Host "Repograph: when work is done, run 'repograph changes finalize' (agent JSON) and 'repograph export'." -ForegroundColor Yellow
Write-Host "Fast loops: repograph changes finalize --no-semantic-rebuild"
exit 0
