"""Model/env readiness probing for the MCP server tools.

Third physical-split slice extracted from the ~2094-line ``mcp_tools`` god-module,
same behavior-preserving pattern as ``mcp_task_presentation`` / ``mcp_task_contracts``:
move a cohesive, down-closed, unpatched leaf cluster to a sibling and re-import it
into the ``mcp_tools`` namespace.

These two functions read the local ``.env`` file and resolve the active model
provider/readiness snapshot reported by ``get_server_status`` and consulted by
``run_task`` / ``run_task_async``. They call no other ``mcp_tools`` function (except
each other), touch no module state, and are not part of the test monkeypatch
surface. Their ``config.settings`` dependencies are inline imports resolved at the
source module (``flaghunter.config.settings``), so tests patch them there — not via
the ``mcp_tools`` namespace — and the move is transparent. Callers
(``get_server_status`` / ``run_task`` / ``run_task_async``) stay in ``mcp_tools``
and resolve these names via re-import.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _read_local_env() -> dict[str, str]:
    env_path = Path(".env")
    result: dict[str, str] = {}
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def _current_model_readiness() -> dict[str, Any]:
    from ...config.settings import (
        get_settings,
        resolve_model_provider,
        resolve_model_readiness,
    )

    env = _read_local_env()
    settings = get_settings()
    api_base = env.get(
        "LITELLM_API_BASE",
        env.get("OPENAI_API_BASE", os.getenv("LITELLM_API_BASE") or os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL") or ""),
    )
    anthropic_api_key = env.get("ANTHROPIC_API_KEY") or settings.anthropic_api_key
    openai_api_key = env.get("OPENAI_API_KEY") or settings.openai_api_key
    provider = resolve_model_provider(
        explicit_provider=env.get("FH_PROVIDER", os.getenv("FH_PROVIDER", "")),
        api_base=api_base,
        openai_api_key=openai_api_key,
        anthropic_api_key=anthropic_api_key,
    )
    active_api_key = anthropic_api_key if provider == "anthropic" else openai_api_key
    return resolve_model_readiness(
        provider=provider,
        model=env.get("FLAGHUNTER_MODEL") or settings.model or "",
        api_base=api_base,
        api_key=active_api_key,
    )
