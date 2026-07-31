#!/usr/bin/env python3
"""Regenerate FlagHunter's canonical dependency manifest + reproducible lock (B-07).

``pyproject.toml`` ``[project.dependencies]`` is the **single canonical source**
of runtime dependency declarations. This script derives the two downstream files
from it so they can never drift by hand:

* ``requirements.txt`` — a *generated mirror* of the canonical runtime specifiers
  (the loose ``>=`` declarations), so the documented ``pip install -r
  requirements.txt`` path installs exactly what ``pyproject.toml`` declares.
* ``requirements.lock`` — the **reproducible lock**: exact ``name==version`` pins
  for the full transitive runtime closure, resolved from the *currently installed*
  environment via installed distribution metadata. Rebuilding from this lock
  reproduces the same versions.

Run from the repo root inside the project virtualenv::

    python scripts/lock_dependencies.py            # rewrite both files
    python scripts/lock_dependencies.py --check     # verify they are up to date

The lock captures whatever is installed, so regenerate it after any dependency
bump. Hash-level pinning (``--require-hashes``) and Docker base-image digest
pinning are the release supply-chain follow-up (B-05); they need a clean network
resolve that this offline-friendly script deliberately does not perform.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from importlib import metadata
from pathlib import Path

from packaging.markers import UndefinedEnvironmentName
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
LOCKFILE = REPO_ROOT / "requirements.lock"

_GENERATED_BANNER = (
    "# GENERATED — do not edit by hand.\n"
    "# Source of truth: pyproject.toml [project.dependencies].\n"
    "# Regenerate with: python scripts/lock_dependencies.py\n"
)


def read_canonical_dependencies() -> list[str]:
    """Return the canonical runtime dependency specifiers from pyproject.toml."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    deps = data.get("project", {}).get("dependencies", [])
    return list(deps)


def render_requirements(specifiers: list[str]) -> str:
    """Render requirements.txt as a generated mirror of the canonical specifiers."""
    body = "\n".join(sorted(specifiers, key=str.lower))
    return f"{_GENERATED_BANNER}{body}\n"


def _installed_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def resolve_runtime_closure(specifiers: list[str]) -> dict[str, str]:
    """Walk installed metadata to pin the full transitive runtime closure.

    Starting from the canonical top-level requirements, follow each installed
    distribution's ``Requires-Dist`` edges, evaluating environment markers for
    the current interpreter and **excluding** extras-gated dependencies (only the
    mandatory runtime install is locked). Returns ``{canonical_name: version}``.
    """
    pinned: dict[str, str] = {}
    seen: set[str] = set()
    queue: list[Requirement] = [Requirement(spec) for spec in specifiers]

    while queue:
        req = queue.pop()
        # Skip requirements gated behind an extra or an unsatisfied env marker.
        if req.marker is not None:
            try:
                if not req.marker.evaluate():
                    continue
            except UndefinedEnvironmentName:
                # Marker references an "extra" we are not installing → skip.
                continue

        key = canonicalize_name(req.name)
        if key in seen:
            continue
        seen.add(key)

        version = _installed_version(req.name)
        if version is None:
            # Declared but not installed in this environment; record for honesty.
            pinned[key] = ""
            continue
        pinned[key] = version

        for raw in metadata.requires(req.name) or []:
            try:
                dep = Requirement(raw)
            except Exception:  # malformed metadata line — skip defensively
                continue
            queue.append(dep)

    return pinned


def render_lock(pinned: dict[str, str]) -> str:
    lines = []
    missing = []
    for name in sorted(pinned, key=str.lower):
        version = pinned[name]
        if version:
            lines.append(f"{name}=={version}")
        else:
            missing.append(name)
    header = _GENERATED_BANNER + (
        "# Reproducible runtime lock: exact pins of the transitive closure of\n"
        "# pyproject.toml [project.dependencies], resolved from the installed env.\n"
        "# Scope: the interpreter/OS this was generated on (markers evaluated\n"
        "# locally). Cross-platform universal locking needs a network resolver\n"
        "# (release supply-chain follow-up, B-05).\n"
    )
    if missing:
        header += "# NOTE: declared but not installed here: " + ", ".join(missing) + "\n"
    return header + "\n".join(lines) + "\n"


def _write_or_check(path: Path, content: str, *, check: bool) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if check:
        return current == content
    path.write_text(content, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the generated files are current without rewriting them",
    )
    args = parser.parse_args(argv)

    specifiers = read_canonical_dependencies()
    requirements = render_requirements(specifiers)
    lock = render_lock(resolve_runtime_closure(specifiers))

    req_ok = _write_or_check(REQUIREMENTS, requirements, check=args.check)
    lock_ok = _write_or_check(LOCKFILE, lock, check=args.check)

    if args.check:
        if req_ok and lock_ok:
            print("dependency manifest + lock are up to date")
            return 0
        stale = [
            name
            for name, ok in ((REQUIREMENTS.name, req_ok), (LOCKFILE.name, lock_ok))
            if not ok
        ]
        print(f"stale (regenerate with scripts/lock_dependencies.py): {', '.join(stale)}")
        return 1

    print(f"wrote {REQUIREMENTS.name} and {LOCKFILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
