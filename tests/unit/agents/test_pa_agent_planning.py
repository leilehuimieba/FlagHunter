from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.pa_agent import FlagHunterAgent
from flaghunter.agents.pa_agent.planner import generate_plan


class _PromptCaptureLLM:
    def __init__(self, payload: dict):
        self.payload = payload
        self.last_prompt = ""

    async def generate(self, system_prompt, messages, tools, task_hint="default", **kwargs):
        self.last_prompt = messages[0]["content"]
        return SimpleNamespace(
            content=json.dumps(self.payload, ensure_ascii=False),
            tool_calls=None,
            usage={"total_tokens": 1},
        )


class _DummyRuntime:
    def __init__(self):
        self.environment = SimpleNamespace()
        self.plan = None


@pytest.mark.asyncio
async def test_generate_plan_appends_known_credentials_to_prompt():
    llm = _PromptCaptureLLM(
        {
            "objective": "test objective",
            "phases": [],
            "risk_level": "medium",
            "estimated_steps": 0,
        }
    )

    await generate_plan(
        task="测试 SQL 注入",
        target="127.0.0.1",
        scope=["127.0.0.1/32"],
        tools=["sqlmap", "dirscan", "nuclei"],
        llm=llm,
        known_credentials=[
            {
                "username": "admin",
                "password": "supersecretpw",
                "cookie": "PHPSESSID=abc123;security=low",
                "protocol": "http",
                "target": "127.0.0.1",
            }
        ],
    )

    assert "已知凭据/Session（在相关步骤的 args 中直接使用）:" in llm.last_prompt
    assert "user=admin" in llm.last_prompt
    assert "pass=supersecretpw" in llm.last_prompt
    assert "cookie=PHPSESSID=abc123;security=low" in llm.last_prompt
    assert 'sqlmap 步骤 args 里若有可用 cookie，加 "cookie": "<value>"' in llm.last_prompt
    assert 'dirscan/nuclei 步骤若需要认证，在 args 里加 "headers": {"Cookie": "<value>"}' in llm.last_prompt


@pytest.mark.asyncio
async def test_auto_generate_plan_extracts_known_credentials_and_redacts_password_logs(
    monkeypatch,
):
    captured: dict = {}

    async def _fake_generate_plan(**kwargs):
        captured["known_credentials"] = kwargs.get("known_credentials")
        return {
            "objective": "测试 127.0.0.1:8080 的 SQL 注入",
            "phases": [
                {
                    "phase": 1,
                    "name": "利用",
                    "steps": [
                        {
                            "step": 1,
                            "tool": "sqlmap",
                            "args": {
                                "url": "http://127.0.0.1:8080/vuln.php?id=1",
                                "cookie": "PHPSESSID=abc123;security=low",
                                "password": "supersecretpw",
                            },
                            "purpose": "测试 SQL 注入",
                            "depends_on": [],
                        }
                    ],
                    },
                ],
            "risk_level": "medium",
            "estimated_steps": 1,
        }

    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.pa_agent.generate_plan",
        _fake_generate_plan,
    )
    monkeypatch.setattr(
        "flaghunter.tools.notes.get_all_notes_sync",
        lambda: {
            "dvwa_session": {
                "category": "credential",
                "content": "DVWA session cookie",
                "metadata": {
                    "cookie": "PHPSESSID=abc123;security=low",
                    "target": "127.0.0.1",
                },
            },
            "fallback_cookie": {
                "category": "credential",
                "content": "cookie: TOKEN=xyz",
                "metadata": {},
            },
        },
    )

    agent = FlagHunterAgent(
        llm=SimpleNamespace(),
        tools=[SimpleNamespace(name="sqlmap", enabled=True)],
        runtime=_DummyRuntime(),
        target="127.0.0.1",
        scope=["127.0.0.1/32"],
    )
    agent.conversation_history.append(
        SimpleNamespace(role="user", content="测试 127.0.0.1:8080 的 SQL 注入")
    )

    plan_msg = await agent._auto_generate_plan()

    assert plan_msg is not None
    assert captured["known_credentials"] == [
        {"cookie": "PHPSESSID=abc123;security=low", "target": "127.0.0.1"},
        {"cookie": "TOKEN=xyz"},
    ]
    assert "PHPSESSID=abc123;security=low" in plan_msg.content
    assert "supersecretpw" not in plan_msg.content
    assert "supersec..." in plan_msg.content
    assert "supersecretpw" not in plan_msg.metadata["structured_plan_json"]
    assert "supersec..." in plan_msg.metadata["structured_plan_json"]
    assert "supersecretpw" in agent._task_plan.steps[0].description


def test_get_system_prompt_includes_missing_tool_install_hints(monkeypatch):
    monkeypatch.setattr(
        "flaghunter.tools.notes.get_all_notes_sync",
        lambda: {
            "missing_tool_sqlmap": {
                "category": "artifact",
                "content": "Tool 'sqlmap' not found. Install: apt install sqlmap",
                "metadata": {
                    "tool": "sqlmap",
                    "install_hint": "Tool 'sqlmap' not found. Install: apt install sqlmap",
                },
            },
            "other_artifact": {
                "category": "artifact",
                "content": "generic artifact",
                "metadata": {},
            },
        },
    )

    agent = FlagHunterAgent(
        llm=SimpleNamespace(),
        tools=[SimpleNamespace(name="sqlmap", enabled=True)],
        runtime=_DummyRuntime(),
        target="127.0.0.1",
        scope=["127.0.0.1/32"],
    )

    prompt = agent.get_system_prompt()

    assert "## Missing Tools (install before retry):" in prompt
    assert "- Tool 'sqlmap' not found. Install: apt install sqlmap" in prompt
