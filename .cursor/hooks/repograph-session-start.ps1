# Repograph Cursor hook — ingest + warn-only status (see docs/cursor/).

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
exit 0
