"""Governance for the ATT&CK/WSTG technique taxonomy.

Pins the tagging contract so it cannot silently rot:
  * every catalogued/used ID is well-formed and labelled;
  * every *registered* offensive tool and strategy is either tagged or
    explicitly exempt (a new capability that forgets its tag fails CI);
  * backfill populates the dataclass fields and inline tags win;
  * the coverage report aggregates and surfaces gaps.

This mirrors the I1 (import-linter) and I5 (chain reachability) enforcement
pattern: convert a by-hand audit into a test.
"""

from __future__ import annotations

from flaghunter.agents.attack_coverage import build_coverage_report
from flaghunter.agents.pa_agent.strategy_registry import StrategyRegistry
from flaghunter.knowledge.attack_taxonomy import (
    STRATEGY_EXEMPT,
    STRATEGY_TECHNIQUES,
    TECHNIQUE_CATALOG,
    TOOL_EXEMPT,
    TOOL_TECHNIQUES,
    framework_of,
    is_valid_technique_id,
    tag_strategies,
    tag_tools,
)
from flaghunter.tools.loader import load_all_tools
from flaghunter.tools.registry import Tool, ToolSchema, get_all_tools


def _all_used_ids() -> set[str]:
    used: set[str] = set()
    for ids in (*TOOL_TECHNIQUES.values(), *STRATEGY_TECHNIQUES.values()):
        used.update(ids)
    return used


def test_every_used_id_is_well_formed_and_catalogued():
    used = _all_used_ids()
    malformed = sorted(i for i in used if not is_valid_technique_id(i))
    assert not malformed, f"malformed technique IDs: {malformed}"
    orphan = sorted(i for i in used if i not in TECHNIQUE_CATALOG)
    assert not orphan, f"IDs used but absent from TECHNIQUE_CATALOG: {orphan}"


def test_catalog_framework_matches_id_format():
    mismatched = [
        tid
        for tid, entry in TECHNIQUE_CATALOG.items()
        if entry.get("framework") != framework_of(tid)
    ]
    assert not mismatched, f"catalog framework disagrees with ID format: {mismatched}"


def test_no_tool_is_both_tagged_and_exempt():
    overlap = set(TOOL_TECHNIQUES) & set(TOOL_EXEMPT)
    assert not overlap, f"tools both tagged and exempt: {sorted(overlap)}"


def test_no_strategy_is_both_tagged_and_exempt():
    overlap = set(STRATEGY_TECHNIQUES) & set(STRATEGY_EXEMPT)
    assert not overlap, f"strategies both tagged and exempt: {sorted(overlap)}"


def test_every_registered_tool_is_tagged_or_exempt():
    """A new tool must declare ATT&CK techniques or be explicitly exempt."""
    load_all_tools()
    untagged = sorted(
        tool.name
        for tool in get_all_tools()
        if tool.name not in TOOL_TECHNIQUES and tool.name not in TOOL_EXEMPT
    )
    assert not untagged, (
        f"registered tool(s) {untagged} have no ATT&CK technique tag and are not in "
        f"TOOL_EXEMPT — add them to TOOL_TECHNIQUES or TOOL_EXEMPT in attack_taxonomy."
    )


def test_every_registered_strategy_is_tagged_or_exempt():
    """A new attack-chain strategy must declare WSTG/ATT&CK tags or be exempt."""
    registry = StrategyRegistry.build_default()
    untagged = sorted(
        s.kind
        for s in registry.all()
        if s.kind not in STRATEGY_TECHNIQUES and s.kind not in STRATEGY_EXEMPT
    )
    assert not untagged, (
        f"registered strategy kind(s) {untagged} have no technique tag and are not in "
        f"STRATEGY_EXEMPT — add them to STRATEGY_TECHNIQUES or STRATEGY_EXEMPT."
    )


def test_backfill_populates_fields_and_inline_wins():
    load_all_tools()
    nmap = next(t for t in get_all_tools() if t.name == "nmap")
    assert nmap.technique_ids == TOOL_TECHNIQUES["nmap"]

    strategies = StrategyRegistry.build_default().all()
    deser = next(s for s in strategies if s.kind == "insecure_deserialization")
    assert deser.technique_ids == STRATEGY_TECHNIQUES["insecure_deserialization"]

    # inline declaration is not overwritten by the central map
    inline = Tool(
        name="nmap",
        description="x",
        schema=ToolSchema(),
        execute_fn=lambda *a, **k: None,
        technique_ids=["T9999"],
    )
    tag_tools([inline])
    assert inline.technique_ids == ["T9999"]


def test_tag_strategies_is_non_destructive():
    class _S:
        kind = "auth_form_sqli"
        technique_ids = ["WSTG-CUSTOM-99"]

    s = _S()
    tag_strategies([s])
    assert s.technique_ids == ["WSTG-CUSTOM-99"]


def test_coverage_report_aggregates_and_surfaces_gaps():
    report = build_coverage_report()
    assert report["covered_count"] > 0
    assert report["catalog_count"] == len(TECHNIQUE_CATALOG)

    # known coverage: pickle/php deserialization → WSTG-INPV-11 (Code Injection)
    inpv11 = report["covered"].get("WSTG-INPV-11", [])
    assert "strategy:insecure_deserialization" in inpv11
    assert "strategy:php_unserialize_magic_method" in inpv11

    # XXE (WSTG-INPV-07) is now covered by the xxe_injection strategy.
    inpv07 = report["covered"].get("WSTG-INPV-07", [])
    assert "strategy:xxe_injection" in inpv07

    # Reflected XSS (WSTG-INPV-01) is now covered by the reflected_xss strategy
    # (was the previously-surfaced web gap; stored XSS = WSTG-INPV-02).
    inpv01 = report["covered"].get("WSTG-INPV-01", [])
    assert "strategy:reflected_xss" in inpv01

    # known remaining gap: External Remote Services (T1133) is catalogued but
    # has no covering tool/strategy → still a gap.
    assert "T1133" in report["gaps"]

    # gaps and covered are disjoint
    assert not (set(report["gaps"]) & set(report["covered"]))
