"""Slice 2 of the 黑板 pivot: deterministic ``CTFState`` seams for the loop.

These pin the binding contract — ``view`` re-projects the live board, ``goal``
reports the confirmed flag, and the ``record_*`` seams append back into the real
ledger — all without an LLM, against a real :class:`CTFState`.
"""

from __future__ import annotations

import pytest

from flaghunter.agents.pa_agent.blackboard_adapter import (
    bind_seams,
    make_declare_intent,
    make_goal,
    make_record_fact,
    make_record_tool_result,
    make_view,
)
from flaghunter.agents.pa_agent.blackboard_loop import Action, Budget, run_blackboard_solve
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.knowledge.blackboard_schema import BoardView


def _state() -> CTFState:
    return CTFState(target="example.com", goal="get the flag")


# --- view ------------------------------------------------------------------


def test_view_reprojects_live_state():
    state = _state()
    view = make_view(state)
    assert view().facts == []

    state.add_observation("note", "saw /admin", source="recon")
    board = view()
    assert isinstance(board, BoardView)
    assert any(f.value == "saw /admin" for f in board.facts)


def test_view_resolves_static_and_callable_hints():
    state = _state()
    assert "from-list" in make_view(state, hints=["from-list", "  "])().hints
    assert "from-thunk" in make_view(state, hints=lambda: ["from-thunk"])().hints


# --- goal ------------------------------------------------------------------


def test_goal_none_without_confirmed_flag():
    state = _state()
    state.add_flag("FLAG{maybe}", level="candidate", evidence_source="guess", confidence=0.4)
    assert make_goal(state)() is None


def test_goal_verified_outranks_runtime_and_picks_highest_confidence():
    state = _state()
    state.add_flag("FLAG{runtime}", level="runtime", evidence_source="rt", confidence=0.9)
    state.add_flag("FLAG{low}", level="verified", evidence_source="v1", confidence=0.5)
    state.add_flag("FLAG{win}", level="verified", evidence_source="v2", confidence=0.95)
    assert make_goal(state)() == "FLAG{win}"


def test_goal_falls_back_to_runtime_when_no_verified():
    state = _state()
    state.add_flag("FLAG{rt}", level="runtime", evidence_source="rt", confidence=0.8)
    assert make_goal(state)() == "FLAG{rt}"


# --- record_tool_result (§3.5 detect seam) ---------------------------------


def test_record_tool_result_logs_observation_and_signal():
    state = _state()
    record = make_record_tool_result(state)
    action = Action(kind="call_tool", tool="sqli", input={"param": "id"}, expected_signal="root:x:")
    record(action, "uid=0 root:x:0:0 in /etc/passwd")

    tool_obs = [o for o in state.observations if o.kind == "tool_result"]
    assert len(tool_obs) == 1
    assert tool_obs[0].source == "sqli"
    assert tool_obs[0].metadata["input"] == {"param": "id"}
    assert tool_obs[0].metadata["truncated"] is False
    assert any(o.kind == "signal_met" and o.value == "root:x:" for o in state.observations)


def test_record_tool_result_no_signal_when_expectation_absent():
    state = _state()
    make_record_tool_result(state)(
        Action(kind="call_tool", tool="web", expected_signal="flag{"), "nothing here"
    )
    assert not any(o.kind == "signal_met" for o in state.observations)


def test_record_tool_result_truncates_long_payload():
    state = _state()
    make_record_tool_result(state)(Action(kind="call_tool", tool="web"), "A" * 5000)
    obs = next(o for o in state.observations if o.kind == "tool_result")
    assert len(obs.value) == 800
    assert obs.metadata["truncated"] is True


# --- record_fact / declare_intent ------------------------------------------


def test_record_fact_and_intent_append_with_brain_source():
    state = _state()
    make_record_fact(state)("app is Flask")
    make_declare_intent(state)("try SSTI on /greet")
    make_record_fact(state)("   ")  # blank is a no-op

    kinds = {(o.kind, o.value, o.source) for o in state.observations}
    assert ("model_fact", "app is Flask", "brain") in kinds
    assert ("model_intent", "try SSTI on /greet", "brain") in kinds
    assert len([o for o in state.observations if o.kind == "model_fact"]) == 1


# --- bind_seams + end-to-end through the slice-1 loop ----------------------


def test_bind_seams_returns_every_seam():
    seams = bind_seams(_state())
    assert set(seams) == {"view", "goal", "record_tool_result", "record_fact", "declare_intent"}
    assert all(callable(v) for v in seams.values())


class _ScriptedBrain:
    def __init__(self, actions):
        self._actions = list(actions)

    async def propose(self, view, tools):
        return self._actions.pop(0)


class _FakeHands:
    async def execute(self, name, input):
        return "uid=0 root:x:" if name == "sqli" else ""


@pytest.mark.asyncio
async def test_loop_drives_real_state_through_bound_seams():
    state = _state()
    brain = _ScriptedBrain(
        [
            Action(kind="declare_intent", content="probe sqli on id"),
            Action(kind="call_tool", tool="sqli", input={"p": "id"}, expected_signal="root:x:"),
            Action(kind="stop"),
        ]
    )
    outcome = await run_blackboard_solve(
        brain=brain,
        hands=_FakeHands(),
        tools=[],
        budget=Budget(max_steps=10),
        **bind_seams(state),
    )

    # The loop wrote the brain's intent and the tool result back into the real ledger.
    assert any(o.kind == "model_intent" and o.value == "probe sqli on id" for o in state.observations)
    assert any(o.kind == "tool_result" and o.source == "sqli" for o in state.observations)
    assert any(o.kind == "signal_met" for o in state.observations)
    assert outcome.stopped == "brain_stop"
