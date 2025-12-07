#!/bin/bash
# GhostCrew Setup Script

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}GhostCrew${NC} - AI Penetration Testing"
echo ""

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.10"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo -e "${RED}Error: Python $required_version or higher is required (found $python_version)${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $python_version${NC}"

# Create virtual environment
echo -e "${YELLOW}Creating virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment exists${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Upgrade pip
echo -e "${YELLOW}Upgrading pip...${NC}"
pip install --upgrade pip

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install -e ".[all]"
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Install playwright browsers
echo -e "${YELLOW}Installing Playwright browsers...${NC}"
playwright install chromium
echo -e "${GREEN}✓ Playwright browsers installed${NC}"

# Create .env file if not exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file...${NC}"
    cat > .env << EOF
# GhostCrew Configuration
# Add your API keys here

# OpenAI API Key (required for GPT models)
OPENAI_API_KEY=

# Anthropic API Key (required for Claude models)
ANTHROPIC_API_KEY=

# Model Configuration
GHOSTCREW_MODEL=gpt-5

# Debug Mode
GHOSTCREW_DEBUG=false

# Max Iterations
GHOSTCREW_MAX_ITERATIONS=50
EOF
    echo -e "${GREEN}✓ .env file created${NC}"
    echo -e "${YELLOW}⚠️  Please edit .env and add your API keys${NC}"
fi

# Create loot directory for reports
mkdir -p loot
echo -e "${GREEN}✓ Loot directory created${NC}"

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo -e "To get started:"
echo -e "  1. Edit ${YELLOW}.env${NC} and add your API keys"
echo -e "  2. Activate the virtual environment: ${YELLOW}source venv/bin/activate${NC}"
echo -e "  3. Run GhostCrew: ${YELLOW}ghostcrew${NC} or ${YELLOW}python -m ghostcrew${NC}"
echo ""
echo -e "For Docker usage:"
echo -e "  ${YELLOW}docker-compose up ghostcrew${NC}"
echo -e "  ${YELLOW}docker-compose --profile kali up ghostcrew-kali${NC}"
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
