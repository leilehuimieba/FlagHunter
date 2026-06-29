"""Emergent-chain scoring — reuse reward + negative feedback (P7 — 闭环波).

Builds on P6 (``knowledge/emergent_chains.py``). P6 *describes* which tool
sequences recur and how they correlate with flags; P7 adds the **judgement
lens**: a per-chain score that rewards *reuse* (sequences that led to flags) and
penalises *negative feedback* (sequences whose calls keep erroring). The output
classifies each chain as ``reuse`` / ``neutral`` / ``avoid`` and surfaces the
``avoid`` set as explicit negative-feedback candidates.

Why this is not a duplicate of ``agents/pa_agent/strategy_memory.py``:
  * strategy_memory scores **strategy-kind** sequences (coarse: ``web``/``sqli``),
    drawn from per-challenge *retrospectives* recorded only at solve time, gated
    by fingerprint similarity, and it is already wired into chain ordering.
  * this module scores **tool-call** sequences (fine:
    ``param_discovery→generic_param_sqli``) mined from *every* provenance call —
    so it sees the futile / error-prone tool spinning that a solve-time
    retrospective structurally never records.

Honest v1 boundary (continues P6's discipline):
  * **read-only** — this produces a ranking + verdicts; nothing here feeds back
    into chain ordering or the orchestrator prompt. Injecting the score into live
    decisions (回灌) is **P8**. So the default solve path stays byte-identical.
  * **descriptive, not causal** — flag-correlation and error-rate are signals,
    not proof a chain caused (or doomed) a solve.

Layer note (I1): CAPABILITY layer (``knowledge/``), stdlib only, never imports
``agents/``. Pure ``report``-dict in, scored-list out (it consumes the dict shape
emitted by ``mine_emergent_chains`` — no extra IO).
"""

from __future__ import annotations

from typing import Any, Dict, List

# Default weights. flag-correlation is the primary reuse signal; error-rate is
# the primary negative-feedback signal. Tuned so a flag-bearing clean chain scores
# clearly positive and a never-flagged mostly-erroring chain scores clearly
# negative, while clean-but-unproven exploration sits near zero (neutral).
_W_FLAG = 1.0
_W_ERROR = 1.0
# A chain erroring at/above this rate is an ``avoid`` candidate regardless of
# flags — the genuine negative-feedback target.
_AVOID_ERROR_RATE = 0.5


def score_chain(
    chain: Dict[str, Any],
    *,
    w_flag: float = _W_FLAG,
    w_error: float = _W_ERROR,
    avoid_error_rate: float = _AVOID_ERROR_RATE,
) -> Dict[str, Any]:
    """Score one mined chain dict (from :func:`mine_emergent_chains`).

    Returns a copy enriched with ``reuse_reward`` / ``penalty`` / ``score`` /
    ``verdict``. ``score = w_flag*flag_rate - w_error*error_rate`` (range roughly
    ``[-w_error, w_flag]``). Verdict:

    * ``reuse``  — led to a flag (``flag_runs>0``) and not net-negative;
    * ``avoid``  — erroring at/above ``avoid_error_rate`` (negative feedback),
      OR net-negative score;
    * ``neutral`` — explored cleanly but unproven (no flags, low error).
    """
    runs = int(chain.get("runs", 0))
    flag_runs = int(chain.get("flag_runs", 0))
    flag_rate = float(chain.get("flag_rate", (flag_runs / runs) if runs else 0.0))
    error_rate = float(chain.get("error_rate", 0.0))

    reuse_reward = round(w_flag * flag_rate, 4)
    penalty = round(w_error * error_rate, 4)
    score = round(reuse_reward - penalty, 4)

    if error_rate >= avoid_error_rate or score < 0:
        verdict = "avoid"
    elif flag_runs > 0 and score >= 0:
        verdict = "reuse"
    else:
        verdict = "neutral"

    return {
        **chain,
        "reuse_reward": reuse_reward,
        "penalty": penalty,
        "score": score,
        "verdict": verdict,
    }


def score_emergent_chains(
    report: Dict[str, Any],
    *,
    w_flag: float = _W_FLAG,
    w_error: float = _W_ERROR,
    avoid_error_rate: float = _AVOID_ERROR_RATE,
    top_n: int | None = None,
) -> Dict[str, Any]:
    """Score every chain in a mined ``report`` and rank by net score.

    Returns ``{"scored": [...], "reuse": [...], "avoid": [...]}`` where ``scored``
    is the full ranked list (best reuse first), ``reuse`` are the positive
    verdicts, and ``avoid`` are the negative-feedback candidates (what a future
    P8 would down-weight). Empty-in → empty-out, so it is a no-op on a cold log.
    """
    scored = [
        score_chain(
            c, w_flag=w_flag, w_error=w_error, avoid_error_rate=avoid_error_rate
        )
        for c in report.get("chains", [])
    ]
    # Best reuse first: higher score, then more flag-bearing runs, then broader
    # support, then a stable chain-name tiebreak.
    scored.sort(
        key=lambda c: (
            -c["score"],
            -c["flag_runs"],
            -c["runs"],
            "->".join(c["chain"]),
        )
    )
    if top_n is not None:
        scored = scored[: max(top_n, 0)]

    reuse = [c for c in scored if c["verdict"] == "reuse"]
    avoid = [c for c in scored if c["verdict"] == "avoid"]
    return {"scored": scored, "reuse": reuse, "avoid": avoid}


def format_scored_chains(scored_report: Dict[str, Any]) -> str:
    """Render :func:`score_emergent_chains` output as a human-readable report."""
    scored = scored_report.get("scored", [])
    lines: List[str] = [
        "Chain scoring (P7 — reuse reward / negative feedback)",
        "=" * 56,
    ]
    if not scored:
        lines.append("No scorable chains yet (need recurring tool sequences).")
        return "\n".join(lines)

    lines.append("Ranked chains (best reuse first):")
    for c in scored:
        arrow = " → ".join(c["chain"])
        lines.append(
            f"  [{c['verdict']:<7}] {arrow}"
            f"   score={c['score']:+.3f}  "
            f"(reward={c['reuse_reward']:.3f}  penalty={c['penalty']:.3f}  "
            f"flag_runs={c['flag_runs']}  error_rate={c.get('error_rate', 0.0)})"
        )

    avoid = scored_report.get("avoid", [])
    if avoid:
        lines.append("")
        lines.append("Negative-feedback candidates (P8 would down-weight these):")
        for c in avoid:
            lines.append(f"  {' → '.join(c['chain'])}  (score={c['score']:+.3f})")

    return "\n".join(lines)


__all__ = ["score_chain", "score_emergent_chains", "format_scored_chains"]
