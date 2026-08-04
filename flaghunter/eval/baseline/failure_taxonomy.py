"""Cluster non-solved scorecard rows into a data-driven optimization backlog.

D-05 (§13.5 Phase D ← §6.18 item 8: "failure taxonomy 直接生成优化 backlog，避免手工
挑选结果"). The report stops being just "solve@1 N%" and becomes "here are the failure
classes, ranked, each an actionable backlog item" — so the next optimization is
chosen by data, not by hand-picking one challenge to tell a story about. This module
also emits the §6.18 item-3 outcome breakdown (pass / honest-stop / false-success /
infra-failure / timeout) because it reads the same scorecard surface.

The load-bearing signals, all carried on ``ScorecardRow``:
  - ``verdict``        solved | near | fail | error | skipped
  - ``stop_reason``    the dispatcher's proof-gated terminal reason
                       (goal_met | brain_stop | budget_exhausted), or None
  - ``timed_out``      the subprocess hit the wall clock
  - ``tier`` + ``matched_expectation``   a T2/T3 fail that MATCHES its prediction is
                       a confirmed capability ceiling, not a backlog regression
  - ``diseases``       fixation | spinning | reachability (chronic-disease cues)

Priority is driven by tier×expectation (how urgent); the suggested action is driven
by stop_reason×disease (what to actually do). The two are orthogonal on purpose — a
T1 miss is P0 regardless of *why* it missed, and the diagnosis then says how to fix
it. Confirmed ceilings are excluded from the backlog (recorded separately): they are
predicted outcomes, not bugs.
"""

from __future__ import annotations

from dataclasses import dataclass

from .runner import ScorecardRow

_SOLVED = "solved"
_NEAR = "near"
_FAIL = "fail"
_ERROR = "error"
_SKIPPED = "skipped"


def outcome_breakdown(rows: list[ScorecardRow]) -> dict[str, int]:
    """Partition scored (non-skipped) rows into the §6.18 item-3 outcome classes.

    ``false_success`` is the *caught* monitor: a flag-shaped string the judge
    correctly refused to bless as SOLVED (a ``near`` verdict that still carries a
    ``flag_found``). It is a positive signal that the D-02 proof gate is working —
    never an alarm. The alarm condition — a SOLVED verdict with no proof — is
    structurally impossible post-D-02 and is surfaced separately as
    ``false_success_uncaught`` (must stay 0; a nonzero value means the proof gate
    regressed).
    """
    out = {
        "pass": 0,
        "honest_stop": 0,
        "false_success": 0,
        "infra_failure": 0,
        "timeout": 0,
        "false_success_uncaught": 0,
    }
    for r in rows:
        if r.verdict == _SKIPPED:
            continue
        if r.verdict == _SOLVED:
            out["pass"] += 1
            # A SOLVED must be proof-backed: goal_met (live) or a known-flag oracle
            # run (no terminal line but a captured flag). Anything else is an alarm.
            if r.stop_reason not in (None, "goal_met") and not r.flag_found:
                out["false_success_uncaught"] += 1
        elif r.verdict == _ERROR:
            out["timeout" if r.timed_out else "infra_failure"] += 1
        elif r.verdict == _NEAR and r.flag_found:
            out["false_success"] += 1
        else:  # near without a flag, or fail — an honest not-solved
            out["honest_stop"] += 1
    return out


@dataclass(frozen=True)
class BacklogItem:
    challenge_id: str
    tier: str
    priority: str  # P0 | P1 | P2
    failure_class: str
    stop_reason: str | None
    diseases: tuple[str, ...]
    suggested_action: str


def _is_confirmed_ceiling(r: ScorecardRow) -> bool:
    """A T2/T3 fail/near that matches its prediction — a confirmed capability
    ceiling, not a regression. These are recorded, never backlogged."""
    return (
        r.matched_expectation and r.tier in ("T2", "T3") and r.verdict in (_FAIL, _NEAR)
    )


def _diagnose(r: ScorecardRow) -> tuple[str, str]:
    """Return ``(failure_class, suggested_action)`` from the run's failure signals."""
    if r.verdict == _ERROR:
        if r.timed_out:
            return (
                "timeout",
                "题超时：核 timeout_s 与 runtime/VM 延迟（基建，非能力缺口）",
            )
        return "infra_failure", "基建修复：runtime/VM/代理不可用（非能力缺口）"
    if "reachability" in r.diseases or r.stop_reason == "repertoire_miss":
        return (
            "reachability_gap",
            "可达性桥接：把制胜向量接进 WEB_STRATEGY_ORDER（bab6e7f/9b9aef3 同构）",
        )
    if r.stop_reason == "budget_exhausted" or "spinning" in r.diseases:
        return (
            "budget_waste",
            "收紧进度判据 / breadth-exhaustion trigger（436673c 同构）",
        )
    if "fixation" in r.diseases:
        return "fixation", "负反馈粒度 / 向量去重（5cd0d6d 同构）"
    if r.stop_reason == "brain_stop":
        return (
            "capability_depth",
            "能力扩面：建模该 exploit 家族（PHP 对象注入/二次注入/WAF 盲注同构）",
        )
    return "unclassified", "亲核该题走哪条 loop 与失败信号"


def _priority(r: ScorecardRow, failure_class: str) -> str:
    if failure_class in ("infra_failure", "timeout"):
        return "P0"  # blocks measurement itself
    if r.tier in ("T0", "T1") and not r.matched_expectation:
        return "P0"  # a floor challenge that should solve but didn't = regression
    if failure_class in ("reachability_gap", "budget_waste", "fixation"):
        return "P1"
    return "P2"  # capability_depth / unclassified


def build_backlog(
    rows: list[ScorecardRow],
) -> tuple[list[BacklogItem], list[ScorecardRow]]:
    """Cluster non-solved rows into a ranked backlog.

    Returns ``(backlog, ceilings)``: ``backlog`` is P0→P2 ordered actionable items;
    ``ceilings`` are the confirmed capability ceilings, recorded but not backlogged.
    """
    backlog: list[BacklogItem] = []
    ceilings: list[ScorecardRow] = []
    for r in rows:
        if r.verdict in (_SOLVED, _SKIPPED):
            continue
        if _is_confirmed_ceiling(r):
            ceilings.append(r)
            continue
        failure_class, action = _diagnose(r)
        backlog.append(
            BacklogItem(
                challenge_id=r.challenge_id,
                tier=r.tier,
                priority=_priority(r, failure_class),
                failure_class=failure_class,
                stop_reason=r.stop_reason,
                diseases=tuple(r.diseases),
                suggested_action=action,
            )
        )
    rank = {"P0": 0, "P1": 1, "P2": 2}
    backlog.sort(
        key=lambda b: (rank.get(b.priority, 9), b.failure_class, b.challenge_id)
    )
    return backlog, ceilings
