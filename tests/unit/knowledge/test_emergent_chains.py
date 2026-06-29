"""Tests for flaghunter.knowledge.emergent_chains (P6 emergent tool-chain mining).

Pure-function tests over synthetic provenance records (the shape emitted by
``provenance.record_call_sync``). No real executor / no disk — mirrors the P3
provenance store's isolation discipline.
"""

from __future__ import annotations

from flaghunter.knowledge.emergent_chains import (
    format_emergent_chains,
    mine_emergent_chains,
)


def _rec(run_id, seq, tool, *, success=True, found_flag=False):
    return {
        "run_id": run_id,
        "seq": seq,
        "tool": tool,
        "success": success,
        "found_flag": found_flag,
    }


def test_empty_records_yield_zeroed_summary_and_no_chains():
    report = mine_emergent_chains([])
    assert report["summary"] == {
        "total_calls": 0,
        "total_runs": 0,
        "flag_runs": 0,
        "distinct_tools": 0,
    }
    assert report["chains"] == []
    assert report["tools"] == []


def test_single_run_below_min_support_not_surfaced():
    # One run with a clear A→B sequence, but support=1 < min_support=2.
    records = [_rec("r1", 1, "a"), _rec("r1", 2, "b")]
    report = mine_emergent_chains(records)
    assert report["summary"]["total_runs"] == 1
    assert report["chains"] == []  # not "emergent" — appears in only one run
    # but per-tool stats are still aggregated
    assert {t["tool"] for t in report["tools"]} == {"a", "b"}


def test_recurring_bigram_surfaces_with_support_and_occurrences():
    records = [
        _rec("r1", 1, "a"), _rec("r1", 2, "b"),
        _rec("r2", 1, "a"), _rec("r2", 2, "b"),
    ]
    report = mine_emergent_chains(records)
    chains = {tuple(c["chain"]): c for c in report["chains"]}
    assert ("a", "b") in chains
    ab = chains[("a", "b")]
    assert ab["runs"] == 2
    assert ab["occurrences"] == 2
    assert ab["length"] == 2


def test_chains_ordered_by_objects_within_run_by_seq_not_insertion():
    # Records arrive out of seq order; mining must sort by seq within a run.
    records = [
        _rec("r1", 2, "b"), _rec("r1", 1, "a"),
        _rec("r2", 2, "b"), _rec("r2", 1, "a"),
    ]
    report = mine_emergent_chains(records)
    chains = {tuple(c["chain"]) for c in report["chains"]}
    assert ("a", "b") in chains  # a before b by seq
    assert ("b", "a") not in chains


def test_flag_correlation_ranks_flag_bearing_chain_first():
    # Chain (x→y) recurs in 2 flag-bearing runs; (p→q) recurs in 2 flagless runs.
    records = [
        _rec("r1", 1, "x"), _rec("r1", 2, "y", found_flag=True),
        _rec("r2", 1, "x"), _rec("r2", 2, "y", found_flag=True),
        _rec("r3", 1, "p"), _rec("r3", 2, "q"),
        _rec("r4", 1, "p"), _rec("r4", 2, "q"),
    ]
    report = mine_emergent_chains(records)
    assert report["summary"]["flag_runs"] == 2
    top = report["chains"][0]
    assert tuple(top["chain"]) == ("x", "y")
    assert top["flag_runs"] == 2
    assert top["flag_rate"] == 1.0


def test_trigram_mined_when_three_consecutive_calls():
    records = [
        _rec("r1", 1, "a"), _rec("r1", 2, "b"), _rec("r1", 3, "c"),
        _rec("r2", 1, "a"), _rec("r2", 2, "b"), _rec("r2", 3, "c"),
    ]
    report = mine_emergent_chains(records)
    chains = {tuple(c["chain"]) for c in report["chains"]}
    assert ("a", "b", "c") in chains  # trigram
    assert ("a", "b") in chains and ("b", "c") in chains  # bigrams too


def test_blank_run_id_records_excluded_from_chains_but_counted_in_tools():
    records = [
        _rec("", 1, "a"), _rec("", 2, "b"),  # no run grouping → no chains
    ]
    report = mine_emergent_chains(records)
    assert report["summary"]["total_runs"] == 0
    assert report["chains"] == []
    assert report["summary"]["total_calls"] == 2  # still counted overall
    assert {t["tool"] for t in report["tools"]} == {"a", "b"}


def test_per_tool_success_and_flag_counts():
    records = [
        _rec("r1", 1, "scan", success=True),
        _rec("r1", 2, "scan", success=False),
        _rec("r1", 3, "exploit", success=True, found_flag=True),
    ]
    report = mine_emergent_chains(records)
    by_tool = {t["tool"]: t for t in report["tools"]}
    assert by_tool["scan"]["count"] == 2
    assert by_tool["scan"]["success"] == 1
    assert by_tool["scan"]["failed"] == 1
    assert by_tool["exploit"]["flag_count"] == 1


def test_top_n_caps_chain_list():
    # Build many distinct recurring bigrams; cap to top_n=2.
    records = []
    for i in range(5):
        a, b = f"t{i}a", f"t{i}b"
        records += [
            _rec(f"r{i}_1", 1, a), _rec(f"r{i}_1", 2, b),
            _rec(f"r{i}_2", 1, a), _rec(f"r{i}_2", 2, b),
        ]
    report = mine_emergent_chains(records, top_n=2)
    assert len(report["chains"]) == 2


def test_format_emergent_chains_renders_summary_and_chains():
    records = [
        _rec("r1", 1, "a"), _rec("r1", 2, "b", found_flag=True),
        _rec("r2", 1, "a"), _rec("r2", 2, "b", found_flag=True),
    ]
    text = format_emergent_chains(mine_emergent_chains(records))
    assert "Emergent tool-chain report" in text
    assert "a → b" in text
    assert "flag_runs=2" in text


def test_format_emergent_chains_handles_empty_report():
    text = format_emergent_chains(mine_emergent_chains([]))
    assert "No recurring chains yet" in text
