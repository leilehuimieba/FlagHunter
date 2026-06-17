from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from flaghunter.agents.crew.models import AgentStatus, AgentWorker
from flaghunter.agents.crew.tools import create_crew_tools
from flaghunter.agents.crew.worker_pool import WorkerPool
from flaghunter.tools.registry import Tool, ToolSchema


def _make_tool(name: str) -> Tool:
    async def _noop(arguments, runtime):
        return ""

    return Tool(
        name=name,
        description=f"{name} tool",
        schema=ToolSchema(type="object", properties={}, required=[]),
        execute_fn=_noop,
    )


class _DummyRuntime:
    environment = SimpleNamespace()


class _DummyLLM:
    async def generate(self, *args, **kwargs):
        return SimpleNamespace(content="", tool_calls=None, usage=None)


@pytest.mark.asyncio
async def test_worker_pool_spawn_normalizes_worker_type_and_emits_event(monkeypatch):
    events = []
    pool = WorkerPool(
        llm=_DummyLLM(),
        tools=[],
        runtime=_DummyRuntime(),
        on_worker_event=lambda worker_id, event, data: events.append(
            (worker_id, event, data)
        ),
    )

    def _fake_create_task(coro):
        coro.close()
        return SimpleNamespace(done=lambda: True)

    monkeypatch.setattr(asyncio, "create_task", _fake_create_task)

    worker_id = await pool.spawn("enumerate target", worker_type="unknown-type")
    status = pool.get_status(worker_id)

    assert worker_id == "agent-0"
    assert status is not None
    assert status["worker_type"] == "default"
    assert events == [
        (
            "agent-0",
            "spawn",
            {"worker_type": "default", "task": "enumerate target"},
        )
    ]


@pytest.mark.asyncio
async def test_run_worker_filters_tools_and_applies_specialized_prompt(monkeypatch):
    captured: dict = {}

    class _FakeLocalRuntime:
        def __init__(self):
            self.plan = None

        async def start(self):
            return None

        async def stop(self):
            return None

    class _FakeAgent:
        def __init__(
            self,
            llm,
            tools,
            runtime,
            target="",
            rag_engine=None,
            max_iterations=0,
        ):
            self.tools = tools
            self.runtime = runtime
            captured["tools"] = [t.name for t in tools]

        def get_system_prompt(self, mode: str = "agent") -> str:
            return "BASE PROMPT"

        async def agent_loop(self, task):
            captured["task"] = task
            captured["prompt"] = self.get_system_prompt()
            yield SimpleNamespace(
                content="worker complete",
                tool_calls=None,
                usage=None,
                metadata={},
            )

    async def _noop_on_complete(**kwargs):
        return None

    monkeypatch.setattr(
        "flaghunter.runtime.runtime.LocalRuntime",
        _FakeLocalRuntime,
    )
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.PentestAgentAgent",
        _FakeAgent,
    )
    monkeypatch.setattr(
        "flaghunter.agents.crew.worker_pool.on_worker_complete",
        _noop_on_complete,
    )

    pool = WorkerPool(
        llm=_DummyLLM(),
        tools=[
            _make_tool("nmap"),
            _make_tool("dirscan"),
            _make_tool("sqlmap"),
            _make_tool("notes"),
            _make_tool("finish"),
            _make_tool("terminal"),
        ],
        runtime=_DummyRuntime(),
        target="192.168.1.100",
    )

    worker = AgentWorker(id="agent-7", task="scan web surface", worker_type="web")
    await pool._run_worker(worker)

    assert worker.status == AgentStatus.COMPLETE
    assert captured["tools"] == ["dirscan", "sqlmap", "notes", "finish", "terminal"]
    assert "Worker specialization:" in captured["prompt"]
    assert "specialized web worker" in captured["prompt"]
    assert worker.result == "worker complete"


@pytest.mark.asyncio
async def test_spawn_agent_tool_exposes_worker_type_and_normalizes_unknown():
    class _Pool:
        def __init__(self):
            self.calls = []

        async def spawn(self, task, priority=1, depends_on=None, worker_type="default"):
            self.calls.append((task, priority, depends_on, worker_type))
            return "agent-3"

    pool = _Pool()
    tools = create_crew_tools(pool, _DummyLLM())
    spawn_tool = next(t for t in tools if t.name == "spawn_agent")

    result = await spawn_tool.execute(
        {
            "task": "enumerate web app",
            "priority": 2,
            "depends_on": ["agent-0"],
            "worker_type": "weird",
        },
        _DummyRuntime(),
    )

    assert pool.calls == [
        ("enumerate web app", 2, ["agent-0"], "default")
    ]
    assert result == "Spawned agent-3 [default]: enumerate web app"
    assert "worker_type" in spawn_tool.schema.properties
    assert spawn_tool.schema.properties["worker_type"]["enum"] == [
        "default",
        "web",
        "recon",
        "exploit",
        "crypto",
    ]

