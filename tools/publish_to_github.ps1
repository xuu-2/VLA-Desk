[CmdletBinding()]
param(
    [string]$Repository = "https://github.com/xuu-2/VLA-Desk.git",
    [string]$Branch = "main",
    [switch]$Commit
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

Write-Host "Project: $ProjectRoot"
Write-Host "Repository: $Repository"
Write-Host "Branch: $Branch"

if (-not (Test-Path ".git")) {
    throw "Not a Git repository: $ProjectRoot"
}

# Never stage secrets, local models, caches, or IDE settings.
git add -A

# These are unrelated parent-repository documents; never include their deletions.
git reset -- COMMIT_CHECKLIST.md GIT_COMMIT_GUIDE.md PROJECT_COMPLETION.md RELEASE_CHECKLIST.md 2>$null

# Remove secrets, local models, generated binaries, caches, and temporary captures.
# Keep .env.example as a safe configuration template.
git reset -- .env models 2>$null
if (Test-Path ".env.example") {
    git add ".env.example"
}

git diff --cached --name-only | ForEach-Object {
    if ($_ -match '(^|/)(\.env$|models/|__pycache__/|\.vscode/)' -or
        $_ -match '(^|/)(temp_|test_image|desk\.jpg|SimSun\.ttf|MJMODEL\.TXT|MUJOCO_LOG\.TXT)' -or
        $_ -match '\.(whl|mjb|mp4|obj)$') {
        git reset -- "$_"
        Write-Warning "Removed from staging: $_"
    }
}

$remote = git remote get-url origin 2>$null
if ($remote -ne $Repository) {
    git remote set-url origin $Repository
    Write-Host "Updated origin remote."
}

if ($Commit) {
    $message = "Update VLA-Desk second-generation pipeline"
    git commit -m $message
} else {
    Write-Host "No commit created. Review staged changes first."
    git status --short
    Write-Host "Run again with -Commit after reviewing the staged files."
    exit 0
}

# Rebase local work on the latest GitHub main to avoid non-fast-forward conflicts.
git fetch origin $Branch
git pull --rebase --autostash origin $Branch

git push origin HEAD:$Branch
Write-Host "Published successfully to $Repository ($Branch)."
