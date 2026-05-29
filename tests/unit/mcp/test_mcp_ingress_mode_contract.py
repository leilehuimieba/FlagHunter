from __future__ import annotations

import sys
import types

from types import SimpleNamespace

import pytest

from pentestagent.mcp.server import mcp_tools


class _PrimaryAgentStub:
    target = None
    scope: list[str] = []
    max_iterations = 30

    def get_tools(self):
        return []


def _close_created_task(coro):
    coro.close()
    return SimpleNamespace(done=lambda: True)


@pytest.fixture(autouse=True)
def _reset_mcp_task_state(monkeypatch: pytest.MonkeyPatch):
    mcp_tools._tasks.clear()
    monkeypatch.setattr(mcp_tools, "_primary_agent", _PrimaryAgentStub())


def test_run_task_schema_accepts_mode_and_ctf_type() -> None:
    schema = mcp_tools.mcp_tool_registry._tools["run_task"].schema

    assert "mode" in schema["properties"]
    assert "ctfType" in schema["properties"]
    assert "challengePath" in schema["properties"]
    assert "artifactPaths" in schema["properties"]


def test_run_task_async_schema_accepts_mode_and_ctf_type() -> None:
    schema = mcp_tools.mcp_tool_registry._tools["run_task_async"].schema

    assert "mode" in schema["properties"]
    assert "ctfType" in schema["properties"]
    assert "challengePath" in schema["properties"]
    assert "artifactPaths" in schema["properties"]


@pytest.mark.asyncio
async def test_run_task_async_resolves_mode_contract_before_task_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    async def fake_make_agent(target, scope):
        return SimpleNamespace()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        seen["payload"] = dict(payload)
        seen["source_task"] = source_task
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools.asyncio, "create_task", _close_created_task)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    await mcp_tools.run_task_async(
        {
            "task": "analyze challenge",
            "target": "http://challenge.test",
            "mode": "auto",
            "ctfType": "web",
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
            ],
        }
    )

    assert seen["payload"] == {
        "task": "analyze challenge",
        "target": "http://challenge.test",
        "mode": "auto",
        "ctfType": "web",
        "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        "artifactPaths": [
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
        ],
    }
    assert seen["source_task"] is None


@pytest.mark.asyncio
async def test_run_task_async_persists_and_reports_mode_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_make_agent(target, scope):
        return SimpleNamespace()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools.asyncio, "create_task", _close_created_task)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    result = await mcp_tools.run_task_async(
        {
            "task": "analyze challenge",
            "target": "http://challenge.test",
            "mode": "auto",
            "ctfType": "web",
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
            ],
        }
    )

    assert len(mcp_tools._tasks) == 1
    entry = next(iter(mcp_tools._tasks.values()))
    assert getattr(entry, "mode", None) == "ctf"
    assert getattr(entry, "modeSubtype", None) == "web"
    assert getattr(entry, "goalStyle", None) == "flag"
    assert getattr(entry, "challengePath", None) == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    assert getattr(entry, "artifactPaths", None) == [
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
    ]
    assert "mode: ctf" in result
    assert "mode_subtype: web" in result
    assert "goal_style: flag" in result
    assert r"challenge_path: D:\webstudy\CTF\2026\CTF比赛题\easy_login" in result
    assert r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml" in result


class _ForbiddenMcpAgent:
    def __init__(self):
        self.runtime = object()
        self.tools = []

    async def run_mcp(self, task):
        raise AssertionError("run_mcp should not be used for MCP CTF dispatcher path")


@pytest.mark.asyncio
async def test_run_task_routes_ctf_mode_into_dispatcher_with_explicit_challenge_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_make_agent(target, scope):
        return _ForbiddenMcpAgent()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    class _FakeDispatcher:
        def __init__(self, runtime, progress_callback=None, verification_callback=None):
            captured["runtime"] = runtime

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None):
            captured["target"] = target
            captured["goal"] = goal
            captured["type"] = type
            captured["hint"] = hint
            captured["challenge_context"] = challenge_context
            return SimpleNamespace(flag="flag{mcp_ctf_ok}", reason="ok", chain_used=["xss"], missing_tools=[], notes=[])

    fake_dispatcher_module = types.ModuleType("pentestagent.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    result = await mcp_tools.run_task(
        {
            "task": "solve easy_login from MCP",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\README.md",
            ],
        }
    )

    assert captured["target"] == "http://challenge.test"
    assert captured["goal"] == "solve easy_login from MCP"
    assert captured["type"] == "web"
    assert captured["challenge_context"] == {
        "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        "artifactPaths": [
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\README.md",
        ],
    }
    assert "flag{mcp_ctf_ok}" in result


@pytest.mark.asyncio
async def test_run_task_async_background_ctf_path_uses_explicit_challenge_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_make_agent(target, scope):
        return _ForbiddenMcpAgent()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    class _FakeDispatcher:
        def __init__(self, runtime, progress_callback=None, verification_callback=None):
            captured["runtime"] = runtime

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None):
            captured["target"] = target
            captured["goal"] = goal
            captured["type"] = type
            captured["hint"] = hint
            captured["challenge_context"] = challenge_context
            return SimpleNamespace(flag="flag{mcp_async_ctf_ok}", reason="ok", chain_used=["xss"], missing_tools=[], notes=[])

    def fake_create_task(coro):
        captured["scheduled_coro"] = coro
        return SimpleNamespace(done=lambda: False)

    fake_dispatcher_module = types.ModuleType("pentestagent.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    result = await mcp_tools.run_task_async(
        {
            "task": "solve easy_login from MCP async",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            ],
        }
    )

    assert "task_id:" in result
    scheduled = captured.get("scheduled_coro")
    assert scheduled is not None
    await scheduled

    assert captured["target"] == "http://challenge.test"
    assert captured["goal"] == "solve easy_login from MCP async"
    assert captured["type"] == "web"
    assert captured["challenge_context"] == {
        "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        "artifactPaths": [
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        ],
    }

