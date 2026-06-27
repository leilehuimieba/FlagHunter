"""Technique-coverage matrix over FlagHunter's arsenal (ATT&CK + OWASP WSTG).

Aggregates the technique tags carried by tools and attack-chain strategies into
a coverage matrix and a gap list. This reads *both* the CAPABILITY layer (tool
registry + taxonomy) and the ORCHESTRATION layer (strategy registry), so it
necessarily lives here in ORCHESTRATION — the taxonomy data itself lives one
layer down in :mod:`flaghunter.knowledge.attack_taxonomy` (I1: CAPABILITY must
not import ORCHESTRATION).

A "gap" is a technique present in the catalog that no capability covers — e.g.
``WSTG-INPV-07`` (XML Injection / XXE) is catalogued but unimplemented, so it
surfaces here automatically, turning the by-hand "what's missing" audit into a
queryable report.
"""

from __future__ import annotations

from typing import Any

from ..knowledge.attack_taxonomy import TECHNIQUE_CATALOG, framework_of, label_for


def build_coverage_report(
    tools: list[Any] | None = None,
    strategies: list[Any] | None = None,
) -> dict[str, Any]:
    """Build the technique-coverage matrix.

    Args:
        tools: Tool objects (default: load + read the global registry).
        strategies: StrategyDefinition objects (default: the built-in registry).

    Returns a dict with: ``covered`` (id → list of "tool:x"/"strategy:y"),
    ``frameworks`` (framework → bucket → {id: caps}), ``gaps`` (catalogued but
    uncovered ids), and summary counts.
    """
    if tools is None:
        from ..tools.loader import load_all_tools
        from ..tools.registry import get_all_tools

        load_all_tools()
        tools = get_all_tools()
    if strategies is None:
        from .pa_agent.strategy_registry import StrategyRegistry

        strategies = StrategyRegistry.build_default().all()

    covered: dict[str, list[str]] = {}
    for tool in tools:
        for tid in getattr(tool, "technique_ids", []) or []:
            covered.setdefault(tid, []).append(f"tool:{tool.name}")
    for strategy in strategies:
        for tid in getattr(strategy, "technique_ids", []) or []:
            covered.setdefault(tid, []).append(f"strategy:{strategy.kind}")

    frameworks: dict[str, dict[str, dict[str, list[str]]]] = {}
    for tid, caps in covered.items():
        entry = TECHNIQUE_CATALOG.get(tid, {})
        fw = entry.get("framework") or framework_of(tid)
        bucket = entry.get("tactic") or entry.get("category") or "uncategorized"
        frameworks.setdefault(fw, {}).setdefault(bucket, {})[tid] = sorted(caps)

    gaps = sorted(tid for tid in TECHNIQUE_CATALOG if tid not in covered)

    return {
        "covered_count": len(covered),
        "catalog_count": len(TECHNIQUE_CATALOG),
        "gap_count": len(gaps),
        "frameworks": frameworks,
        "covered": {tid: sorted(caps) for tid, caps in covered.items()},
        "gaps": gaps,
    }


def format_coverage_report(report: dict[str, Any]) -> str:
    """Render a coverage report as a human-readable text matrix."""
    lines: list[str] = []
    lines.append(
        f"Technique coverage: {report['covered_count']}/{report['catalog_count']} "
        f"catalogued techniques covered ({report['gap_count']} gap(s))."
    )
    for framework in sorted(report["frameworks"]):
        buckets = report["frameworks"][framework]
        lines.append("")
        lines.append(f"== {framework} ==")
        for bucket in sorted(buckets):
            lines.append(f"  [{bucket}]")
            for tid in sorted(buckets[bucket]):
                caps = ", ".join(buckets[bucket][tid])
                lines.append(f"    {tid}  {label_for(tid)}")
                lines.append(f"        <- {caps}")
    if report["gaps"]:
        lines.append("")
        lines.append("== GAPS (catalogued, no capability) ==")
        for tid in report["gaps"]:
            lines.append(f"    {tid}  {label_for(tid)}")
    return "\n".join(lines)


__all__ = ["build_coverage_report", "format_coverage_report"]
