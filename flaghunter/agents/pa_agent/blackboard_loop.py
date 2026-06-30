"""Shape-A worker loop (黑板 pivot slice 1): the thin top-level driver.

The model is the driver. This loop performs the OODA *mechanics* only: project
the board, ask the brain for ONE next action, route it to the hands (tools),
record the result back to the ledger, repeat until the goal is met or the budget
runs out. It owns **no strategy** — no chain scheduling, no hypothesis ranking.

This is the loop meant to eventually REPLACE ``HypothesisEngine.choose_chain_order``
as the top-level driver. Per the strangler-fig discipline it lands additively
first (runs alongside, wired to nothing live), and the old scheduler is deleted
only once this covers it. Chains become tools the brain calls via :class:`Hands`;
the 曲库 enters as Hints on the board. See [[project_flaghunter_blackboard_pivot]]
and [[feedback_less_is_more_dont_cage_llm]] — the code gives the OODA boundary,
the model decides what to do within it.

Seams (``view`` / ``goal`` / ``record_*``) are injected so the loop is pure and
testable with fakes; binding to ``CTFState`` / ``project_board`` and the real
chains-as-tools lands in later slices. The board read-model is reused as-is
(``knowledge.blackboard_schema.BoardView``) — no second board is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Protocol, runtime_checkable

from ...knowledge.blackboard_schema import BoardView

ActionKind = Literal["call_tool", "write_fact", "declare_intent", "stop"]


@dataclass
class ToolSpec:
    """A capability the brain may invoke. Chains are wrapped as these (slice 2)."""

    name: str
    description: str


@dataclass
class Action:
    """One structured next step proposed by the brain."""

    kind: ActionKind
    rationale: str = ""
    tool: Optional[str] = None
    input: dict[str, Any] = field(default_factory=dict)
    expected_signal: Optional[str] = None
    content: str = ""  # payload for write_fact / declare_intent


@runtime_checkable
class Brain(Protocol):
    """The swappable model. One LiteLLM call behind ``propose`` (any provider)."""

    async def propose(self, view: BoardView, tools: list[ToolSpec]) -> Action: ...


@runtime_checkable
class Hands(Protocol):
    """The tool environment. ``execute(name, input) -> str`` — tools are cattle."""

    async def execute(self, name: str, input: dict[str, Any]) -> str: ...


@dataclass
class Budget:
    """Cumulative step ceiling — a cost boundary, not a scripted step count."""

    max_steps: int
    spent: int = 0

    def ok(self) -> bool:
        return self.spent < max(1, int(self.max_steps))

    def charge(self) -> None:
        self.spent += 1


@dataclass
class SolveOutcome:
    solved: bool
    flag: Optional[str]
    steps: int
    stopped: str  # "goal_met" | "brain_stop" | "budget_exhausted"


# Injected seams — real wiring (CTFState/project_board, chains-as-tools) lands later.
ViewFn = Callable[[], BoardView]
GoalFn = Callable[[], Optional[str]]  # goal met? -> flag, else None
RecordToolResultFn = Callable[[Action, str], None]
RecordContentFn = Callable[[str], None]
# Observability seam — fired once per step *after* the action is routed, so a live
# driver can surface the brain's decision trail (kind/tool/rationale + tool result).
# Pure no-op by default; the loop stays strategy-free and testable with fakes.
OnStepFn = Callable[[int, Action, Optional[str]], None]


def _noop(_content: str) -> None:  # default for optional ledger writers
    return None


def _noop_step(_step: int, _action: "Action", _result: Optional[str]) -> None:
    return None


async def run_blackboard_solve(
    *,
    brain: Brain,
    hands: Hands,
    tools: list[ToolSpec],
    view: ViewFn,
    goal: GoalFn,
    record_tool_result: RecordToolResultFn,
    budget: Budget,
    record_fact: RecordContentFn = _noop,
    declare_intent: RecordContentFn = _noop,
    on_step: OnStepFn = _noop_step,
) -> SolveOutcome:
    """Drive the board toward ``goal`` by asking ``brain`` for one action at a time.

    The brain reads the projected board (Observe/Orient), proposes one Action
    (Decide), the loop routes it to the hands (Act) and records the result so the
    next projection reflects it. Stops on goal, the brain's own ``stop``, or the
    budget. Verification of a tool result into a Fact happens inside
    ``record_tool_result`` (the §3.5 detect/verify seam), keeping this loop strategy-free.
    """
    while budget.ok():
        won = goal()
        if won is not None:
            return SolveOutcome(True, won, budget.spent, "goal_met")

        action = await brain.propose(view(), list(tools))
        budget.charge()

        if action.kind == "stop":
            on_step(budget.spent, action, None)
            won = goal()
            return SolveOutcome(won is not None, won, budget.spent, "brain_stop")
        if action.kind == "call_tool":
            result = await hands.execute(str(action.tool or ""), dict(action.input))
            record_tool_result(action, result)
            on_step(budget.spent, action, result)
        elif action.kind == "write_fact":
            record_fact(action.content)
            on_step(budget.spent, action, None)
        elif action.kind == "declare_intent":
            declare_intent(action.content)
            on_step(budget.spent, action, None)
        else:
            on_step(budget.spent, action, None)

    won = goal()
    return SolveOutcome(won is not None, won, budget.spent, "budget_exhausted")


__all__ = [
    "Action",
    "Brain",
    "Hands",
    "ToolSpec",
    "Budget",
    "SolveOutcome",
    "OnStepFn",
    "run_blackboard_solve",
]
