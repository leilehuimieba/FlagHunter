"""Slice 3 of the 黑板 pivot: chains-as-tools ``Hands``.

These pin the wiring contract — the tool list comes from the dispatcher's live
chain map, ``execute`` routes to ``_execute_chain`` with the bound detect context,
and ``_ChainOutcome`` is summarised back into the string the detect seam records —
against a tiny duck-typed fake dispatcher (no live LLM / detect phase).
"""

from __future__ import annotations

import pytest

from flaghunter.agents.pa_agent.blackboard_adapter import bind_seams
from flaghunter.agents.pa_agent.blackboard_hands import (
    ChainContext,
    ChainHands,
    SupportsChains,
    chain_tools,
    summarize_outcome,
)
from flaghunter.agents.pa_agent.blackboard_loop import Action, Budget, run_blackboard_solve
from flaghunter.agents.pa_agent.chains.base import _ChainOutcome
from flaghunter.agents.pa_agent.ctf_state import CTFState


class _FakeDispatcher:
    """Implements only the two methods the Hands adapter needs."""

    def __init__(self, *, outcomes=None, names=("web", "sqli", "jwt")):
        self._names = names
        self._outcomes = outcomes or {}
        self.calls: list[dict] = []
        # When a chain "wins", record the flag into this state (real chains do this),
        # so goal() composes with slice 2.
        self.state: CTFState | None = None

    def _chain_handler_map(self, *, target, page_features, hint):
        return {name: (lambda: None) for name in self._names}

    async def _execute_chain(self, *, chain_name, target, page_features, hint):
        self.calls.append(
            {"chain_name": chain_name, "target": target, "page_features": page_features, "hint": hint}
        )
        outcome = self._outcomes.get(chain_name, _ChainOutcome(progress=False, reason="no-op"))
        if outcome.flag and self.state is not None:
            self.state.add_flag(
                outcome.flag, level="runtime", evidence_source=chain_name, confidence=0.9
            )
        return outcome


def test_fake_satisfies_protocol():
    assert isinstance(_FakeDispatcher(), SupportsChains)


# --- summarize_outcome -----------------------------------------------------


def test_summarize_outcome_variants():
    assert summarize_outcome(_ChainOutcome(flag="FLAG{x}", progress=True)) == "flag=FLAG{x}"
    assert summarize_outcome(_ChainOutcome(progress=True, reason="leaked /etc/passwd")) == (
        "progress=true reason=leaked /etc/passwd"
    )
    assert summarize_outcome(_ChainOutcome()) == "progress=false"


# --- chain_tools -----------------------------------------------------------


def test_chain_tools_track_live_map_with_curated_descriptions():
    tools = chain_tools(_FakeDispatcher(names=("web", "sqli")), context=ChainContext())
    names = [t.name for t in tools]
    assert names == ["web", "sqli"]
    assert "SQL injection" in next(t for t in tools if t.name == "sqli").description


def test_chain_tools_generic_description_for_unknown_chain():
    tools = chain_tools(_FakeDispatcher(names=("novel_chain",)), context=ChainContext())
    assert tools[0].description == "novel_chain chain"


def test_chain_tools_resolves_callable_context():
    disp = _FakeDispatcher(names=("web",))
    tools = chain_tools(disp, context=lambda: ChainContext(target="t", page_features={"a": 1}))
    assert [t.name for t in tools] == ["web"]


# --- ChainHands.execute ----------------------------------------------------


@pytest.mark.asyncio
async def test_execute_routes_with_bound_context_and_summarises():
    disp = _FakeDispatcher(outcomes={"sqli": _ChainOutcome(progress=True, reason="dumped users")})
    hands = ChainHands(disp, context=ChainContext(target="ex.com", page_features={"endpoints": ["/x"]}, hint="h"))
    result = await hands.execute("sqli", {})

    assert result == "progress=true reason=dumped users"
    call = disp.calls[0]
    assert call["chain_name"] == "sqli"
    assert call["target"] == "ex.com"
    assert call["page_features"] == {"endpoints": ["/x"]}
    assert call["hint"] == "h"


@pytest.mark.asyncio
async def test_execute_fires_on_outcome_hook_with_raw_outcome():
    disp = _FakeDispatcher(outcomes={"web": _ChainOutcome(flag="FLAG{x}", reason="found")})
    seen = []
    hands = ChainHands(disp, context=ChainContext(), on_outcome=lambda name, oc: seen.append((name, oc)))
    await hands.execute("web", {})
    assert seen[0][0] == "web"
    assert seen[0][1].flag == "FLAG{x}"


@pytest.mark.asyncio
async def test_execute_input_overrides_hint_and_target():
    disp = _FakeDispatcher()
    hands = ChainHands(disp, context=ChainContext(target="base", hint="base-hint"))
    await hands.execute("web", {"target": "override", "hint": "focus-here"})
    assert disp.calls[0]["target"] == "override"
    assert disp.calls[0]["hint"] == "focus-here"


# --- end-to-end: slice 1 loop + slice 2 seams + slice 3 hands --------------


class _ScriptedBrain:
    def __init__(self, actions):
        self._actions = list(actions)

    async def propose(self, view, tools):
        return self._actions.pop(0)


@pytest.mark.asyncio
async def test_loop_solves_via_chain_tool_recorded_through_seams():
    state = CTFState(target="ex.com", goal="flag")
    disp = _FakeDispatcher(outcomes={"sqli": _ChainOutcome(flag="FLAG{won}")})
    disp.state = state  # winning chain records the flag into state (real behaviour)

    context = ChainContext(target="ex.com", page_features={"endpoints": ["/login"]})
    tools = chain_tools(disp, context=context)
    hands = ChainHands(disp, context=context)
    brain = _ScriptedBrain(
        [Action(kind="call_tool", tool="sqli", input={}, expected_signal="FLAG{")]
    )

    outcome = await run_blackboard_solve(
        brain=brain,
        hands=hands,
        tools=tools,
        budget=Budget(max_steps=10),
        **bind_seams(state),
    )

    # The sqli chain found the flag (recorded into state); the next goal() projection
    # saw it and the loop reported solved. The tool result was recorded via the detect seam.
    assert outcome.solved is True
    assert outcome.flag == "FLAG{won}"
    assert any(o.kind == "tool_result" and "flag=FLAG{won}" in o.value for o in state.observations)
