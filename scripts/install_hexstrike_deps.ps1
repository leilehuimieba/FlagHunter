<#
Install vendored HexStrike Python dependencies (Windows/PowerShell).

This mirrors `scripts/install_hexstrike_deps.sh` for Windows users.
#>
Set-StrictMode -Version Latest

Write-Host "Installing vendored HexStrike dependencies (Windows)..."

# Load .env if present (simple parser: ignore comments/blank lines)
if (Test-Path -Path ".env") {
    Write-Host "Sourcing .env"
    Get-Content .env | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line -split "=", 2
            $name = $parts[0].Trim()
            $value = $parts[1].Trim()
            # Only set if not empty
            if ($name) { $env:$name = $value }
        }
    }
}

$req = Join-Path -Path (Get-Location) -ChildPath "third_party/hexstrike/requirements.txt"

if (-not (Test-Path -Path $req)) {
    Write-Host "Cannot find $req. Is the HexStrike subtree present?" -ForegroundColor Yellow
    exit 1
}

# Prefer venv python if present
$python = "python"
if (Test-Path -Path ".\venv\Scripts\python.exe") {
    $python = Join-Path -Path (Get-Location) -ChildPath ".\venv\Scripts\python.exe"
}

Write-Host "Using Python: $python"

& $python -m pip install --upgrade pip
& $python -m pip install -r $req

Write-Host "HexStrike dependencies installed. Note: many external tools are not included and must be installed separately as described in third_party/hexstrike/requirements.txt." -ForegroundColor Green

exit 0
