#!/usr/bin/env bash
# Helper script to vendor HexStrike into this repo using git subtree.
# Run from repository root.

set -euo pipefail

REPO_URL="https://github.com/0x4m4/hexstrike-ai.git"
PREFIX="third_party/hexstrike"
BRANCH="main"

echo "This will add HexStrike as a git subtree under ${PREFIX}."
echo "If you already have a subtree, use 'git subtree pull' instead.\n"

git subtree add --prefix="${PREFIX}" "${REPO_URL}" "${BRANCH}" --squash

echo "HexStrike subtree added under ${PREFIX}."
