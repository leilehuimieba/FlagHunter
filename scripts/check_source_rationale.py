#!/usr/bin/env python3
"""Source rationale gate for B-13.

The optimization masterplan (§13.3, B-13) requires source code and tests to be
self-contained: no comments, docstrings or rationale text may reference private
AI memory tokens such as ``[[project_xxx]]`` / ``[[feedback_xxx]]`` /
``[[reference_xxx]]`` (wiki-style citation stubs that only resolve inside the
authoring assistant's session memory).

Rationale references that need to survive review must point at durable locations:

* an ADR under ``docs/dev/adr/`` (or a similar committed doc),
* a GitHub issue or PR number,
* a commit SHA, or
* a path inside the repository.

This script scans the repository, prints every offending reference it finds,
and exits with a non-zero status so it can be used as a blocking CI gate. It
deliberately avoids false positives by requiring the ``[[...]]`` form: ordinary
identifiers like ``project_root``, ``_project_candidate_a_board`` and
``project_blackboard`` are part of the public API and stay untouched.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = (REPO_ROOT / "flaghunter", REPO_ROOT / "tests")

# Tokens that look like private-memory citations. The leading double-bracket
# is the wiki-style stub; the trailing brackets are required to keep this from
# matching legitimate identifiers such as ``project_root``.
PATTERN = re.compile(
    r"\[\[(project_[a-z0-9_]+|feedback_[a-z0-9_]+|reference_[a-z0-9_]+)\]\]"
)
ALLOWED_LINE_PARTS = (
    # Whitelist nothing — even ADR-style \"[[project_x]]\" citations in source
    # have no place when the source must stand on its own.
)


def iter_python_files(roots: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.py")))
    return files


def scan(path: Path) -> list[tuple[int, str, str]]:
    """Return [(line_no, token, line_text), ...] for every offending reference."""
    findings: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return findings
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in PATTERN.finditer(line):
            findings.append((line_no, match.group(1), line.strip()))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        help="Root directory to scan (repeatable). Defaults to flaghunter/ and tests/.",
    )
    args = parser.parse_args()

    roots = tuple(args.root) if args.root else DEFAULT_ROOTS
    files = iter_python_files(roots)
    total_findings = 0
    for path in files:
        for line_no, token, line_text in scan(path):
            relative = path.relative_to(REPO_ROOT)
            print(f"{relative}:{line_no}: [{token}] {line_text}", file=sys.stderr)
            total_findings += 1

    if total_findings:
        print(
            f"\nSource rationale gate (B-13) found {total_findings} private-memory "
            f"reference(s). Replace with a durable citation (ADR, issue, commit, "
            f"or repo path) or remove the comment.",
            file=sys.stderr,
        )
        return 1
    print(
        f"Source rationale gate (B-13) clean: {len(files)} files scanned, "
        f"no [[project_*]] / [[feedback_*]] / [[reference_*]] citations found."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
