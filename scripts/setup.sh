#!/bin/bash
# PentestAgent Setup Script

set -e

echo "=================================================================="
echo "                        PENTESTAGENT"
echo "                  AI Penetration Testing"
echo "=================================================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.10"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python $required_version or higher is required (found $python_version)"
    exit 1
fi
echo "[OK] Python $python_version"

# Create virtual environment
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "[OK] Virtual environment created"
else
    echo "[OK] Virtual environment exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -e ".[all]"
echo "[OK] Dependencies installed"

# Install playwright browsers
echo "Installing Playwright browsers..."
playwright install chromium
echo "[OK] Playwright browsers installed"

# Create .env file if not exists
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cat > .env << EOF
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
EOF
    echo "[OK] .env file created"
    echo "[!] Please edit .env and add your API keys"
fi

# Load .env into environment if present
if [ -f ".env" ]; then
    # Export variables defined in .env for the duration of this script
    set -a
    # shellcheck disable=SC1091
    . .env
    set +a
fi

# Create loot directory for reports
mkdir -p loot
echo "[OK] Loot directory created"

# NOTE: Automatic vendored MCP installation/start has been removed.
# If you need vendored MCP servers (e.g., HexStrike, MetasploitMCP), run
# the helper scripts under `third_party/` or the `scripts/` helpers manually.
# Example manual steps:
#   bash scripts/install_hexstrike_deps.sh
#   bash scripts/add_metasploit_subtree.sh
#   bash scripts/install_metasploit_deps.sh
# Starting msfrpcd or other networked services should be done explicitly by
# the operator in a controlled environment.

echo ""
echo "=================================================================="
echo "Setup complete!"
echo ""
echo "To get started:"
echo "  1. Edit .env and add your API keys"
echo "  2. Activate the virtual environment: source venv/bin/activate"
echo "  3. Run PentestAgent: pentestagent or python -m pentestagent"
echo ""
echo "For Docker usage:"
echo "  docker-compose up pentestagent"
echo "  docker-compose --profile kali up pentestagent-kali"
echo ""
echo "=================================================================="
