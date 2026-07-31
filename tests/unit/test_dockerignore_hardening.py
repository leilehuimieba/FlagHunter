"""Guard: the Docker build context must exclude local runtime products & secrets.

The Dockerfiles ship the whole tree with ``COPY . .``. Anything not listed in
``.dockerignore`` lands in image layers, which would leak collected evidence
(``loot/``), logs, per-challenge working dirs, conversations, workspaces, RAG
session caches, secrets (``.env``) and local databases.

This test pins the exclusion policy for governance item F-06 / A-10 in
``docs/dev/FlagHunter_优化总纲.md``. If you intentionally change the policy,
update both files together.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCKERIGNORE = _REPO_ROOT / ".dockerignore"

# Patterns that MUST be excluded from the build context. Each entry is matched
# as a whole line (after stripping) against .dockerignore.
_REQUIRED_EXCLUDES = [
    ".env",
    "loot/",
    "logs/",
    "reports/",
    "challenges/",
    "conversations/",
    "workspaces/",
    "embeddings/",
    "flaghunter/knowledge/sessions/",
    "flaghunter/knowledge/ctf_sessions/",
    ".git",
    "third_party/MetasploitMCP",
]

# Substrings that must appear on some line (looser glob-style patterns).
_REQUIRED_PATTERN_SUBSTRINGS = [
    "*.db",
    "*.log",
    "tmp_",
    "__pycache__",
]


def _lines() -> list[str]:
    assert _DOCKERIGNORE.exists(), ".dockerignore is missing from repo root"
    return [ln.strip() for ln in _DOCKERIGNORE.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("pattern", _REQUIRED_EXCLUDES)
def test_sensitive_dir_is_excluded(pattern: str) -> None:
    assert pattern in _lines(), (
        f"{pattern!r} must be excluded from the Docker build context "
        f"(see F-06 / A-10). Add it to .dockerignore."
    )


@pytest.mark.parametrize("needle", _REQUIRED_PATTERN_SUBSTRINGS)
def test_sensitive_pattern_present(needle: str) -> None:
    joined = "\n".join(_lines())
    assert needle in joined, (
        f"Expected a .dockerignore rule containing {needle!r} to keep local "
        f"artifacts out of image layers (F-06 / A-10)."
    )


def test_env_example_is_not_ignored() -> None:
    """`.env.example` is documentation and should still be shippable."""
    assert "!.env.example" in _lines(), (
        ".env.* is excluded; re-include .env.example so the sample config "
        "remains available in the build context."
    )
