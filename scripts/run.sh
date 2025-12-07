#!/bin/bash
# GhostCrew Run Script

set -e

# Activate virtual environment if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Load environment variables
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Parse arguments
MODE="cli"
TARGET=""
VPN_CONFIG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --tui)
            MODE="tui"
            shift
            ;;
        --target)
            TARGET="$2"
            shift 2
            ;;
        --vpn)
            VPN_CONFIG="$2"
            shift 2
            ;;
        --help)
            echo "GhostCrew - AI Penetration Testing"
            echo ""
            echo "Usage: run.sh [options]"
            echo ""
            echo "Options:"
            echo "  --tui              Run in TUI mode"
            echo "  --target <url>     Set initial target"
            echo "  --vpn <config>     Connect to VPN before starting"
            echo "  --help             Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Connect to VPN if specified
if [ -n "$VPN_CONFIG" ]; then
    echo "Connecting to VPN..."
    sudo openvpn --config "$VPN_CONFIG" --daemon
    sleep 5
fi

# Build command
CMD="python -m ghostcrew"

if [ "$MODE" = "tui" ]; then
    CMD="$CMD --tui"
fi

if [ -n "$TARGET" ]; then
    CMD="$CMD --target $TARGET"
fi

# Run GhostCrew
echo "Starting GhostCrew..."
$CMD
