from __future__ import annotations

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


def test_run_task_async_schema_accepts_mode_and_ctf_type() -> None:
    schema = mcp_tools.mcp_tool_registry._tools["run_task_async"].schema

    assert "mode" in schema["properties"]
    assert "ctfType" in schema["properties"]


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
        }
    )

    assert seen["payload"] == {
        "task": "analyze challenge",
        "target": "http://challenge.test",
        "mode": "auto",
        "ctfType": "web",
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
        }
    )

    assert len(mcp_tools._tasks) == 1
    entry = next(iter(mcp_tools._tasks.values()))
    assert getattr(entry, "mode", None) == "ctf"
    assert getattr(entry, "modeSubtype", None) == "web"
    assert getattr(entry, "goalStyle", None) == "flag"
    assert "mode: ctf" in result
    assert "mode_subtype: web" in result
    assert "goal_style: flag" in result
