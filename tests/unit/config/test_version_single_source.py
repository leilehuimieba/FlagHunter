"""F-10 / B-06 — one version truth source; no 0.2/0.4 drift across surfaces.

``pyproject.toml`` is the authoritative version. ``APP_VERSION`` and every
place that advertises the project version (MCP client ``clientInfo`` and server
``serverInfo``) must resolve to that same value rather than a hand-maintained
literal that can drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _pyproject_version() -> str:
    if sys.version_info >= (3, 11):
        import tomllib

        data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text("utf-8"))
        return data["project"]["version"]
    # Minimal fallback parse for the single line we need.
    for line in (_REPO_ROOT / "pyproject.toml").read_text("utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("version") and "=" in stripped:
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    raise AssertionError("version not found in pyproject.toml")


def test_app_version_matches_pyproject() -> None:
    from flaghunter.config.constants import APP_VERSION

    assert APP_VERSION == _pyproject_version()


def test_mcp_server_version_matches_app_version() -> None:
    from flaghunter.config.constants import APP_VERSION
    from flaghunter.mcp.server.mcp_core import MCPRouter

    assert MCPRouter.SERVER_VERSION == APP_VERSION


def test_mcp_client_info_uses_app_version_not_a_literal() -> None:
    # The clientInfo advertised on `initialize` must be the live project
    # version, never a frozen "0.2.0" literal.
    from flaghunter.config import constants
    from flaghunter.mcp import manager as manager_module

    source = Path(manager_module.__file__).read_text("utf-8")
    assert '"version": "0.2.0"' not in source
    assert '"version": APP_VERSION' in source
    assert constants.APP_VERSION != "0.2.0"
