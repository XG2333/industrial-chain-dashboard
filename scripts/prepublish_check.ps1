$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ExcludedParts = @(
    "\.git\",
    "\.venv\",
    "\node_modules\",
    "\dist\",
    "\dist-offline\",
    "\data\raw\",
    "\data\processed\",
    "\data\stock-targets\",
    "\runtime\",
    "\artifacts\"
)
$ForbiddenExtensions = @(".xlsx", ".xls", ".xlsm", ".csv", ".tsv", ".parquet", ".db", ".sqlite", ".sqlite3", ".pkl", ".pickle", ".log", ".jsonl")
$TextExtensions = @(".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".ps1", ".bat")
$UserPathPattern = 'C:' + '[\\/]' + 'Users[\\/]|/Users/' + '[A-Za-z0-9._-]+/'
$Findings = New-Object System.Collections.Generic.List[string]

function Is-Excluded([string]$Path) {
    foreach ($Part in $ExcludedParts) {
        if ($Path.Contains($Part, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

foreach ($File in Get-ChildItem -LiteralPath $RepoRoot -Recurse -Force -File) {
    if (Is-Excluded $File.FullName) { continue }
    $Relative = $File.FullName.Substring($RepoRoot.Length + 1)

    # Local .env files are deliberately ignored. If Git has been initialized,
    # fail only when one is actually tracked.
    if ($File.Name -eq ".env") {
        $Tracked = $false
        if (Test-Path -LiteralPath (Join-Path $RepoRoot ".git")) {
            git -C $RepoRoot ls-files --error-unmatch -- $Relative *> $null
            $Tracked = $LASTEXITCODE -eq 0
        }
        if (-not $Tracked) { continue }
    }

    if ($File.Name -eq ".env" -or ($File.Name -like ".env.*" -and $File.Name -ne ".env.example")) {
        $Findings.Add("secret config file: $Relative")
    }
    if ($ForbiddenExtensions -contains $File.Extension.ToLowerInvariant()) {
        $Findings.Add("private/generated data file: $Relative")
    }
    if ($TextExtensions -notcontains $File.Extension.ToLowerInvariant()) { continue }

    $Content = [System.IO.File]::ReadAllText($File.FullName)
    if ($Content -match 'sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{16}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY') {
        $Findings.Add("credential-shaped literal: $Relative")
    }
    if ($Content -match $UserPathPattern) {
        $Findings.Add("absolute user path: $Relative")
    }
}

if ($Findings.Count -gt 0) {
    $Findings | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
    throw "Pre-publish check failed with $($Findings.Count) finding(s)."
}

Write-Host "Pre-publish check passed: no blocked data files, secret files, credential literals, or user paths found."
