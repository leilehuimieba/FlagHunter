from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import pentestagent.tools.notes as notes_module
from pentestagent.agents.pa_agent.pa_agent import PentestAgentAgent
from pentestagent.tools.executor import ToolExecutor
from pentestagent.tools.notes import set_notes_file
from pentestagent.tools.registry import Tool, ToolSchema


class _PlannerAwareLLM:
    def __init__(self):
        self.last_prompt = ""

    async def generate(
        self, system_prompt, messages, tools, task_hint="default", **kwargs
    ):
        self.last_prompt = messages[0]["content"]
        has_missing_tool = "缺失工具（重试前优先安装）:" in self.last_prompt
        payload = {
            "objective": "处理 SQL 注入挑战",
            "phases": [
                {
                    "phase": 1,
                    "name": "准备",
                    "steps": [
                        {
                            "step": 1,
                            "tool": "terminal",
                            "args": {
                                "command": (
                                    "apt install sqlmap"
                                    if has_missing_tool
                                    else "echo skip install"
                                )
                            },
                            "purpose": (
                                "安装缺失的 sqlmap"
                                if has_missing_tool
                                else "跳过安装"
                            ),
                            "depends_on": [],
                        }
                    ],
                },
                {
                    "phase": 2,
                    "name": "利用",
                    "steps": [
                        {
                            "step": 2,
                            "tool": "sqlmap",
                            "args": {"url": "http://127.0.0.1:8080/vuln.php?id=1"},
                            "purpose": "测试 SQL 注入",
                            "depends_on": [],
                        }
                    ],
                },
            ],
            "risk_level": "medium",
            "estimated_steps": 2,
        }
        return SimpleNamespace(
            content=json.dumps(payload, ensure_ascii=False),
            tool_calls=None,
            usage={"total_tokens": 1},
        )


class _DummyRuntime:
    def __init__(self):
        self.environment = SimpleNamespace()
        self.plan = None


@pytest.fixture
def isolated_notes(tmp_path):
    notes_file = tmp_path / "notes.json"
    set_notes_file(notes_file)
    notes_module._notes.clear()
    yield notes_file
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


def _missing_sqlmap_tool() -> Tool:
    async def fn(arguments: dict, runtime) -> str:
        raise RuntimeError("command not found")

    return Tool(
        name="sqlmap",
        description="",
        schema=ToolSchema(properties={"cmd": {"type": "string"}}),
        execute_fn=fn,
    )


@pytest.mark.asyncio
async def test_missing_tool_note_affects_next_auto_generated_plan(isolated_notes):
    executor = ToolExecutor(runtime=None, timeout=10, max_retries=0)
    await executor.execute(_missing_sqlmap_tool(), {"cmd": "scan"})

    llm = _PlannerAwareLLM()
    agent = PentestAgentAgent(
        llm=llm,
        tools=[
            SimpleNamespace(name="sqlmap", enabled=True),
            SimpleNamespace(name="terminal", enabled=True),
        ],
        runtime=_DummyRuntime(),
        target="127.0.0.1",
        scope=["127.0.0.1/32"],
    )
    agent.conversation_history.append(
        SimpleNamespace(role="user", content="测试 127.0.0.1:8080 的 SQL 注入")
    )

    plan_msg = await agent._auto_generate_plan()

    assert plan_msg is not None
    assert "缺失工具（重试前优先安装）:" in llm.last_prompt
    assert "sqlmap" in llm.last_prompt
    assert "安装缺失的 sqlmap" in plan_msg.content
    assert "tool=terminal" in plan_msg.content
    assert "apt install sqlmap" in plan_msg.content
    assert "安装缺失的 sqlmap" in agent._task_plan.steps[0].description
