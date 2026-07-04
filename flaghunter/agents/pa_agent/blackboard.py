"""Fact / Intent / Hint blackboard projection (Workstream B, slice B1).

A pure read-model over :class:`CTFState`. It does not mutate state and performs
no I/O — it projects the run's structured state into three low-noise segments:

* **facts**   — confirmed world state: observations, artifacts, verified and
  runtime flags, and *refuted* flags (rejected candidates).
* **intents** — pending, model/rule-proposed directions with confidence: active
  hypotheses, candidate flags, and unexplored agenda items. Refuted / exhausted
  intents stay visible (marked ``refuted``) and are sorted last so the model can
  see what was already tried and switch candidates *itself* — the protocol
  expresses failure, it does not force a switch.
* **hints**   — external guidance: user hints, challenge context, and the run's
  own progress markers.

This is the shared blackboard the coordinator/solve-loop reads; the session
ledger remains the sole append-only source of truth (this view is a disposable
projection, never a second copy of the truth).
"""

from __future__ import annotations

from typing import Any

from ...knowledge.blackboard_schema import (
    BoardAttempt,
    BoardFact,
    BoardIntent,
    BoardView,
    intent_sort_key,
)
from .claim_views import claim_confidence, claim_source, preferred_flag_buckets
from .ctf_state import CTFState, FlagRecord

_REFUTED_HYPOTHESIS_STATUSES = {"rejected", "exhausted"}


def _project_attempts(state: CTFState) -> list[BoardAttempt]:
    """Tally already-run tool actions from the ledger — the negative-feedback trail.

    Scans the **full** observation history (not the truncated FACTS window) so a tool
    run many times keeps a complete tally even after its individual results scroll off
    the recent-facts view — that persistence is the whole point: the smoke test showed
    the brain re-running one chain a dozen times because each result aged out and it
    never saw the pile-up. Aggregated per tool: total calls, how many made *distinct*
    progress, and the last outcome summary. A ``tool_result`` value is productive when it
    carries a flag or ``progress=true`` (the summary shape from ``hands.summarize_outcome``)
    — but only *distinct* productive results count: ``summarize_outcome`` is deterministic,
    so a chain that keeps REPLAYING the same ``progress=true reason=…`` line collapses to a
    single distinct result. That is the "progress=true spinning" the third smoke test exposed
    (lfi hammered six times, each an identical productive-looking line): total calls climb
    while distinct progress stays at one, which :attr:`BoardAttempt.stalled` reads as a switch
    signal instead of mistaking repetition for advancement.
    """
    by_tool: dict[str, list] = {}
    for obs in state.observations:
        if str(getattr(obs, "kind", "") or "") != "tool_result":
            continue
        meta = getattr(obs, "metadata", {}) or {}
        tool = str(meta.get("tool") or getattr(obs, "source", "") or "").strip() or "?"
        value = str(getattr(obs, "value", "") or "")
        entry = by_tool.setdefault(tool, [0, set(), ""])
        entry[0] += 1
        if value.startswith("flag=") or "progress=true" in value:
            entry[1].add(value)
        entry[2] = value
    attempts = [
        BoardAttempt(tool=tool, count=c, progress_count=len(distinct), last_result=v[:120])
        for tool, (c, distinct, v) in by_tool.items()
    ]
    # Most-repeated first; among equal counts, dead ends (no progress) first so the
    # brain reads the strongest "switch away" signal at the top.
    attempts.sort(key=lambda a: (-a.count, a.progress_count))
    return attempts


def _flag_fact(record: FlagRecord, kind: str) -> BoardFact:
    return BoardFact.flag(
        kind=kind,
        value=record.value,
        source=str(getattr(record, "evidence_source", "") or ""),
        confidence=float(getattr(record, "confidence", 0.0) or 0.0),
    )


def _claim_flag_fact(claim, kind: str) -> BoardFact:
    return BoardFact.flag(
        kind=kind,
        value=str(getattr(claim, "content", "") or ""),
        source=claim_source(claim),
        confidence=claim_confidence(claim),
    )


def project_board(
    state: CTFState,
    *,
    hints: list[str] | None = None,
    observation_limit: int = 12,
    intent_limit: int = 12,
) -> BoardView:
    """Project ``state`` into the typed canonical :class:`BoardView`.

    ``observation_limit`` keeps the most recent observations; ``intent_limit``
    caps the intent list after sorting (active + highest value first, refuted
    last). Both default to small values to stay low-noise. Typed entry point;
    :func:`project_blackboard` is the dict-returning back-compat wrapper.
    """
    facts: list[BoardFact] = []
    for obs in list(state.observations)[-max(0, observation_limit):]:
        facts.append(
            BoardFact.observation(
                subkind=str(getattr(obs, "kind", "") or ""),
                value=str(getattr(obs, "value", "") or ""),
                source=str(getattr(obs, "source", "") or ""),
            )
        )
    for art in state.artifacts:
        facts.append(
            BoardFact.artifact(
                value=str(getattr(art, "name", "") or ""),
                location=getattr(art, "location", None),
                source=str(getattr(art, "source", "") or ""),
            )
        )
    flag_buckets = preferred_flag_buckets(state)
    if flag_buckets["verified"].from_claims:
        for claim in flag_buckets["verified"].items:
            facts.append(_claim_flag_fact(claim, "verified_flag"))
    else:
        for record in flag_buckets["verified"].items:
            facts.append(_flag_fact(record, "verified_flag"))
    if flag_buckets["runtime"].from_claims:
        for claim in flag_buckets["runtime"].items:
            facts.append(_claim_flag_fact(claim, "runtime_flag"))
    else:
        for record in flag_buckets["runtime"].items:
            facts.append(_flag_fact(record, "runtime_flag"))
    if flag_buckets["retracted"].from_claims:
        for claim in flag_buckets["retracted"].items:
            facts.append(_claim_flag_fact(claim, "refuted_flag"))
    else:
        for record in flag_buckets["retracted"].items:
            # A rejected flag is a refuted fact — kept visible so the loop/model
            # does not re-propose it.
            facts.append(_flag_fact(record, "refuted_flag"))

    intents: list[BoardIntent] = []
    for hyp in state.hypotheses:
        status = str(getattr(hyp, "status", "active") or "active")
        next_experiments = list(getattr(hyp, "next_experiments", []) or [])
        supporting = list(getattr(hyp, "supporting_observations", []) or [])
        intents.append(
            BoardIntent(
                id=str(getattr(hyp, "id", "") or ""),
                kind=str(getattr(hyp, "kind", "") or ""),
                description=str(getattr(hyp, "description", "") or ""),
                confidence=float(getattr(hyp, "confidence", 0.0) or 0.0),
                value_score=float(getattr(hyp, "value_score", 0.0) or 0.0),
                status=status,
                refuted=status in _REFUTED_HYPOTHESIS_STATUSES,
                next_experiments=next_experiments,
                # Directness (走最短链): accumulated evidence minus remaining
                # steps. Higher = closer to the flag / shorter remaining path.
                directness=len(supporting) - len(next_experiments),
                origin="hypothesis",
            )
        )
    for item in state.exploration_agenda:
        if getattr(item, "explored", False):
            continue
        intents.append(
            BoardIntent(
                id=str(getattr(item, "id", "") or ""),
                kind="exploration",
                description=str(getattr(item, "url_or_path", "") or ""),
                confidence=float(getattr(item, "hint_strength", 0) or 0) / 10.0,
                value_score=float(getattr(item, "hint_strength", 0) or 0) / 10.0,
                status="active",
                refuted=False,
                next_experiments=[],
                directness=0,
                origin="exploration_agenda",
            )
        )
    if flag_buckets["candidate"].from_claims:
        for claim in flag_buckets["candidate"].items:
            confidence = claim_confidence(claim)
            intents.append(
                BoardIntent(
                    id=str(getattr(claim, "id", "") or ""),
                    kind="candidate_flag",
                    description=str(getattr(claim, "content", "") or ""),
                    confidence=confidence,
                    value_score=confidence,
                    status="active",
                    refuted=False,
                    next_experiments=[],
                    directness=2,
                    origin="claim_store",
                )
            )
    else:
        for record in flag_buckets["candidate"].items:
            intents.append(
                BoardIntent(
                    id="",
                    kind="candidate_flag",
                    description=str(getattr(record, "value", "") or ""),
                    confidence=float(getattr(record, "confidence", 0.0) or 0.0),
                    value_score=float(getattr(record, "confidence", 0.0) or 0.0),
                    status="active",
                    refuted=False,
                    next_experiments=[],
                    # A candidate flag is the most direct intent — one verify step away.
                    directness=2,
                    origin="candidate_flag",
                )
            )

    # Active first; among active, highest value, then most direct (shortest
    # remaining path — 走最短链), then highest confidence. Refuted/exhausted
    # intents stay last but visible (so the model sees what was already tried).
    intents.sort(key=intent_sort_key)
    if intent_limit >= 0:
        intents = intents[:intent_limit]

    hint_list: list[str] = [str(h).strip() for h in (hints or []) if str(h or "").strip()]
    last_progress = str(getattr(state, "last_progress_marker", "") or "").strip()
    if last_progress:
        hint_list.append(f"last_progress={last_progress}")
    stop_reason = str(getattr(state, "stop_reason", "") or "").strip()
    if stop_reason:
        hint_list.append(f"stop_reason={stop_reason}")

    return BoardView(
        facts=facts,
        intents=intents,
        hints=hint_list,
        attempts=_project_attempts(state),
    )


def project_blackboard(
    state: CTFState,
    *,
    hints: list[str] | None = None,
    observation_limit: int = 12,
    intent_limit: int = 12,
) -> dict[str, Any]:
    """Dict-returning back-compat wrapper over :func:`project_board`.

    Byte-identical to the previous ad-hoc projection — existing consumers and
    tests are unchanged.
    """
    return project_board(
        state,
        hints=hints,
        observation_limit=observation_limit,
        intent_limit=intent_limit,
    ).to_dict()
