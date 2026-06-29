"""Emergent tool-chain mining (P6 — operating-model闭环波 first item).

This is the **first real consumer** of the P3 provenance store
(``flaghunter/tools/provenance.py``). P3 deliberately captured ``run_id`` + ``seq``
per tool call so a later layer could reconstruct *which tool sequences the agent
actually ran, in what order, and which correlated with finding a flag*. That is
exactly what this module does — see
``docs/dev/FlagHunter_运行方式愿景与上线问题清单_2026-06-28_V1.md`` (P6).

Relationship to ShadowGraph (orthogonal): ``knowledge/graph.py`` mines the
**target topology** (host/service/cred/vuln) from *notes* to derive strategic
hints about *what is out there*. This module mines the **tool-call process**
(which tool n-grams recur and lead to flags) from *provenance*. They never
overlap — one is about the target, the other about how we attacked it.

Honest v1 boundary (mirrors P3's "records + queries only"):
  * this is **descriptive** mining — frequency + flag-correlation, NOT causal
    inference and NOT a recommender;
  * it is **read-only** — nothing here feeds back into chain ordering or the
    orchestrator prompt. Reusing mined chains (复用 + 负反馈) is **P7**; injecting
    them back into live decisions (回灌) is **P8**. P6 only mines + surfaces, so
    the default solve path stays byte-identical.

Design: a pure function over a list of provenance record dicts (the shape
emitted by ``provenance.record_call_sync`` / read by ``get_all_calls``). It does
**not** import ``tools.provenance`` — the caller does the wiring (CLI / MCP read
surface). Layer note (I1): CAPABILITY layer (``knowledge/``), stdlib only, never
imports ``agents/``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# A chain is an ordered tuple of tool names (an n-gram of consecutive calls).
Chain = Tuple[str, ...]

_DEFAULT_MIN_N = 2  # shortest mined sequence (a tool pair)
_DEFAULT_MAX_N = 3  # longest mined sequence (a tool triple)


def _group_by_run(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Bucket records by ``run_id`` (skipping blank ids), preserving membership.

    Ordering within a run is applied by the caller (by ``seq``).
    """
    runs: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        run_id = str(rec.get("run_id") or "").strip()
        if not run_id:
            continue
        runs.setdefault(run_id, []).append(rec)
    return runs


def _consecutive_ngrams(tools: List[str], n: int) -> List[Chain]:
    """Adjacent n-grams over an ordered tool list (the agent's real sequence)."""
    if n <= 0 or len(tools) < n:
        return []
    return [tuple(tools[i : i + n]) for i in range(len(tools) - n + 1)]


def mine_emergent_chains(
    records: List[Dict[str, Any]],
    *,
    min_n: int = _DEFAULT_MIN_N,
    max_n: int = _DEFAULT_MAX_N,
    min_support: int = 2,
    top_n: int = 10,
) -> Dict[str, Any]:
    """Mine recurring tool sequences and their flag-correlation from provenance.

    Args:
        records: provenance record dicts (``get_all_calls()`` output shape).
        min_n / max_n: n-gram length window (consecutive calls).
        min_support: a chain must appear in at least this many distinct runs to
            be surfaced (one-off sequences are not "emergent").
        top_n: cap on the number of chains returned.

    Returns a JSON-serializable dict::

        {
          "summary": {total_calls, total_runs, flag_runs, distinct_tools},
          "chains":  [{chain, length, runs, occurrences, flag_runs, flag_rate}],
          "tools":   [{tool, count, success, failed, flag_count}],
        }

    The chain list is sorted by flag-bearing runs first, then breadth of support
    — the sequences that recur *and* tend to end in a flag float to the top.
    """
    summary = {
        "total_calls": len(records),
        "total_runs": 0,
        "flag_runs": 0,
        "distinct_tools": 0,
    }

    # Per-chain aggregates across runs.
    chain_runs: Dict[Chain, set] = {}          # chain -> set of run_ids it appeared in
    chain_occurrences: Dict[Chain, int] = {}   # chain -> total adjacent occurrences
    chain_flag_runs: Dict[Chain, set] = {}     # chain -> set of flag-bearing run_ids

    # Per-tool aggregates (independent of run grouping; mirrors get_tool_stats).
    tool_count: Dict[str, int] = {}
    tool_success: Dict[str, int] = {}
    tool_flag: Dict[str, int] = {}
    distinct_tools: set = set()

    for rec in records:
        tool = str(rec.get("tool") or "?")
        distinct_tools.add(tool)
        tool_count[tool] = tool_count.get(tool, 0) + 1
        if rec.get("success"):
            tool_success[tool] = tool_success.get(tool, 0) + 1
        if rec.get("found_flag"):
            tool_flag[tool] = tool_flag.get(tool, 0) + 1

    runs = _group_by_run(records)
    summary["total_runs"] = len(runs)

    for run_id, run_records in runs.items():
        ordered = sorted(run_records, key=lambda r: r.get("seq", 0))
        tools = [str(r.get("tool") or "?") for r in ordered]
        run_has_flag = any(r.get("found_flag") for r in ordered)
        if run_has_flag:
            summary["flag_runs"] += 1

        seen_in_run: set = set()  # so a chain counts once toward *support* per run
        for n in range(max(min_n, 1), max_n + 1):
            for gram in _consecutive_ngrams(tools, n):
                chain_occurrences[gram] = chain_occurrences.get(gram, 0) + 1
                if gram not in seen_in_run:
                    seen_in_run.add(gram)
                    chain_runs.setdefault(gram, set()).add(run_id)
                    if run_has_flag:
                        chain_flag_runs.setdefault(gram, set()).add(run_id)

    summary["distinct_tools"] = len(distinct_tools)

    chains: List[Dict[str, Any]] = []
    for gram, run_set in chain_runs.items():
        support = len(run_set)
        if support < min_support:
            continue
        flag_runs = len(chain_flag_runs.get(gram, set()))
        chains.append(
            {
                "chain": list(gram),
                "length": len(gram),
                "runs": support,
                "occurrences": chain_occurrences.get(gram, 0),
                "flag_runs": flag_runs,
                "flag_rate": round(flag_runs / support, 3) if support else 0.0,
            }
        )

    # Flag-bearing sequences first, then breadth of support, then how many times
    # they fired, then longer chains (more specific) before shorter, stable name.
    chains.sort(
        key=lambda c: (
            -c["flag_runs"],
            -c["runs"],
            -c["occurrences"],
            -c["length"],
            "->".join(c["chain"]),
        )
    )
    chains = chains[: max(top_n, 0)]

    tools_report = [
        {
            "tool": t,
            "count": tool_count[t],
            "success": tool_success.get(t, 0),
            "failed": tool_count[t] - tool_success.get(t, 0),
            "flag_count": tool_flag.get(t, 0),
        }
        for t in sorted(tool_count, key=lambda t: (-tool_count[t], t))
    ]

    return {"summary": summary, "chains": chains, "tools": tools_report}


def format_emergent_chains(report: Dict[str, Any]) -> str:
    """Render :func:`mine_emergent_chains` output as a human-readable report."""
    s = report.get("summary", {})
    lines: List[str] = [
        "Emergent tool-chain report (P6 — mined from provenance)",
        "=" * 56,
        f"tool calls: {s.get('total_calls', 0)}   "
        f"runs: {s.get('total_runs', 0)}   "
        f"flag-bearing runs: {s.get('flag_runs', 0)}   "
        f"distinct tools: {s.get('distinct_tools', 0)}",
        "",
    ]

    chains = report.get("chains", [])
    if chains:
        lines.append("Recurring chains (sorted by flag-correlation, then support):")
        for c in chains:
            arrow = " → ".join(c["chain"])
            lines.append(
                f"  {arrow}"
                f"   [runs={c['runs']}  occ={c['occurrences']}  "
                f"flag_runs={c['flag_runs']}  flag_rate={c['flag_rate']}]"
            )
    else:
        lines.append("No recurring chains yet (need ≥2 runs sharing a tool sequence).")

    tools = report.get("tools", [])
    if tools:
        lines.append("")
        lines.append("Per-tool usage:")
        for t in tools:
            flag = f"  flags={t['flag_count']}" if t["flag_count"] else ""
            lines.append(
                f"  {t['tool']:<24} calls={t['count']}  "
                f"ok={t['success']}  fail={t['failed']}{flag}"
            )

    return "\n".join(lines)


__all__ = ["mine_emergent_chains", "format_emergent_chains", "Chain"]
