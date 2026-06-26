"""Settings / .env IO + UI settings-payload projection.

Extracted from web_server.py (god-module 分簇·刀9, 债池第五波). This themed
cluster owns the round-trip between the on-disk ``.env`` file, the Settings
singleton and the shape the web console expects: flat ``.env`` read/write, the
editable / restart-required path tables, secret masking, the per-project MCP
manager factory, and the ``_settings_to_api`` / ``_apply_settings`` projections.
It is fully self-contained — members call only each other plus stdlib and
function-local lazy imports (config.settings / config.constants / mcp.manager),
so it carries no dependency on web_server (not even on the shared leaf layer).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _read_env(project_root: Path) -> dict:
    """Read .env as a flat dict (only lines with KEY=VALUE)."""
    env_path = project_root / ".env"
    result: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
    return result


def _write_env_key(project_root: Path, key: str, value: str) -> None:
    """Update or add a single KEY=VALUE in .env without touching other lines."""
    env_path = project_root / ".env"
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped == key:
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_SETTINGS_EDITABLE_PATHS = {
    "model.provider",
    "model.apiBase",
    "model.name",
    "model.apiKey",
    "runtime.dockerEnabled",
    "runtime.workdir",
    "budget.dailyTokenLimit",
    "budget.dailyCostLimit",
    "budget.perTaskTokenLimit",
    "budget.alertAt",
    "knowledge.embeddingModel",
    "ctf.enabled",
    "ctf.maxIterations",
    "ctf.autoRetry",
    "ctf.hintPolicy",
    "ctf.hypothesisDepth",
    "ctf.strategyMemory",
    "ctf.flagFormat",
    "ctf.verifierUrl",
}

_SETTINGS_RESTART_REQUIRED_PATHS = {
    "model.provider",
    "model.apiBase",
    "model.name",
    "model.apiKey",
    "runtime.dockerEnabled",
    "runtime.workdir",
    "knowledge.embeddingModel",
    "ctf.enabled",
    "ctf.maxIterations",
    "ctf.autoRetry",
    "ctf.hintPolicy",
    "ctf.hypothesisDepth",
    "ctf.strategyMemory",
    "ctf.flagFormat",
    "ctf.verifierUrl",
}


def _mask_secret(value: str | None) -> str:
    secret = str(value or "").strip()
    if not secret:
        return ""
    if len(secret) <= 8:
        return secret
    return secret[:8] + "•" * 16


def _settings_meta() -> dict[str, Any]:
    return {
        "editablePaths": sorted(_SETTINGS_EDITABLE_PATHS),
        "restartRequiredPaths": sorted(_SETTINGS_RESTART_REQUIRED_PATHS),
        "saveMode": "partial",
    }


def _mcp_manager_for_project(project_root: Path):
    from ..mcp.manager import MCPManager

    return MCPManager(project_root / "mcp_servers.json")


def _settings_to_api(project_root: Path) -> dict:
    """Build the settings payload the UI expects from env + Settings object."""
    env = _read_env(project_root)
    from ..config.settings import (
        get_settings,
        resolve_model_provider,
        resolve_model_readiness,
    )
    from ..config.constants import AGENT_MAX_ITERATIONS

    s = get_settings()
    mcp_manager = _mcp_manager_for_project(project_root)
    mcp_servers = mcp_manager.list_configured_servers()

    api_base = env.get("LITELLM_API_BASE", env.get("OPENAI_API_BASE", ""))
    anthropic_api_key = env.get("ANTHROPIC_API_KEY") or s.anthropic_api_key
    openai_api_key = env.get("OPENAI_API_KEY") or s.openai_api_key
    provider = resolve_model_provider(
        explicit_provider=env.get("FH_PROVIDER", ""),
        api_base=api_base,
        openai_api_key=openai_api_key,
        anthropic_api_key=anthropic_api_key,
    )
    active_api_key = anthropic_api_key if provider == "anthropic" else openai_api_key
    api_key = _mask_secret(active_api_key)
    model_name = env.get("FLAGHUNTER_MODEL", s.model or "")
    readiness = resolve_model_readiness(
        provider=provider,
        model=model_name,
        api_base=api_base,
        api_key=active_api_key,
    )

    return {
        "model": {
            "provider": provider,
            "apiBase": api_base,
            "name": model_name,
            "temperature": s.temperature,
            "maxTokens": s.max_tokens,
            "apiKey": api_key,
            "streaming": True,
            "readiness": readiness,
        },
        "runtime": {
            "mode": "docker" if env.get("FLAGHUNTER_DOCKER") == "true" else "local",
            "autoSsh": env.get("FLAGHUNTER_AUTO_SSH", "false").lower() == "true",
            "dockerEnabled": env.get("FLAGHUNTER_DOCKER", "false").lower() == "true",
            "sshConfigured": bool(env.get("KALI_SSH_HOST")),
            "workdir": env.get("FLAGHUNTER_WORKDIR", "workspaces"),
            "sandboxNetwork": env.get("DOCKER_NETWORK", "host"),
        },
        "mcp": {
            "enabled": True,
            "servers": [
                {
                    "name": str(item.get("name") or ""),
                    "type": str(item.get("type") or ""),
                    "url": str(item.get("url") or ""),
                    "enabled": bool(item.get("enabled", True)),
                    "connected": bool(item.get("connected", False)),
                }
                for item in mcp_servers
            ],
            "timeoutMs": int(env.get("MCP_TIMEOUT_MS", "30000")),
        },
        "knowledge": {
            "enabled": env.get("FLAGHUNTER_EMBEDDINGS", "local") != "disabled",
            "embeddingModel": env.get("FLAGHUNTER_EMBEDDINGS", "local"),
            "chunkSize": 1000,
            "overlap": 200,
            "threshold": 0.35,
        },
        "budget": {
            "dailyTokenLimit": int(env.get("FH_DAILY_TOKEN_LIMIT", "500000")),
            "dailyCostLimit": float(env.get("FH_DAILY_COST_LIMIT", "50")),
            "perTaskTokenLimit": int(env.get("FH_PER_TASK_TOKEN_LIMIT", "80000")),
            "alertAt": float(env.get("FH_BUDGET_ALERT_AT", "0.8")),
        },
        "audit": {
            "persistToolIO": True,
            "persistObservations": True,
            "redactSecrets": True,
            "retentionDays": 30,
        },
        "ctf": {
            "enabled": env.get("CPA_CTF_MODE", "true").lower() != "false",
            "maxIterations": int(env.get("FLAGHUNTER_AGENT_MAX_ITERATIONS", str(AGENT_MAX_ITERATIONS))),
            "autoRetry": int(env.get("CTF_AUTO_RETRY", "2")),
            "flagFormat": env.get("CTF_FLAG_FORMAT", r"flag\{[^}]+\}"),
            "hintPolicy": env.get("CTF_HINT_POLICY", "manual"),
            "hypothesisDepth": int(env.get("CTF_HYPOTHESIS_DEPTH", "3")),
            "strategyMemory": env.get("CTF_STRATEGY_MEMORY", "true").lower() != "false",
            "verifierUrl": env.get("CTF_VERIFIER_URL", ""),
        },
        "meta": _settings_meta(),
    }


def _apply_settings(project_root: Path, payload: dict) -> dict[str, Any]:
    """Write supported settings back to .env and report what happened."""
    env_before = _read_env(project_root)
    result = {
        "saved": [],
        "ignored": [],
        "restartRequired": [],
    }

    def mark_saved(path: str) -> None:
        if path not in result["saved"]:
            result["saved"].append(path)
        if path in _SETTINGS_RESTART_REQUIRED_PATHS and path not in result["restartRequired"]:
            result["restartRequired"].append(path)

    def mark_ignored(path: str) -> None:
        if path not in result["ignored"]:
            result["ignored"].append(path)

    def write_if_changed(path: str, env_key: str, value: Any) -> None:
        normalized = str(value)
        if env_before.get(env_key) == normalized:
            return
        _write_env_key(project_root, env_key, normalized)
        mark_saved(path)

    for section, values in payload.items():
        if section == "meta" or not isinstance(values, dict):
            continue
        for key in values.keys():
            path = f"{section}.{key}"
            if path not in _SETTINGS_EDITABLE_PATHS:
                mark_ignored(path)

    m = payload.get("model", {})
    if "apiBase" in m:
        write_if_changed("model.apiBase", "LITELLM_API_BASE", str(m.get("apiBase") or ""))
    if "name" in m:
        write_if_changed("model.name", "FLAGHUNTER_MODEL", str(m.get("name") or ""))
    if "provider" in m:
        write_if_changed("model.provider", "FH_PROVIDER", str(m.get("provider") or ""))
    # Only write key if it doesn't look masked
    if "apiKey" in m and "•" not in str(m.get("apiKey") or ""):
        provider = str(m.get("provider") or "")
        if provider in ("anthropic",):
            write_if_changed("model.apiKey", "ANTHROPIC_API_KEY", str(m.get("apiKey") or ""))
        else:
            write_if_changed("model.apiKey", "OPENAI_API_KEY", str(m.get("apiKey") or ""))

    r = payload.get("runtime", {})
    if "dockerEnabled" in r:
        write_if_changed("runtime.dockerEnabled", "FLAGHUNTER_DOCKER", str(r["dockerEnabled"]).lower())
    if "workdir" in r:
        write_if_changed("runtime.workdir", "FLAGHUNTER_WORKDIR", str(r.get("workdir") or ""))

    ctf = payload.get("ctf", {})
    if "maxIterations" in ctf:
        write_if_changed("ctf.maxIterations", "FLAGHUNTER_AGENT_MAX_ITERATIONS", str(ctf["maxIterations"]))
    if "autoRetry" in ctf:
        write_if_changed("ctf.autoRetry", "CTF_AUTO_RETRY", str(ctf["autoRetry"]))
    if "flagFormat" in ctf:
        write_if_changed("ctf.flagFormat", "CTF_FLAG_FORMAT", ctf["flagFormat"])
    if "hintPolicy" in ctf:
        write_if_changed("ctf.hintPolicy", "CTF_HINT_POLICY", ctf["hintPolicy"])
    if "hypothesisDepth" in ctf:
        write_if_changed("ctf.hypothesisDepth", "CTF_HYPOTHESIS_DEPTH", str(ctf["hypothesisDepth"]))
    if "strategyMemory" in ctf:
        write_if_changed("ctf.strategyMemory", "CTF_STRATEGY_MEMORY", str(ctf["strategyMemory"]).lower())
    if "verifierUrl" in ctf:
        write_if_changed("ctf.verifierUrl", "CTF_VERIFIER_URL", str(ctf.get("verifierUrl") or ""))
    if "enabled" in ctf:
        write_if_changed("ctf.enabled", "CPA_CTF_MODE", str(ctf["enabled"]).lower())

    budget = payload.get("budget", {})
    for k, env_k in [
        ("dailyTokenLimit", "FH_DAILY_TOKEN_LIMIT"),
        ("dailyCostLimit", "FH_DAILY_COST_LIMIT"),
        ("perTaskTokenLimit", "FH_PER_TASK_TOKEN_LIMIT"),
        ("alertAt", "FH_BUDGET_ALERT_AT"),
    ]:
        if k in budget:
            write_if_changed(f"budget.{k}", env_k, str(budget[k]))

    knowledge = payload.get("knowledge", {})
    if "embeddingModel" in knowledge:
        write_if_changed("knowledge.embeddingModel", "FLAGHUNTER_EMBEDDINGS", str(knowledge["embeddingModel"]))

    result["saved"].sort()
    result["ignored"].sort()
    result["restartRequired"].sort()
    return result
