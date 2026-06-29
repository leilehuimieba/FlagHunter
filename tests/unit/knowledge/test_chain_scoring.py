"""Tests for flaghunter.knowledge.chain_scoring (P7 reuse / negative feedback).

Pure-function tests over mined-report dicts (the shape emitted by
``mine_emergent_chains``). No IO.
"""

from __future__ import annotations

from flaghunter.knowledge.chain_scoring import (
    format_scored_chains,
    score_chain,
    score_emergent_chains,
)
from flaghunter.knowledge.emergent_chains import mine_emergent_chains


def _chain(name, *, runs=2, flag_runs=0, error_rate=0.0, occurrences=2):
    flag_rate = round(flag_runs / runs, 3) if runs else 0.0
    return {
        "chain": list(name),
        "length": len(name),
        "runs": runs,
        "occurrences": occurrences,
        "flag_runs": flag_runs,
        "flag_rate": flag_rate,
        "error_rate": error_rate,
    }


def test_flag_bearing_clean_chain_is_reuse_with_positive_score():
    out = score_chain(_chain(("a", "b"), runs=2, flag_runs=2, error_rate=0.0))
    assert out["verdict"] == "reuse"
    assert out["score"] > 0
    assert out["reuse_reward"] == 1.0
    assert out["penalty"] == 0.0


def test_mostly_erroring_chain_is_avoid_even_without_flags():
    out = score_chain(_chain(("x", "y"), runs=3, flag_runs=0, error_rate=0.8))
    assert out["verdict"] == "avoid"
    assert out["score"] < 0


def test_clean_unproven_chain_is_neutral():
    out = score_chain(_chain(("p", "q"), runs=4, flag_runs=0, error_rate=0.0))
    assert out["verdict"] == "neutral"
    assert out["score"] == 0.0


def test_net_negative_score_classified_avoid():
    # low error but a flag rate that cannot offset → still avoid only if negative;
    # here flags 0 and error 0.5 → score -0.5 → avoid.
    out = score_chain(_chain(("m", "n"), runs=2, flag_runs=0, error_rate=0.5))
    assert out["score"] < 0
    assert out["verdict"] == "avoid"


def test_score_emergent_chains_ranks_reuse_above_avoid():
    report = {
        "chains": [
            _chain(("bad",), runs=3, flag_runs=0, error_rate=0.9),
            _chain(("good",), runs=3, flag_runs=3, error_rate=0.0),
            _chain(("meh",), runs=3, flag_runs=0, error_rate=0.0),
        ]
    }
    out = score_emergent_chains(report)
    order = [c["chain"][0] for c in out["scored"]]
    assert order[0] == "good"          # highest score first
    assert order[-1] == "bad"          # negative score last
    assert [c["chain"][0] for c in out["reuse"]] == ["good"]
    assert [c["chain"][0] for c in out["avoid"]] == ["bad"]


def test_score_emergent_chains_empty_in_empty_out():
    out = score_emergent_chains({"chains": []})
    assert out == {"scored": [], "reuse": [], "avoid": []}


def test_top_n_caps_scored_list():
    report = {
        "chains": [_chain((f"c{i}",), runs=2, flag_runs=i % 2) for i in range(6)]
    }
    out = score_emergent_chains(report, top_n=2)
    assert len(out["scored"]) == 2


def test_end_to_end_mine_then_score():
    # x→y leads to a flag and is clean; p→q never flags and always errors.
    records = [
        {"run_id": "r1", "seq": 1, "tool": "x", "success": True, "found_flag": False},
        {"run_id": "r1", "seq": 2, "tool": "y", "success": True, "found_flag": True},
        {"run_id": "r2", "seq": 1, "tool": "x", "success": True, "found_flag": False},
        {"run_id": "r2", "seq": 2, "tool": "y", "success": True, "found_flag": True},
        {"run_id": "r3", "seq": 1, "tool": "p", "success": False, "found_flag": False},
        {"run_id": "r3", "seq": 2, "tool": "q", "success": False, "found_flag": False},
        {"run_id": "r4", "seq": 1, "tool": "p", "success": False, "found_flag": False},
        {"run_id": "r4", "seq": 2, "tool": "q", "success": False, "found_flag": False},
    ]
    out = score_emergent_chains(mine_emergent_chains(records))
    top = out["scored"][0]
    assert tuple(top["chain"]) == ("x", "y")
    assert top["verdict"] == "reuse"
    assert any(tuple(c["chain"]) == ("p", "q") for c in out["avoid"])


def test_format_scored_chains_renders_verdicts_and_avoid_section():
    report = {
        "chains": [
            _chain(("good",), runs=2, flag_runs=2, error_rate=0.0),
            _chain(("bad",), runs=2, flag_runs=0, error_rate=0.9),
        ]
    }
    text = format_scored_chains(score_emergent_chains(report))
    assert "Chain scoring (P7" in text
    assert "[reuse" in text and "[avoid" in text
    assert "Negative-feedback candidates" in text


def test_format_scored_chains_handles_empty():
    text = format_scored_chains(score_emergent_chains({"chains": []}))
    assert "No scorable chains yet" in text
