# FlagHunter Windows Runner Script
# Usage: .\run.ps1 [tui|run] [options...]
#
# Examples:
#   .\run.ps1 tui
#   .\run.ps1 run -t http://target.com --max-loops 30
#   .\run.ps1 run -t http://target.com --playbook thp3_web

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")

# Activate virtual environment
$VenvActivate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $VenvActivate) {
    & $VenvActivate
} else {
    Write-Host "Error: Virtual environment not found at .venv/" -ForegroundColor Red
    exit 1
}

# Load .env if exists
$EnvFile = Join-Path $ProjectRoot ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#\s][^=]*)=(.*)$') {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim()
            # Remove surrounding quotes if present
            if ($val -match '^"(.*)"$') { $val = $matches[1] }
            elseif ($val -match "^'(.*)'$") { $val = $matches[1] }
            [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

# Set UTF-8 encoding for Windows terminals
if ($env:OS -eq "Windows_NT") {
    [System.Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    chcp 65001 | Out-Null
}

# Run FlagHunter
Set-Location $ProjectRoot
$ArgsList = $args
if ($ArgsList.Count -eq 0 -or $ArgsList[0] -eq "tui") {
    python -m flaghunter @ArgsList
} else {
    python -m flaghunter @ArgsList
}
