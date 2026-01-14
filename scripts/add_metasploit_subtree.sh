#!/usr/bin/env bash
# Helper script to vendor MetasploitMCP into this repo using git subtree.
# Run from repository root.

set -euo pipefail

REPO_URL="${METASPLOIT_SUBTREE_REPO:-https://github.com/GH05TCREW/MetasploitMCP.git}"
PREFIX="third_party/MetasploitMCP"
BRANCH="main"

echo "This will add MetasploitMCP as a git subtree under ${PREFIX}."
echo "You can override the upstream repo with: METASPLOIT_SUBTREE_REPO=...\n"
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
		echo "  FORCE_SUBTREE_PULL=true bash scripts/add_metasploit_subtree.sh"
		echo "Or run manually: git subtree pull --prefix=\"${PREFIX}\" ${REPO_URL} ${BRANCH} --squash"
	fi
else
	echo "Adding subtree for the first time..."
	# Ensure parent dir exists for clearer errors
	mkdir -p "$(dirname "${PREFIX}")"

	if git subtree add --prefix="${PREFIX}" "${REPO_URL}" "${BRANCH}" --squash; then
		echo "MetasploitMCP subtree added under ${PREFIX}."
	else
		echo "Failed to add subtree from ${REPO_URL}." >&2
		echo "Check that the URL is correct or override with METASPLOIT_SUBTREE_REPO." >&2
		exit 1
	fi
fi
