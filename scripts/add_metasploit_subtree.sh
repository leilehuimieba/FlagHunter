#!/usr/bin/env bash
# Helper script to vendor MetasploitMCP into this repo using git subtree.
# Run from repository root.

set -euo pipefail

REPO_URL="https://github.com/GH05TCREW/MetasploitMCP.git"
PREFIX="third_party/MetasploitMCP"
BRANCH="main"

echo "This will add MetasploitMCP as a git subtree under ${PREFIX}."
echo "If you already have a subtree, use 'git subtree pull' instead.\n"

git subtree add --prefix="${PREFIX}" "${REPO_URL}" "${BRANCH}" --squash

echo "MetasploitMCP subtree added under ${PREFIX}."
