"""Deterministic ``CTFState`` seams for the Shape-A blackboard loop (黑板 pivot slice 2).

Slice 1 built the strategy-free OODA driver (``blackboard_loop.run_blackboard_solve``)
with its world bound only through injected seams. This slice binds the *deterministic*
seams — ``view`` / ``goal`` / ``record_tool_result`` / ``record_fact`` /
``declare_intent`` — to a real :class:`CTFState`, using the existing pure read-model
(:func:`blackboard.project_board`) and ``CTFState``'s own append entry points. These
seams need no LLM and are fully unit-testable against a real state object.

What stays for later slices (per the strangler-fig plan in the slice-1 commit):
  * **Hands** (chains-as-tools wrapping ``dispatcher._chain_handler_map``) — slice 3.
  * **Brain** (one LiteLLM call ``BoardView`` → ``Action``; 曲库 as Hints) — slice 4.
  * Switching the live path and deleting ``HypothesisEngine.choose_chain_order`` — slice 5.

This lands additively and touches no existing file — it is the common ground both the
Hands and Brain adapters build on (they both record results back into ``CTFState``).
The code gives the boundary; the model decides within it
(see [[feedback_less_is_more_dont_cage_llm]] and [[project_flaghunter_blackboard_pivot]]).
"""

from __future__ import annotations

from typing import Callable, Optional

from ...knowledge.blackboard_schema import BoardView
from .blackboard import project_board
from .blackboard_loop import Action
from .ctf_state import CTFState, FlagRecord

# Tool results are recorded as observations that the next board projection renders;
# cap the previewed payload so a chatty tool cannot flood the board with noise.
_RESULT_PREVIEW_LIMIT = 800

# Injected-seam types (mirror ``blackboard_loop``'s aliases).
ViewFn = Callable[[], BoardView]
GoalFn = Callable[[], Optional[str]]
RecordToolResultFn = Callable[[Action, str], None]
RecordContentFn = Callable[[str], None]

# ``hints`` may be a static list or a thunk so slice 4 can inject 曲库 retrieval
# (which depends on the current board) without re-binding the view.
HintsProvider = list[str] | Callable[[], list[str]]


def _resolve_hints(hints: HintsProvider | None) -> list[str]:
    if hints is None:
        return []
    resolved = hints() if callable(hints) else hints
    return [str(h).strip() for h in (resolved or []) if str(h or "").strip()]


def make_view(
    state: CTFState,
    *,
    hints: HintsProvider | None = None,
    observation_limit: int = 12,
    intent_limit: int = 12,
) -> ViewFn:
    """Bind the ``view`` seam to the live board projection of ``state``.

    Re-projects on every call so the loop always observes the latest ledger
    (Observe/Orient). ``hints`` is resolved per call, so a thunk can surface
    board-dependent guidance (曲库 Hints, slice 4) without rebinding.
    """

    def _view() -> BoardView:
        return project_board(
            state,
            hints=_resolve_hints(hints),
            observation_limit=observation_limit,
            intent_limit=intent_limit,
        )

    return _view


def _best_flag(bucket: list[FlagRecord]) -> Optional[FlagRecord]:
    return max(bucket, key=lambda r: float(getattr(r, "confidence", 0.0) or 0.0), default=None)


def make_goal(state: CTFState) -> GoalFn:
    """Bind the ``goal`` seam: the highest-confidence *confirmed* flag, else ``None``.

    Verified flags outrank runtime flags (a verified flag is the won state).
    Candidate / rejected flags are intents on the board, not goal completion, so
    they never satisfy the goal here.
    """

    def _goal() -> Optional[str]:
        for bucket in (state.verified_flags, state.runtime_flags):
            best = _best_flag(bucket)
            if best is not None and str(getattr(best, "value", "") or "").strip():
                return str(best.value)
        return None

    return _goal


def make_record_tool_result(state: CTFState) -> RecordToolResultFn:
    """Bind ``record_tool_result``: the §3.5 detect seam.

    Always records the (previewed) tool result as a ``tool_result`` observation so
    the next projection reflects it. When the brain declared an ``expected_signal``
    and it appears in the result, an additional ``signal_met`` observation is laid
    down — a low-noise *detection* marker the model can orient on. Turning a result
    into a verified Fact/flag stays with the existing verification pipeline (slice 5
    reuses it); this seam does no flag regex of its own.
    """

    def _record(action: Action, result: str) -> None:
        text = str(result or "")
        preview = text[:_RESULT_PREVIEW_LIMIT]
        tool = str(getattr(action, "tool", "") or "").strip()
        expected = str(getattr(action, "expected_signal", "") or "").strip()
        state.add_observation(
            "tool_result",
            preview,
            source=tool,
            metadata={
                "tool": tool,
                "input": dict(getattr(action, "input", {}) or {}),
                "rationale": str(getattr(action, "rationale", "") or ""),
                "expected_signal": expected,
                "truncated": len(text) > _RESULT_PREVIEW_LIMIT,
            },
        )
        if expected and expected in text:
            state.add_observation(
                "signal_met",
                expected,
                source=tool,
                metadata={"tool": tool},
            )

    return _record


def make_record_fact(state: CTFState) -> RecordContentFn:
    """Bind ``record_fact``: the brain's asserted world-state note.

    Recorded as a ``model_fact`` observation (source ``brain``) so it surfaces as a
    Fact on the next projection without bypassing the append-only ledger.
    """

    def _record(content: str) -> None:
        text = str(content or "").strip()
        if text:
            state.add_observation("model_fact", text, source="brain")

    return _record


def make_declare_intent(state: CTFState) -> RecordContentFn:
    """Bind ``declare_intent``: the brain's stated direction.

    Recorded as a ``model_intent`` observation (source ``brain``). It is a stated
    direction, not a confirmed Fact, so it stays an observation the model can revisit
    rather than mutating hypotheses/agenda here (that ranking is the engine's job).
    """

    def _record(content: str) -> None:
        text = str(content or "").strip()
        if text:
            state.add_observation("model_intent", text, source="brain")

    return _record


def bind_seams(
    state: CTFState,
    *,
    hints: HintsProvider | None = None,
    observation_limit: int = 12,
    intent_limit: int = 12,
) -> dict[str, Callable]:
    """Bind every deterministic seam to ``state`` in one call.

    Returns the ``view`` / ``goal`` / ``record_tool_result`` / ``record_fact`` /
    ``declare_intent`` kwargs that :func:`blackboard_loop.run_blackboard_solve`
    consumes. The caller still supplies the (heavier) ``brain`` / ``hands`` / ``tools``
    / ``budget`` — slices 3 and 4.
    """

    return {
        "view": make_view(
            state,
            hints=hints,
            observation_limit=observation_limit,
            intent_limit=intent_limit,
        ),
        "goal": make_goal(state),
        "record_tool_result": make_record_tool_result(state),
        "record_fact": make_record_fact(state),
        "declare_intent": make_declare_intent(state),
    }


__all__ = [
    "make_view",
    "make_goal",
    "make_record_tool_result",
    "make_record_fact",
    "make_declare_intent",
    "bind_seams",
    "HintsProvider",
]
