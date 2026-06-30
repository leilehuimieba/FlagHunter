"""Slice 1 of the 黑板 pivot: the thin Shape-A worker loop, tested with fakes.

The loop is strategy-free OODA mechanics. These tests pin that contract: it asks
the brain for one action, routes tool calls to the hands, records results, and
stops on goal / brain-stop / budget — deterministically, no live coupling.
"""

from __future__ import annotations

import pytest

from flaghunter.agents.pa_agent.blackboard_loop import (
    Action,
    Brain,
    Budget,
    Hands,
    ToolSpec,
    run_blackboard_solve,
)
from flaghunter.knowledge.blackboard_schema import BoardView


class _ScriptedBrain:
    """Returns a fixed queue of actions; records the views it was shown."""

    def __init__(self, actions: list[Action]) -> None:
        self._actions = list(actions)
        self.seen_views: list[BoardView] = []

    async def propose(self, view: BoardView, tools: list[ToolSpec]) -> Action:
        self.seen_views.append(view)
        return self._actions.pop(0)


class _FakeHands:
    def __init__(self, outputs: dict[str, str]) -> None:
        self._outputs = outputs
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, name: str, input: dict) -> str:
        self.calls.append((name, dict(input)))
        return self._outputs.get(name, "")


def _view() -> BoardView:
    return BoardView()


def test_protocols_are_satisfied_by_fakes():
    assert isinstance(_ScriptedBrain([]), Brain)
    assert isinstance(_FakeHands({}), Hands)


@pytest.mark.asyncio
async def test_tool_call_then_goal_met():
    brain = _ScriptedBrain([Action(kind="call_tool", tool="web", input={"u": "/"})])
    hands = _FakeHands({"web": "flag{found}"})
    recorded: list[tuple[Action, str]] = []
    # goal: met only after the tool ran (i.e. once a result has been recorded).
    goal = lambda: "flag{found}" if recorded else None

    outcome = await run_blackboard_solve(
        brain=brain,
        hands=hands,
        tools=[ToolSpec("web", "web chain")],
        view=_view,
        goal=goal,
        record_tool_result=lambda a, r: recorded.append((a, r)),
        budget=Budget(max_steps=10),
    )

    assert hands.calls == [("web", {"u": "/"})]
    assert recorded[0][1] == "flag{found}"
    assert outcome.solved is True
    assert outcome.flag == "flag{found}"
    assert outcome.stopped == "goal_met"
    assert outcome.steps == 1


@pytest.mark.asyncio
async def test_brain_stop_unsolved():
    brain = _ScriptedBrain([Action(kind="stop", rationale="no path")])
    outcome = await run_blackboard_solve(
        brain=brain,
        hands=_FakeHands({}),
        tools=[],
        view=_view,
        goal=lambda: None,
        record_tool_result=lambda a, r: None,
        budget=Budget(max_steps=10),
    )
    assert outcome.solved is False
    assert outcome.flag is None
    assert outcome.stopped == "brain_stop"


@pytest.mark.asyncio
async def test_budget_exhausted_bounds_the_loop():
    # Brain keeps proposing no-op tool calls; budget must stop it.
    brain = _ScriptedBrain([Action(kind="call_tool", tool="noop") for _ in range(10)])
    outcome = await run_blackboard_solve(
        brain=brain,
        hands=_FakeHands({"noop": ""}),
        tools=[ToolSpec("noop", "")],
        view=_view,
        goal=lambda: None,
        record_tool_result=lambda a, r: None,
        budget=Budget(max_steps=3),
    )
    assert outcome.stopped == "budget_exhausted"
    assert outcome.steps == 3
    assert outcome.solved is False


@pytest.mark.asyncio
async def test_write_fact_and_declare_intent_route_to_ledger():
    brain = _ScriptedBrain(
        [
            Action(kind="write_fact", content="port 80 open"),
            Action(kind="declare_intent", content="probe /admin"),
            Action(kind="stop"),
        ]
    )
    facts: list[str] = []
    intents: list[str] = []
    outcome = await run_blackboard_solve(
        brain=brain,
        hands=_FakeHands({}),
        tools=[],
        view=_view,
        goal=lambda: None,
        record_tool_result=lambda a, r: None,
        record_fact=facts.append,
        declare_intent=intents.append,
        budget=Budget(max_steps=10),
    )
    assert facts == ["port 80 open"]
    assert intents == ["probe /admin"]
    assert outcome.stopped == "brain_stop"
    assert outcome.steps == 3


@pytest.mark.asyncio
async def test_on_step_observes_every_decision_with_tool_result():
    """5b cut-2: the observability seam fires once per step with (step, action, result).

    ``result`` is the tool output only for ``call_tool`` (so a live driver can preview
    it), and ``None`` for fact/intent/stop. This is the trail that turns a failed solve
    from a black box into something diagnosable.
    """
    brain = _ScriptedBrain(
        [
            Action(kind="call_tool", tool="sqli", input={}),
            Action(kind="declare_intent", content="try /admin next"),
            Action(kind="stop", rationale="exhausted ideas"),
        ]
    )
    steps: list[tuple[int, str, str | None]] = []

    outcome = await run_blackboard_solve(
        brain=brain,
        hands=_FakeHands({"sqli": "progress=true reason=dumped users"}),
        tools=[ToolSpec("sqli", "sqli chain")],
        view=_view,
        goal=lambda: None,
        record_tool_result=lambda a, r: None,
        budget=Budget(max_steps=10),
        on_step=lambda step, action, result: steps.append((step, action.kind, result)),
    )

    assert outcome.stopped == "brain_stop"
    # One breadcrumb per decision, numbered by the charged budget step.
    assert steps == [
        (1, "call_tool", "progress=true reason=dumped users"),
        (2, "declare_intent", None),
        (3, "stop", None),
    ]


@pytest.mark.asyncio
async def test_on_step_defaults_to_noop():
    # Omitting on_step must not change behaviour (pure default seam).
    brain = _ScriptedBrain([Action(kind="stop")])
    outcome = await run_blackboard_solve(
        brain=brain,
        hands=_FakeHands({}),
        tools=[],
        view=_view,
        goal=lambda: None,
        record_tool_result=lambda a, r: None,
        budget=Budget(max_steps=5),
    )
    assert outcome.stopped == "brain_stop"
