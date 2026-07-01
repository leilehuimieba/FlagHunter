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

    # The chain only *asserts* the flag via outcome.flag; it does NOT touch state.
    # The bypass's terminal-success promotion (on_outcome) must turn that into a
    # runtime flag so goal() reports solved — that is the 5b cut-1 wiring under test.
    async def _fake_execute_chain(*, chain_name, target, page_features, hint):
        if chain_name == "web":
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
    # The asserted flag was promoted into state (so goal() could see it).
    assert any(f.value == "FLAG{won}" for f in disp.state.runtime_flags)


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


@pytest.mark.asyncio
async def test_blackboard_loop_marks_repertoire_miss_on_clean_giveup(monkeypatch):
    # ④ give-up 点法 migration: a failed solve with no runtime/candidate flag means the
    # closed repertoire was exhausted → the loop must set repertoire_miss so the CLI
    # radar-capture can sink it (the chain-order path does this via recovery.finalize,
    # which this loop never reaches). Without the wiring the miss evaporates on this path.
    llm = _FakeLLM(['{"kind":"stop","rationale":"out of ideas"}'])
    disp = _dispatcher(llm)
    assert disp.state.repertoire_miss is False

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
    assert disp.state.repertoire_miss is True


@pytest.mark.asyncio
async def test_blackboard_loop_does_not_mark_miss_on_win(monkeypatch):
    # A solved run is never a repertoire miss — the give-up marking is gated on failure.
    llm = _FakeLLM(
        [
            '{"kind":"call_tool","tool":"web","input":{},"expected_signal":"FLAG{"}',
            '{"kind":"stop","rationale":"done"}',
        ]
    )
    disp = _dispatcher(llm)

    async def _identity(result):
        return result

    monkeypatch.setattr(disp, "_finalize_solve_result", _identity)
    monkeypatch.setattr(
        disp,
        "_chain_handler_map",
        lambda *, target, page_features, hint: {"web": (lambda: None)},
    )

    async def _fake_execute_chain(*, chain_name, target, page_features, hint):
        return _ChainOutcome(progress=True, flag="FLAG{won}", reason="found")

    monkeypatch.setattr(disp, "_execute_chain", _fake_execute_chain)

    result = await disp._run_blackboard_loop(
        target="ex.com", hint="", page_features={}, result=SolveResult(success=False)
    )

    assert result.success is True
    assert disp.state.repertoire_miss is False


@pytest.mark.asyncio
async def test_blackboard_loop_emits_step_breadcrumbs(monkeypatch):
    """5b cut-2: the loop must not be a black box live — each brain decision is
    surfaced to the progress stream AND persisted into the notes log (so the trail
    survives the in-memory CTFState after the process exits)."""
    llm = _FakeLLM(
        [
            '{"kind":"call_tool","tool":"web","input":{},"rationale":"probe root","expected_signal":"FLAG{"}',
            '{"kind":"stop","rationale":"nothing left"}',
        ]
    )
    disp = _dispatcher(llm)
    emitted: list[str] = []
    disp.progress_callback = emitted.append

    async def _identity(result):
        return result

    monkeypatch.setattr(disp, "_finalize_solve_result", _identity)
    monkeypatch.setattr(
        disp, "_chain_handler_map", lambda *, target, page_features, hint: {"web": (lambda: None)}
    )

    async def _fake_execute_chain(*, chain_name, target, page_features, hint):
        return _ChainOutcome(progress=True, reason="saw login form")

    monkeypatch.setattr(disp, "_execute_chain", _fake_execute_chain)

    result = await disp._run_blackboard_loop(
        target="ex.com", hint="", page_features={}, result=SolveResult(success=False)
    )

    blackboard_lines = [m for m in emitted if "[blackboard]" in m]
    # step 1 = the tool call (with result preview + rationale), step 2 = stop, + done summary.
    assert any("step 1: call_tool web" in m for m in blackboard_lines)
    assert any("saw login form" in m for m in blackboard_lines)
    assert any("probe root" in m for m in blackboard_lines)
    assert any("step 2: stop" in m for m in blackboard_lines)
    assert any("done: stopped=brain_stop" in m for m in blackboard_lines)
    # The same trail persists into the notes log (which _finalize copies into
    # result.notes / session events — surviving the in-memory state after exit).
    assert any("step 1: call_tool web" in n for n in disp._notes_log)
