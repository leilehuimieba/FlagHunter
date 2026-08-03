#!/usr/bin/env python3
"""Changed-files lint + format gate (B-01 / B-11).

The optimization masterplan (§13.3, B-01) requires the CI pipeline to enforce
Ruff + Black as *blocking* gates, but the legacy tree is not yet
lint/format-zeroed. The compromise is a changed-files gate: every Python file
added or modified in the current commit must pass ``ruff check`` and
``black --check`` with no errors.

This script is the executable side of that gate. It is invoked by the
``ci-lint-changed`` quality gate, which passes the changed python paths as
positional arguments. If no files are given (e.g. on a docs-only commit), the
gate is a no-op and exits 0 so unrelated commits are not held hostage.

The script prefers ``python -m ruff`` and ``python -m black`` (i.e. the same
interpreter that is running the gate) so it stays correct under ``python3``/
``python`` differences, virtualenvs and PEP 668-managed environments. It
falls back to a globally-installed ``ruff`` / ``black`` if the module form is
unavailable.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_tool(module: str, binary: str) -> list[str] | None:
    """Pick the most reliable way to invoke ``module`` / ``binary``."""

    # 1. ``python -m <module>`` — always uses the running interpreter.
    try:
        subprocess.run(
            [sys.executable, "-m", module, "--version"],
            capture_output=True,
            check=True,
            timeout=15,
        )
        return [sys.executable, "-m", module]
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        pass
    # 2. Globally-installed binary.
    path = shutil.which(binary)
    if path:
        return [path]
    return None


def _run(argv: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        argv,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Python files that changed in this commit (paths relative to repo root).",
    )
    parser.add_argument(
        "--skip-black",
        action="store_true",
        help="Skip the Black check (used when Black is not yet zeroed for the tree).",
    )
    args = parser.parse_args()

    files = [str(path) for path in args.files if str(path).endswith(".py")]
    if not files:
        print("ci-lint-changed: no python files in changeset; nothing to check.")
        return 0

    failures: list[str] = []

    ruff = _resolve_tool("ruff", "ruff")
    if ruff is None:
        failures.append("ruff is not installed in the current environment.")
    else:
        code, output = _run([*ruff, "check", *files])
        if code != 0:
            failures.append(f"ruff check failed (exit {code}):\n{output}")
        else:
            print(f"ruff check: {len(files)} file(s) clean")

    if not args.skip_black:
        black = _resolve_tool("black", "black")
        if black is None:
            failures.append("black is not installed in the current environment.")
        else:
            code, output = _run([*black, "--check", "--diff", *files])
            if code != 0:
                failures.append(f"black --check failed (exit {code}):\n{output}")
            else:
                print(f"black --check: {len(files)} file(s) clean")

    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
