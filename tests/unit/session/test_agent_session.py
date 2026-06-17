"""Unit tests for the AgentSession facade (architecture joint A)."""

import pytest

from pentestagent.agents.base_agent import AgentMessage
from pentestagent.session.agent_session import AgentSession, RunResult


class _FakeAgent:
    """Minimal agent whose agent_loop yields a scripted message sequence."""

    def __init__(self, messages, *, raise_on=None):
        self._messages = messages
        self._raise_on = raise_on
        self.llm = object()
        self.seen_task = None

    async def agent_loop(self, task):
        self.seen_task = task
        for msg in self._messages:
            if self._raise_on is not None and msg.content == self._raise_on:
                raise RuntimeError("boom")
            yield msg


def _components(agent, **extra):
    base = {"agent": agent, "runtime": object(), "all_tools": [], "model": "fake-model"}
    base.update(extra)
    return base


@pytest.mark.asyncio
async def test_create_funnels_builder_and_exposes_components():
    captured = {}

    async def fake_builder(**kwargs):
        captured.update(kwargs)
        return _components(_FakeAgent([]), runtime_info={"selected": "local"})

    session = await AgentSession.create(
        target="example.com", model="m", no_mcp=True, builder=fake_builder
    )

    # I2: construction went through the single builder, params forwarded.
    assert captured["target"] == "example.com"
    assert captured["model"] == "m"
    assert captured["no_mcp"] is True
    # components exposed
    assert session.model == "fake-model"
    assert session.runtime_info == {"selected": "local"}
    assert session.agent is not None
    assert session.llm is session.agent.llm


@pytest.mark.asyncio
async def test_run_drives_loop_emits_events_and_accumulates():
    messages = [
        AgentMessage(role="assistant", content="thinking", tool_calls=[1], usage={"total_tokens": 10}),
        AgentMessage(role="assistant", content="final answer", usage={"total_tokens": 5}),
    ]
    agent = _FakeAgent(messages)
    session = AgentSession(_components(agent))

    events = []
    session.events().subscribe(events.append)

    result = await session.run("do the thing")

    assert isinstance(result, RunResult)
    assert result.status == "completed"
    assert result.iterations == 2
    assert result.tokens == 15
    assert result.output == "final answer"  # last plain assistant message
    assert agent.seen_task == "do the thing"

    types = [e.type for e in events]
    assert types[0] == "run_start"
    assert types.count("agent_message") == 2
    assert types[-1] == "run_complete"


@pytest.mark.asyncio
async def test_run_error_returns_error_result_not_raise():
    messages = [
        AgentMessage(role="assistant", content="ok"),
        AgentMessage(role="assistant", content="explode"),
    ]
    session = AgentSession(_components(_FakeAgent(messages, raise_on="explode")))

    events = []
    session.events().subscribe(events.append)

    result = await session.run("task")

    assert result.status == "error"
    assert "boom" in (result.error or "")
    assert any(e.type == "run_error" for e in events)


@pytest.mark.asyncio
async def test_run_without_agent_raises():
    session = AgentSession({"agent": None})
    with pytest.raises(RuntimeError):
        await session.run("task")
