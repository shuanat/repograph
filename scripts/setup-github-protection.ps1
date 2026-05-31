# Apply or list GitHub Repository Rulesets for the public Repograph repo.
# Usage:
#   ./scripts/setup-github-protection.ps1              # list rulesets
#   ./scripts/setup-github-protection.ps1 -Apply       # create or update "Protect main"

param(
    [string]$Owner = 'shuanat',
    [string]$Repo = 'repograph',
    [string]$RulesetName = 'Protect main',
    [string]$RulesetFile = '.github/rulesets/main-protection.json',
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI (gh) is required. Install from https://cli.github.com/ and run gh auth login.'
}

$apiBase = "repos/$Owner/$Repo/rulesets"
$rulesetPath = Join-Path $Root $RulesetFile
if (-not (Test-Path $rulesetPath)) {
    throw "Ruleset file not found: $RulesetFile"
}

function Get-Rulesets {
    gh api $apiBase 2>&1 | ConvertFrom-Json
}

if (-not $Apply) {
    $rulesets = Get-Rulesets
    if (-not $rulesets) {
        Write-Host 'No rulesets configured.'
        exit 0
    }
    $rulesets | ForEach-Object {
        Write-Host ("{0} (id={1}, enforcement={2})" -f $_.name, $_.id, $_.enforcement)
    }
    exit 0
}

$body = Get-Content -Raw -Path $rulesetPath
$existing = @(Get-Rulesets | Where-Object { $_.name -eq $RulesetName })

if ($existing.Count -gt 0) {
    $id = $existing[0].id
    Write-Host "Updating ruleset '$RulesetName' (id=$id)..."
    gh api --method PUT -H 'Accept: application/vnd.github+json' -H 'X-GitHub-Api-Version: 2022-11-28' `
        --input $rulesetPath "$apiBase/$id" | Out-Null
} else {
    Write-Host "Creating ruleset '$RulesetName'..."
    gh api --method POST -H 'Accept: application/vnd.github+json' -H 'X-GitHub-Api-Version: 2022-11-28' `
        --input $rulesetPath $apiBase | Out-Null
}

Write-Host 'Done. Active rulesets:'
Get-Rulesets | ForEach-Object {
    Write-Host ("  {0} (id={1}, enforcement={2})" -f $_.name, $_.id, $_.enforcement)
}
