$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Server = Join-Path $RepoRoot "apps\dashboard\server.py"
$FrontendIndex = Join-Path $RepoRoot "apps\dashboard\frontend\dist\index.html"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual environment not found. Run scripts/setup.ps1 first."
}
if (-not (Test-Path -LiteralPath $FrontendIndex)) {
    throw "Frontend build not found. Run scripts/setup.ps1 or npm run build first."
}

& $Python (Join-Path $RepoRoot "scripts\configure_env.py")
& $Python $Server
