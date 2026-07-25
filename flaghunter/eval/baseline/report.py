"""Aggregate scorecard rows into a reviewable markdown scorecard.

The report's job is to make the product north star legible at a glance: not
"1301 passed" (the code didn't break) but "solved N/M, and here's where and why
the misses happened". Tier-aware, because a T3 (out-of-repertoire) FAIL is a
*confirmed prediction*, not a regression — the report scores runs against what
each tier predicted, and surfaces cold-vs-warm memory deltas.
"""

from __future__ import annotations

from collections import Counter
from statistics import mean

from .runner import ScorecardRow

_SOLVED = "solved"
_NEAR = "near"
_SKIPPED = "skipped"


def _rate(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def summarize(rows: list[ScorecardRow]) -> dict:
    """Compute aggregate metrics. Skipped rows are excluded from rate denominators."""
    scored = [r for r in rows if r.verdict != _SKIPPED]
    total = len(scored)
    by_verdict = Counter(r.verdict for r in scored)
    solved_rows = [r for r in scored if r.verdict == _SOLVED]

    steps = [r.steps for r in solved_rows if r.steps is not None]
    tokens = [r.tokens for r in solved_rows if r.tokens is not None]

    tiers: dict[str, dict] = {}
    for tier in ("T0", "T1", "T2", "T3"):
        tr = [r for r in scored if r.tier == tier]
        if not tr:
            continue
        tiers[tier] = {
            "total": len(tr),
            "solved": sum(1 for r in tr if r.verdict == _SOLVED),
            "near": sum(1 for r in tr if r.verdict == _NEAR),
            "matched_expectation": sum(1 for r in tr if r.matched_expectation),
            "solve_rate": _rate(sum(1 for r in tr if r.verdict == _SOLVED), len(tr)),
        }

    disease_counts = Counter(d for r in scored for d in r.diseases)

    return {
        "total_scored": total,
        "skipped": sum(1 for r in rows if r.verdict == _SKIPPED),
        "solved": by_verdict.get(_SOLVED, 0),
        "near": by_verdict.get(_NEAR, 0),
        "fail": by_verdict.get("fail", 0),
        "error": by_verdict.get("error", 0),
        "solve_at_1": _rate(by_verdict.get(_SOLVED, 0), total),
        "near_rate": _rate(by_verdict.get(_NEAR, 0), total),
        "expectation_match_rate": _rate(sum(1 for r in scored if r.matched_expectation), total),
        "mean_steps_to_solve": round(mean(steps), 1) if steps else None,
        "mean_tokens_per_solve": round(mean(tokens)) if tokens else None,
        "tiers": tiers,
        "diseases": dict(disease_counts),
    }


def _cold_warm_delta(rows: list[ScorecardRow]) -> dict | None:
    """If the sweep ran both memory modes, compare solve@1. Answers the open
    question the memory notes flagged: is warm memory monotonically better?"""
    modes = {r.memory_mode for r in rows if r.verdict != _SKIPPED}
    if not {"cold", "warm"} <= modes:
        return None
    out = {}
    for mode in ("cold", "warm"):
        scored = [r for r in rows if r.memory_mode == mode and r.verdict != _SKIPPED]
        out[mode] = _rate(sum(1 for r in scored if r.verdict == _SOLVED), len(scored))
    out["delta"] = round(out["warm"] - out["cold"], 1)
    return out


def format_markdown(rows: list[ScorecardRow], *, title: str = "FlagHunter Solve-Rate Baseline") -> str:
    s = summarize(rows)
    lines = [f"# {title}", ""]
    lines.append(
        f"**solve@1: {s['solve_at_1']}%** "
        f"({s['solved']}/{s['total_scored']}) · near {s['near_rate']}% · "
        f"fail {s['fail']} · error {s['error']} · skipped {s['skipped']}"
    )
    lines.append("")
    if s["mean_steps_to_solve"] is not None:
        lines.append(
            f"平均 steps-to-solve: {s['mean_steps_to_solve']} · "
            f"平均 tokens/solve: {s['mean_tokens_per_solve']} · "
            f"expectation-match: {s['expectation_match_rate']}%"
        )
        lines.append("")

    # Per-tier — a T3 FAIL that matches expectation is a confirmed ceiling, not a bug.
    lines.append("## 分层 (tier breakdown)")
    lines.append("")
    lines.append("| tier | solved | near | total | solve% | 符合预期 |")
    lines.append("|------|--------|------|-------|--------|----------|")
    for tier, t in s["tiers"].items():
        lines.append(
            f"| {tier} | {t['solved']} | {t['near']} | {t['total']} | "
            f"{t['solve_rate']}% | {t['matched_expectation']}/{t['total']} |"
        )
    lines.append("")

    delta = _cold_warm_delta(rows)
    if delta:
        sign = "+" if delta["delta"] >= 0 else ""
        lines.append("## 冷 vs 暖记忆")
        lines.append("")
        lines.append(
            f"cold solve@1 {delta['cold']}% → warm {delta['warm']}% "
            f"(**delta {sign}{delta['delta']}pp**) — 记忆收益是否单调的量化答案。"
        )
        lines.append("")

    if s["diseases"]:
        lines.append("## 三病命中 (disease incidence)")
        lines.append("")
        for name, count in sorted(s["diseases"].items(), key=lambda kv: -kv[1]):
            lines.append(f"- {name}: {count}")
        lines.append("")

    lines.append("## 逐题 (per challenge)")
    lines.append("")
    lines.append("| id | tier | type | verdict | flag | steps | tokens | wall(s) | 病 | mode |")
    lines.append("|----|------|------|---------|------|-------|--------|---------|----|------|")
    for r in rows:
        flag = "✓" if r.flag_found else ("—" if r.verdict != _SKIPPED else "skip")
        diseases = ",".join(r.diseases) or "-"
        lines.append(
            f"| {r.challenge_id} | {r.tier} | {r.type} | {r.verdict} | {flag} | "
            f"{r.steps if r.steps is not None else '-'} | "
            f"{r.tokens if r.tokens is not None else '-'} | "
            f"{r.wall_time_s if r.wall_time_s is not None else '-'} | {diseases} | {r.memory_mode} |"
        )
    lines.append("")
    return "\n".join(lines)
