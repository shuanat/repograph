# Repograph Cursor hook: ingest git changes, then warn-only staging status (D-10).
# Copy to .cursor/hooks/repograph-session-start.ps1
# Does not call semantic rebuild, finalize, or any ONNX download.

$null = [Console]::In.ReadToEnd()

if ($env:REPOGRAPH_ROOT) {
    $root = $env:REPOGRAPH_ROOT
} else {
    $gitRoot = git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0 -and $gitRoot) {
        $root = $gitRoot.Trim()
    } else {
        $root = (Get-Location).Path
    }
}
Set-Location -LiteralPath $root

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run repograph changes ingest
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    uv run repograph changes status
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    repograph changes ingest
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    repograph changes status
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
# Warn-only: exit 0 when staging is non-empty. Opt-in discipline for CI/hooks:
# & @runner changes status --strict
exit 0
