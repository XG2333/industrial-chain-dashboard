param(
    [string]$PipIndexUrl = "https://pypi.org/simple"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Frontend = Join-Path $RepoRoot "apps\dashboard\frontend"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    $PythonCommand = $null
    foreach ($Candidate in @("py", "python")) {
        $Command = Get-Command $Candidate -ErrorAction SilentlyContinue
        if (-not $Command) { continue }
        & $Command.Source --version *> $null
        if ($LASTEXITCODE -eq 0) {
            $PythonCommand = $Command.Source
            break
        }
    }
    if (-not $PythonCommand) {
        throw "Python 3.12+ was not found on PATH."
    }
    & $PythonCommand -m venv (Join-Path $RepoRoot ".venv")
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        throw "The virtual environment could not be created."
    }
}

& $VenvPython -m pip install --index-url $PipIndexUrl --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $VenvPython -m pip install --index-url $PipIndexUrl -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }
& $VenvPython -m pip install --index-url $PipIndexUrl -e (Join-Path $RepoRoot "packages\selecting-skill")
if ($LASTEXITCODE -ne 0) { throw "Local selecting-skill installation failed." }

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js/npm 18+ is required to build the dashboard frontend."
}

Push-Location $Frontend
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
} finally {
    Pop-Location
}

& $VenvPython (Join-Path $RepoRoot "scripts\configure_env.py")
if ($LASTEXITCODE -ne 0) { throw "Environment configuration failed." }
Write-Host "Setup complete. Add private inputs under data/raw, then run scripts/process_all.py."
