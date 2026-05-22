from __future__ import annotations

from types import SimpleNamespace

import pytest

from pentestagent.agents.pa_agent.ctf_planner import (
    build_ctf_system_prompt,
    get_ctf_quick_path,
)
from pentestagent.agents.pa_agent.pa_agent import PentestAgentAgent


class _NoGenerateLLM:
    async def generate(self, *args, **kwargs):
        raise AssertionError("llm.generate should not be called in CTF mode")


class _DummyRuntime:
    def __init__(self):
        self.environment = SimpleNamespace()
        self.plan = None


def test_get_quick_path_sqli():
    steps = get_ctf_quick_path("sqli")
    assert "登录绕过" in steps[0]


def test_get_quick_path_unknown():
    assert get_ctf_quick_path("unknown") == get_ctf_quick_path("web")


def test_build_system_prompt_hint():
    prompt = build_ctf_system_prompt("web", "admin page")
    assert "Hint from challenge: admin page" in prompt


def test_build_system_prompt_no_hint():
    prompt = build_ctf_system_prompt("web", "")
    assert "Hint from challenge" not in prompt


@pytest.mark.asyncio
async def test_pa_agent_ctf_mode_skips_llm(monkeypatch):
    async def _unexpected_generate_plan(**kwargs):
        raise AssertionError("generate_plan should not be called in CTF mode")

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.pa_agent.generate_plan",
        _unexpected_generate_plan,
    )

    runtime = _DummyRuntime()
    agent = PentestAgentAgent(
        llm=_NoGenerateLLM(),
        tools=[SimpleNamespace(name="sqlmap", enabled=True)],
        runtime=runtime,
        target="http://dvwa.local/",
        scope=[],
    )
    task = """[CTF MODE] Target: http://dvwa.local/
Challenge type: sqli
Hint: login bypass

OBJECTIVE: Find and capture the flag as fast as possible.
"""
    agent.conversation_history.append(SimpleNamespace(role="user", content=task))

    plan_msg = await agent._auto_generate_plan()

    assert plan_msg is None
    assert runtime.plan is agent._task_plan
    assert runtime.plan.original_request == task
    assert runtime.plan.steps
    assert runtime.plan.steps[0].description == get_ctf_quick_path("sqli")[0]
    assert "CTF Quick-Path Mode: SQLI" in agent.get_system_prompt()
