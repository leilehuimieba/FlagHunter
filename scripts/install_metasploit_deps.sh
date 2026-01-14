#!/usr/bin/env bash
set -euo pipefail

# Install vendored MetasploitMCP Python dependencies.
# This script will source a local .env if present so any environment
# variables (proxies/indices/LLM keys) are respected during installation.

HERE=$(dirname "${BASH_SOURCE[0]}")
ROOT=$(cd "$HERE/.." && pwd)

cd "$ROOT"

if [ -f ".env" ]; then
  echo "Sourcing .env"
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

REQ=third_party/MetasploitMCP/requirements.txt

if [ ! -f "$REQ" ]; then
  echo "Cannot find $REQ. Is the MetasploitMCP subtree present?"
  exit 1
fi

echo "Installing MetasploitMCP requirements from $REQ"

PY=$(which python || true)
if [ -n "${VIRTUAL_ENV:-}" ]; then
  PY="$VIRTUAL_ENV/bin/python"
fi

"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r "$REQ"

echo "MetasploitMCP dependencies installed. Note: external components may still be required." 

exit 0
