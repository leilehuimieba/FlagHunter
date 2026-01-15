#!/usr/bin/env bash
set -euo pipefail

# Install vendored HexStrike Python dependencies.
# This script will source a local .env if present so any environment
# variables (proxies/indices/LLM keys) are respected during installation.

HERE=$(dirname "${BASH_SOURCE[0]}")
ROOT=$(cd "$HERE/.." && pwd)

cd "$ROOT"

if [ -f ".env" ]; then
  echo "Sourcing .env"
  # export all vars from .env (ignore comments and blank lines)
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

REQ=third_party/hexstrike/requirements.txt

if [ ! -f "$REQ" ]; then
  echo "Cannot find $REQ. Is the HexStrike subtree present?"
  exit 1
fi

echo "Installing HexStrike requirements from $REQ"

# Prefer using the active venv python if present
PY=$(which python || true)
if [ -n "${VIRTUAL_ENV:-}" ]; then
  PY="$VIRTUAL_ENV/bin/python"
fi

"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r "$REQ"

echo "HexStrike dependencies installed. Note: many external tools are not included and must be installed separately as described in third_party/hexstrike/requirements.txt." 

exit 0
