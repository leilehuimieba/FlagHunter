#!/usr/bin/env bash
# Helper script to vendor HexStrike into this repo using git subtree.
# Run from repository root.

set -euo pipefail

REPO_URL="https://github.com/0x4m4/hexstrike-ai.git"
PREFIX="third_party/hexstrike"
BRANCH="main"

echo "This will add HexStrike as a git subtree under ${PREFIX}."
echo "If the subtree already exists, the script will pull and rebase the subtree instead.\n"

if [ -d "${PREFIX}" ]; then
	echo "Detected existing subtree at ${PREFIX}."
	if [ "${FORCE_SUBTREE_PULL:-false}" = "true" ]; then
		echo "FORCE_SUBTREE_PULL=true: pulling latest changes into existing subtree..."
		git subtree pull --prefix="${PREFIX}" "${REPO_URL}" "${BRANCH}" --squash || {
			echo "git subtree pull failed; attempting without --squash..."
			git subtree pull --prefix="${PREFIX}" "${REPO_URL}" "${BRANCH}" || exit 1
		}
		echo "Subtree at ${PREFIX} updated."
	else
		echo "To update the existing subtree run:"
		echo "  FORCE_SUBTREE_PULL=true bash scripts/add_hexstrike_subtree.sh"
		echo "Or run manually: git subtree pull --prefix=\"${PREFIX}\" ${REPO_URL} ${BRANCH} --squash"
	fi
else
	echo "Adding subtree for the first time..."
	git subtree add --prefix="${PREFIX}" "${REPO_URL}" "${BRANCH}" --squash
	echo "HexStrike subtree added under ${PREFIX}."
fi
