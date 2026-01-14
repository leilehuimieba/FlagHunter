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
	# If directory exists but is empty (left by manual mkdir or previous failed import),
	# treat it as if the subtree is not yet added so we can perform the add operation.
	if [ -z "$(ls -A "${PREFIX}" 2>/dev/null)" ]; then
		echo "Detected empty directory at ${PREFIX}; adding subtree into it..."
		mkdir -p "$(dirname "${PREFIX}")"
		if git subtree add --prefix="${PREFIX}" "${REPO_URL}" "${BRANCH}" --squash; then
			echo "MetasploitMCP subtree added under ${PREFIX}."
		else
			echo "Failed to add subtree from ${REPO_URL}." >&2
			echo "Check that the URL is correct or override with METASPLOIT_SUBTREE_REPO." >&2
			exit 1
		fi
		exit 0
	fi
	# Directory exists; check whether the path is tracked in git.
	if git ls-files --error-unmatch "${PREFIX}" >/dev/null 2>&1; then
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
		# Directory exists but not tracked by git.
		echo "Directory ${PREFIX} exists but is not tracked in git."
		if [ "${FORCE_SUBTREE_PULL:-false}" = "true" ]; then
			echo "FORCE_SUBTREE_PULL=true: backing up existing directory and attempting to add subtree..."
			BACKUP="${PREFIX}.backup.$(date +%s)"
			mv "${PREFIX}" "${BACKUP}" || { echo "Failed to move ${PREFIX} to ${BACKUP}" >&2; exit 1; }
			# Ensure parent exists after move
			mkdir -p "$(dirname "${PREFIX}")"
			if git subtree add --prefix="${PREFIX}" "${REPO_URL}" "${BRANCH}" --squash; then
				echo "MetasploitMCP subtree added under ${PREFIX}."
				echo "Removing backup ${BACKUP}."
				rm -rf "${BACKUP}"
			else
				echo "Failed to add subtree from ${REPO_URL}. Restoring backup." >&2
				rm -rf "${PREFIX}" || true
				mv "${BACKUP}" "${PREFIX}" || { echo "Failed to restore ${BACKUP} to ${PREFIX}" >&2; exit 1; }
				exit 1
			fi
		else
			echo "To add the subtree into the existing directory, either remove/rename ${PREFIX} and retry,"
			echo "or run with FORCE_SUBTREE_PULL=true to back up and add:"
			echo "  FORCE_SUBTREE_PULL=true bash scripts/add_metasploit_subtree.sh"
			echo "Or override the repo with METASPLOIT_SUBTREE_REPO to use a different source."
			exit 1
		fi
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
