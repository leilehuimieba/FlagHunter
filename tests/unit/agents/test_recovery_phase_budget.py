"""P4 stopping rule — RecoveryController EXPLOIT phase-budget backstop.

The dispatcher's per-chain stopping heuristics reset ``no_progress_count`` on
any micro-progress, so a solve that keeps making tiny progress while never
producing a runtime flag can churn indefinitely. ``after_chain`` reads the
first-class EXPLOIT phase round count and stops once the budget is exhausted —
but only as a backstop that yields to any pending runtime/verified flag.
"""

from __future__ import annotations

from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.recovery import RecoveryController
from flaghunter.knowledge.kill_chain import Phase, phase_round_budget


class _NoChainEngine:
    """Hypothesis engine stub: no reranked chains available."""

    def choose_chain_order(self, state):  # noqa: ARG002 - stub
        return []


def _controller() -> RecoveryController:
    return RecoveryController(_NoChainEngine())


def _state_at_exploit_rounds(rounds: int) -> CTFState:
    state = CTFState(target="http://ctf.local", goal="g")
    state.enter_phase(Phase.EXPLOIT)
    for _ in range(rounds):
        state.record_phase_round(Phase.EXPLOIT)
    return state


def test_after_chain_stops_when_exploit_budget_exhausted_and_no_flag():
    budget = phase_round_budget(Phase.EXPLOIT)
    state = _state_at_exploit_rounds(budget)

    decision = _controller().after_chain(
        state,
        current_chain="web",
        active_hypothesis=None,
        outcome_progress=True,  # even WITH micro-progress, the backstop fires
        no_progress_count=0,
        used_chains=["web"],
    )

    assert decision.should_stop is True
    assert decision.action == "stop_phase_budget"


def test_after_chain_does_not_stop_below_exploit_budget():
    budget = phase_round_budget(Phase.EXPLOIT)
    state = _state_at_exploit_rounds(budget - 1)

    decision = _controller().after_chain(
        state,
        current_chain="web",
        active_hypothesis=None,
        outcome_progress=True,
        no_progress_count=0,
        used_chains=["web"],
    )

    assert decision.action != "stop_phase_budget"


def test_phase_budget_backstop_yields_to_pending_runtime_flag():
    # A runtime flag awaiting verification must win over the budget backstop —
    # we never throw away a real flag handoff just because churn was high.
    budget = phase_round_budget(Phase.EXPLOIT)
    state = _state_at_exploit_rounds(budget)
    state.add_flag(
        "flag{pending}",
        level="runtime",
        evidence_source="runtime_echo",
    )

    decision = _controller().after_chain(
        state,
        current_chain="web",
        active_hypothesis=None,
        outcome_progress=False,
        no_progress_count=99,
        used_chains=["web"],
    )

    assert decision.action == "wait_for_verification"
    assert decision.action != "stop_phase_budget"
