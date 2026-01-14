# PentestAgent PowerShell Setup Script

Write-Host "=================================================================="
Write-Host "                        PENTESTAGENT"
Write-Host "                  AI Penetration Testing"
Write-Host "=================================================================="
Write-Host ""
Write-Host "Setup"
Write-Host ""

# Check Python version
Write-Host "Checking Python version..."
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python (\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
            Write-Host "Error: Python 3.10 or higher is required"
            exit 1
        }
        Write-Host "[OK] $pythonVersion"
    }
} catch {
    Write-Host "Error: Python not found. Please install Python 3.10+"
    exit 1
}

# Create virtual environment
Write-Host "Creating virtual environment..."
if (-not (Test-Path "venv")) {
    python -m venv venv
    Write-Host "[OK] Virtual environment created"
} else {
    Write-Host "[OK] Virtual environment exists"
}

# Activate virtual environment
Write-Host "Activating virtual environment..."
& .\venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
Write-Host "Installing dependencies..."
pip install -e ".[all]"
Write-Host "[OK] Dependencies installed"

# Install playwright browsers
Write-Host "Installing Playwright browsers..."
playwright install chromium
Write-Host "[OK] Playwright browsers installed"

# Create .env file if not exists
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env file..."
    @"
# PentestAgent Configuration

# API Keys (set at least one for chat model)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=

# For web search functionality (optional)
TAVILY_API_KEY=

# Chat Model (any LiteLLM-supported model)
# OpenAI: gpt-5, gpt-4.1, gpt-4.1-mini
# Anthropic: claude-sonnet-4-20250514, claude-opus-4-20250514
# Google: gemini models require gemini/ prefix (e.g., gemini/gemini-2.5-flash)
# Other providers: azure/, bedrock/, groq/, ollama/, together_ai/ (see litellm docs)
PENTESTAGENT_MODEL=gpt-5

# Embeddings (for RAG knowledge base)
# Options: openai, local (default: openai if OPENAI_API_KEY set, else local)
# PENTESTAGENT_EMBEDDINGS=local

# Settings
PENTESTAGENT_DEBUG=false

# Auto-launch vendored HexStrike on connect (true/false)
# If true, the MCP manager will attempt to start vendored HexStrike servers
# that are configured or detected under `third_party/hexstrike`.
LAUNCH_HEXTRIKE=false
# Auto-launch vendored Metasploit MCP on connect (true/false)
# If true, the MCP manager will attempt to start vendored MetasploitMCP
# servers that are configured or detected under `third_party/MetasploitMCP`.
LAUNCH_METASPLOIT_MCP=false

# Metasploit RPC (msfrpcd) settings — used when LAUNCH_METASPLOIT_MCP=true
# Set MSF_PASSWORD to enable automatic msfrpcd startup. Example:
# MSF_USER=msf
# MSF_PASSWORD=change_me
# MSF_SERVER=127.0.0.1
# MSF_PORT=55553
# MSF_SSL=false
MSF_USER=msf
MSF_PASSWORD=
MSF_SERVER=127.0.0.1
MSF_PORT=55553
MSF_SSL=false

# Agent max iterations (regular agent + crew workers, default: 30)
# PENTESTAGENT_AGENT_MAX_ITERATIONS=30

# Orchestrator max iterations (crew mode coordinator, default: 50)
# PENTESTAGENT_ORCHESTRATOR_MAX_ITERATIONS=50
"@ | Set-Content -Path ".env" -Encoding UTF8
    Write-Host "[OK] .env file created"
    Write-Host "[!] Please edit .env and add your API keys"
}

# Load .env into process environment variables (so the script can use them)
if (Test-Path -Path ".env") {
    Get-Content .env | ForEach-Object {
        if ($_ -match '^(?:\s*#)|(?:\s*$)') { return }
        if ($_ -match '^(\s*([^=]+)?)=(.*)$') {
            $name = $Matches[2].Trim()
            $value = $Matches[3].Trim()
            if ($name) { [Environment]::SetEnvironmentVariable($name, $value, 'Process') }
        }
    }
}

# Create loot directory for reports
New-Item -ItemType Directory -Force -Path "loot" | Out-Null
Write-Host "[OK] Loot directory created"

# Install vendored HexStrike dependencies automatically if present
$hexReq = Join-Path -Path (Get-Location) -ChildPath "third_party/hexstrike/requirements.txt"
if (Test-Path -Path $hexReq) {
    Write-Host "Installing vendored HexStrike dependencies..."
    try {
        & .\scripts\install_hexstrike_deps.ps1
    } catch {
        Write-Host "Warning: Failed to install HexStrike deps: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# Attempt to vendor MetasploitMCP via bundled script if not already present
$msDir = Join-Path -Path (Get-Location) -ChildPath "third_party/MetasploitMCP"
$addScript = Join-Path -Path (Get-Location) -ChildPath "scripts/add_metasploit_subtree.sh"
if (-not (Test-Path -Path $msDir) -and (Test-Path -Path $addScript)) {
    Write-Host "Vendoring MetasploitMCP into third_party (requires bash)..."
    if (Get-Command bash -ErrorAction SilentlyContinue) {
        try {
            & bash -c "scripts/add_metasploit_subtree.sh"
        } catch {
            Write-Host "Warning: Failed to vendor MetasploitMCP via bash: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Warning: 'bash' not available; please run scripts/add_metasploit_subtree.sh manually." -ForegroundColor Yellow
    }
}

# Install vendored MetasploitMCP dependencies automatically if present
$msReq = Join-Path -Path (Get-Location) -ChildPath "third_party/MetasploitMCP/requirements.txt"
$installMsScript = Join-Path -Path (Get-Location) -ChildPath "scripts/install_metasploit_deps.sh"
if (Test-Path -Path $msReq) {
    Write-Host "Installing vendored MetasploitMCP dependencies..."
    if (Test-Path -Path $installMsScript -and (Get-Command bash -ErrorAction SilentlyContinue)) {
        try {
            & bash -c "scripts/install_metasploit_deps.sh"
        } catch {
            Write-Host "Warning: Failed to install MetasploitMCP deps via bash: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Warning: Could not run install script automatically; run scripts/install_metasploit_deps.sh manually." -ForegroundColor Yellow
    }
}

# Optionally auto-start msfrpcd if configured in .env
if (($env:LAUNCH_METASPLOIT_MCP -eq 'true') -and ($env:MSF_PASSWORD)) {
    $msfUser = if ($env:MSF_USER) { $env:MSF_USER } else { 'msf' }
    $msfServer = if ($env:MSF_SERVER) { $env:MSF_SERVER } else { '127.0.0.1' }
    $msfPort = if ($env:MSF_PORT) { $env:MSF_PORT } else { '55553' }
    Write-Host "Starting msfrpcd (user=$msfUser, host=$msfServer, port=$msfPort) without sudo (background)..."
    # Start msfrpcd without sudo; if it's already running the cmd will fail harmlessly.
    if (Get-Command msfrpcd -ErrorAction SilentlyContinue) {
        try {
            if ($env:MSF_SSL -eq 'true' -or $env:MSF_SSL -eq '1') {
                Start-Process -FilePath msfrpcd -ArgumentList "-U", $msfUser, "-P", $env:MSF_PASSWORD, "-a", $msfServer, "-p", $msfPort, "-S" -NoNewWindow -WindowStyle Hidden
            } else {
                Start-Process -FilePath msfrpcd -ArgumentList "-U", $msfUser, "-P", $env:MSF_PASSWORD, "-a", $msfServer, "-p", $msfPort -NoNewWindow -WindowStyle Hidden
            }
            Write-Host "msfrpcd start requested; check with: netstat -an | Select-String $msfPort"
        } catch {
            Write-Host "Warning: Failed to start msfrpcd: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "msfrpcd not found; please install Metasploit Framework to enable Metasploit RPC." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Setup complete!"
Write-Host ""
Write-Host "To get started:"
Write-Host "  1. Edit .env and add your API keys"
Write-Host "  2. Activate: .\venv\Scripts\Activate.ps1"
Write-Host "  3. Run: pentestagent or python -m pentestagent"
Write-Host ""
