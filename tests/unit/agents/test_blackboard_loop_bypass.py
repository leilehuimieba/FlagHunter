"""Slice 5a of the 黑板 pivot: the live ``_run_solve_loop`` feature-flag bypass.

Pins the cutover wiring: behind ``FLAGHUNTER_BLACKBOARD_LOOP`` the dispatcher drives
the solve with the model-driven Shape-A loop (chains-as-tools + CTFState seams + LLM
brain) and maps its ``SolveOutcome`` onto a ``SolveResult``. Default-OFF means the
chain-order harness is byte-unchanged (guarded by the 705-test suite staying green).
"""

from __future__ import annotations

import pytest

from flaghunter.agents.pa_agent.chains.base import _ChainOutcome
from flaghunter.agents.pa_agent.ctf_dispatcher import (
    CTFTaskDispatcher,
    SolveResult,
    _blackboard_loop_enabled,
)
from flaghunter.agents.pa_agent.ctf_state import CTFState


class _FakeRuntime:
    name = "fake"


class _FakeLLM:
    """Scripts the brain: probe the web tool, then stop."""

    def __init__(self, replies):
        self._replies = iter(replies)

    async def generate(self, system_prompt, messages, *, tools=None, max_tokens=None, task_hint="default"):
        return type("R", (), {"content": next(self._replies)})()


def _dispatcher(llm):
    disp = CTFTaskDispatcher(runtime=_FakeRuntime(), llm=llm)
    disp.state = CTFState(target="ex.com", goal="flag")
    return disp


# --- env flag --------------------------------------------------------------


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("FLAGHUNTER_BLACKBOARD_LOOP", raising=False)
    assert _blackboard_loop_enabled() is False


def test_flag_reads_truthy(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_BLACKBOARD_LOOP", "TRUE")
    assert _blackboard_loop_enabled() is True
    monkeypatch.setenv("FLAGHUNTER_BLACKBOARD_LOOP", "0")
    assert _blackboard_loop_enabled() is False


# --- bypass mapping --------------------------------------------------------


@pytest.mark.asyncio
async def test_blackboard_loop_maps_winning_outcome(monkeypatch):
    llm = _FakeLLM(
        [
            '{"kind":"call_tool","tool":"web","input":{},"expected_signal":"FLAG{"}',
            '{"kind":"stop","rationale":"done"}',
        ]
    )
    disp = _dispatcher(llm)
    # Keep finalize light (avoid strategy-memory IO in this focused unit).
    async def _identity(result):
        return result

    monkeypatch.setattr(disp, "_finalize_solve_result", _identity)
    # Override the chain seam: the web tool "finds" the flag and records it into state
    # (real chains do this), so goal() reports solved.
    monkeypatch.setattr(
        disp,
        "_chain_handler_map",
        lambda *, target, page_features, hint: {"web": (lambda: None), "sqli": (lambda: None)},
    )

    async def _fake_execute_chain(*, chain_name, target, page_features, hint):
        if chain_name == "web":
            disp.state.add_flag("FLAG{won}", level="runtime", evidence_source="web", confidence=0.9)
            return _ChainOutcome(progress=True, flag="FLAG{won}", reason="found in body")
        return _ChainOutcome(progress=False, reason="no-op")

    monkeypatch.setattr(disp, "_execute_chain", _fake_execute_chain)

    result = await disp._run_blackboard_loop(
        target="ex.com", hint="", page_features={"endpoints": ["/"]}, result=SolveResult(success=False)
    )

    assert result.success is True
    assert result.flag == "FLAG{won}"
    assert result.reason == "blackboard_loop:goal_met"
    assert "web" in result.chain_used


@pytest.mark.asyncio
async def test_blackboard_loop_maps_unsolved_stop(monkeypatch):
    llm = _FakeLLM(['{"kind":"stop","rationale":"nothing to do"}'])
    disp = _dispatcher(llm)

    async def _identity(result):
        return result

    monkeypatch.setattr(disp, "_finalize_solve_result", _identity)
    monkeypatch.setattr(
        disp, "_chain_handler_map", lambda *, target, page_features, hint: {"web": (lambda: None)}
    )

    result = await disp._run_blackboard_loop(
        target="ex.com", hint="", page_features={}, result=SolveResult(success=False)
    )

    assert result.success is False
    assert result.flag is None
    assert result.reason == "blackboard_loop:brain_stop"
