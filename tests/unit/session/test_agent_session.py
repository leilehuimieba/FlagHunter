"""Unit tests for the AgentSession facade (architecture joint A)."""

import inspect

import pytest

from flaghunter.agents.base_agent import AgentMessage
from flaghunter.session.agent_session import AgentSession, RunResult


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


def test_default_builder_lives_below_interface_layer():
    """I1/P1-b: AgentSession must not import the entry/interface layer."""
    import flaghunter.session.initializer as session_initializer

    src = inspect.getsource(AgentSession.create)

    assert "interface.initializer" not in src
    assert "from .initializer import build_agent_components as builder" in src
    assert callable(session_initializer.build_agent_components)


def test_build_agent_components_publishes_resolved_model_to_singleton():
    """Single-source write-side: the resolved model lands in get_settings().

    build_agent_components is the one assembly path (invariant I2); it must
    publish whatever model the main agent runs (CLI --model / env / override)
    to the settings singleton so the singleton's readers (delegate_task
    sub-agents, web_server, mcp_tools) converge on the SAME model instead of
    drifting back to FLAGHUNTER_MODEL. Locked at source level (running the real
    heavy assembly — RAG/runtime/CPA — is not unit-testable cheaply).
    """
    import flaghunter.session.initializer as session_initializer

    src = inspect.getsource(session_initializer.build_agent_components)

    assert "update_settings(model=model)" in src
    assert "from ..config.settings import get_settings, update_settings" in src


def test_interface_initializer_is_compatibility_reexport():
    """Old imports remain valid, but the composition root is session-owned."""
    import flaghunter.interface.initializer as interface_initializer
    import flaghunter.session.initializer as session_initializer

    assert interface_initializer.build_agent_components is session_initializer.build_agent_components
    assert interface_initializer.build_runtime is session_initializer.build_runtime
    assert (
        interface_initializer.activate_workspace_for_target
        is session_initializer.activate_workspace_for_target
    )


def test_session_composition_root_characterizes_current_assembly_owner():
    """The session-owned builder remains the current assembly owner."""
    import flaghunter.interface.initializer as interface_initializer
    import flaghunter.session.agent_session as agent_session_module
    import flaghunter.session.initializer as session_initializer

    create_src = inspect.getsource(AgentSession.create)
    session_src = inspect.getsource(session_initializer)
    facade_src = inspect.getsource(agent_session_module)
    compatibility_src = inspect.getsource(interface_initializer)

    assert "from .initializer import build_agent_components as builder" in create_src
    assert "interface.initializer" not in create_src
    for forbidden_facade_token in (
        "from ..agents.pa_agent import FlagHunterAgent",
        "from ..runtime.runtime import LocalRuntime",
        "from ..runtime.docker_runtime import",
        "from ..runtime.ssh_runtime import SSHRuntime",
        "from ..llm import LLM",
        "from ..mcp import MCPManager",
        "from ..tools import get_all_tools",
    ):
        assert forbidden_facade_token not in facade_src
    for current_owner_token in (
        "from ..agents.pa_agent import FlagHunterAgent",
        "from ..runtime.runtime import LocalRuntime",
        "from ..runtime.docker_runtime import DockerConfig, DockerRuntime",
        "from ..runtime.ssh_runtime import SSHRuntime",
        "from ..llm import LLM, ModelConfig",
        "from ..mcp import MCPManager",
        "from ..tools import get_all_tools, register_tool_instance",
    ):
        assert current_owner_token in session_src

    assert "from ..session.initializer import" in compatibility_src
    assert "build_agent_components" in interface_initializer.__all__
    assert interface_initializer.build_agent_components is session_initializer.build_agent_components


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
