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


# Observation kinds that are NOT substantive world-state progress:
#   • tool_result — the call marker itself (handled separately below);
#   • model_fact / model_intent — the brain's own narration / stated direction
#     (source="brain"). Counting these as progress would let the model fabricate
#     "advancement" by narrating a new sentence each spin — the exact fixation gap-B
#     is meant to close. Substance must be WORLD-derived (chain findings, artifacts,
#     signal_met detections, discovered endpoints), not model self-talk.
_NON_SUBSTANTIVE_OBS_KINDS = frozenset({"tool_result", "model_fact", "model_intent"})


def _project_attempts(state: CTFState) -> list[BoardAttempt]:
    """Tally already-run tool actions from the ledger — the negative-feedback trail.

    Scans the **full** observation history (not the truncated FACTS window) so a tool
    run many times keeps a complete tally even after its individual results scroll off
    the recent-facts view — that persistence is the whole point: the smoke test showed
    the brain re-running one chain a dozen times because each result aged out and it
    never saw the pile-up. Aggregated per tool: total calls, how many made *substantive*
    progress, and the last outcome summary.

    **Progress = SUBSTANCE, not a new result string (gap-B).** The earlier version counted
    *distinct* ``tool_result`` value strings as progress. But ``summarize_outcome`` emits
    ``progress=true reason=<text>`` where ``reason`` is the chain's free-text self-report,
    and a spinning chain varies that text every call ("auth form response changed",
    "commands exhausted", …) — so distinct strings kept pace with the call count and
    :attr:`BoardAttempt.stalled` never fired. The LoveSQL live run exposed this: 24 steps,
    the cross-tool spinning cue never triggered because each tool looked like it was
    advancing. A varying reason string is NOT advancement.

    A call now counts as productive iff it actually moved WORLD state:

    * its ``tool_result`` value carries a ``flag=`` (a real extraction — the strongest
      signal, and the only substance the summary itself encodes), OR
    * its execution window introduced at least one **globally-new world-derived
      observation** — a chain finding / artifact / discovered endpoint / ``signal_met``
      detection (kind ∉ :data:`_NON_SUBSTANTIVE_OBS_KINDS`), deduped by ``(kind, value)``
      across the whole run so a chain that re-emits the SAME fact each call does not
      re-count. ``progress=true`` with no flag and no new world observation is the chain
      claiming progress it cannot show on the board — treated as non-productive, which is
      exactly what makes a varying-reason spin read as stalled.

    Chain execution appends its findings to ``state.observations`` before the loop's
    ``record_tool_result`` seam appends the ``tool_result`` marker, so the substance for
    call *k* lands in the window preceding call *k*'s marker; that window is attributed to
    call *k*.
    """
    by_tool: dict[str, list] = {}
    seen_substance: set[tuple[str, str]] = set()
    window_has_new_substance = False
    for obs in state.observations:
        kind = str(getattr(obs, "kind", "") or "")
        if kind != "tool_result":
            if kind not in _NON_SUBSTANTIVE_OBS_KINDS:
                sig = (kind, str(getattr(obs, "value", "") or ""))
                if sig not in seen_substance:
                    seen_substance.add(sig)
                    window_has_new_substance = True
            continue
        meta = getattr(obs, "metadata", {}) or {}
        tool = str(meta.get("tool") or getattr(obs, "source", "") or "").strip() or "?"
        value = str(getattr(obs, "value", "") or "")
        entry = by_tool.setdefault(tool, [0, 0, ""])
        entry[0] += 1
        if value.startswith("flag=") or window_has_new_substance:
            entry[1] += 1
        entry[2] = value
        window_has_new_substance = False
    attempts = [
        BoardAttempt(tool=tool, count=c, progress_count=p, last_result=v[:120])
        for tool, (c, p, v) in by_tool.items()
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
