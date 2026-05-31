# Export Repograph product-only tree to orphan branch and push to GitHub.
# Excludes GSD/SDLC: .planning/, .cursor/get-shit-done/, gsd agents/skills, etc.
# Usage: ./scripts/ship-public.ps1 [-RepoName repograph] [-Push]

param(
    [string]$RepoName = "repograph",
    [string]$Owner = "shuanat",
    [switch]$Push
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$branch = "repograph-public"
$current = git branch --show-current

function Restore-Branch {
    if ($current) { git checkout $current 2>$null }
}

try {
    git checkout --orphan $branch
    # Clear index only — do not reset --hard (that can strip the working tree).
    git rm -rf --cached . 2>$null | Out-Null

    @"
# Public release — GSD/SDLC never belongs on this remote
.planning/
.cursor/get-shit-done/
.cursor/agents/
.cursor/skills/gsd-*/
.cursor/.gsd-profile
.cursor/gsd-file-manifest.json
gsd-local-patches/
.planning/

# Local Repograph runtime
.repograph/db.sqlite
.repograph/db.sqlite.tmp
.repograph/db.sqlite-wal
.repograph/db.sqlite-shm
tests/fixtures/mini-lab/.repograph/

# Legacy / local
project-inventory.db*
.inventory/
batch-*.json
labeled-batch-*.json
project-inventory-summary.md
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
.idea/
.vscode/
"@ | Set-Content -Encoding utf8 .gitignore

    $paths = @(
        "src",
        "tests",
        "docs",
        "archive",
        "scripts/ship-public.ps1",
        ".github",
        "README.md",
        "AGENTS.md",
        "pyproject.toml",
        "uv.lock",
        ".repograph/repograph.yaml",
        ".repograph/repograph.md",
        ".cursor/rules/repograph-workflow.mdc",
        ".cursor/skills/repograph",
        ".cursor/hooks.json",
        ".cursor/hooks/repograph-session-start.ps1",
        ".cursor/hooks/repograph-session-reminder.ps1",
        ".gitignore"
    )

    foreach ($p in $paths) {
        if (Test-Path $p) { git add $p }
    }

    # Drop anything that slipped through ignores
    git reset -- "**/__pycache__/**" "**/*.pyc" "tests/fixtures/mini-lab/.repograph" 2>$null

    if (Test-Path "tests/fixtures/mini-lab/.repograph") {
        git reset -- "tests/fixtures/mini-lab/.repograph" 2>$null
    }

    $staged = git diff --cached --name-only
    if (-not $staged) { throw "Nothing staged for public release." }

    git commit -m @"
feat: Repograph v1.0 MVP

Local CLI for AI agents: metadata scan, change journal, label batches,
FastEmbed semantic query, agent-guide playbook, and Cursor hook templates.

GSD planning artifacts are intentionally excluded from this repository.
"@

    Write-Host "Public branch '$branch' created with $($staged.Count) paths staged."

    if ($Push) {
        $remote = "origin"
        $url = "https://github.com/$Owner/$RepoName.git"
        if (-not (gh repo view "$Owner/$RepoName" 2>$null)) {
            gh repo create $RepoName --public `
                --description "Local repository inventory and health CLI for AI agents" `
                --homepage "https://github.com/$Owner/$RepoName"
            Write-Host "Created GitHub repo $Owner/$RepoName"
        }
        if (-not (git remote get-url $remote 2>$null)) {
            git remote add $remote $url
        }
        git push -u $remote "${branch}:main" --force
        Write-Host "Pushed to https://github.com/$Owner/$RepoName"
    }
}
finally {
    Restore-Branch
}
