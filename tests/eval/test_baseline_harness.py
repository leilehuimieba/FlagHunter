"""Plumbing smoke for the solve-rate baseline harness.

These tests exercise the corpus → runner → judge → report pipeline entirely
offline (``dry_run=True``): no subprocess, no network, no LLM, no tools. They
prove the wiring holds and the tier/expectation/verdict logic is correct — the
*live* solve quality is measured by an operator-driven real run, not here.
"""

from __future__ import annotations

import json
from pathlib import Path

from flaghunter.eval.baseline.corpus import Challenge, Tier, load_corpus
from flaghunter.eval.baseline.judge import Verdict, extract_flag, judge_run
from flaghunter.eval.baseline.report import format_markdown, summarize
from flaghunter.eval.baseline.runner import run_baseline


def _corpus() -> list[Challenge]:
    return [
        Challenge("t1_web", "in-repertoire", Tier.T1, "web", "solve it",
                  r"CTF2\{[^}]+\}", "solved"),
        Challenge("t2_edge", "edge", Tier.T2, "web", "solve it",
                  r"CTF2\{[^}]+\}", "near"),
        Challenge("t3_off", "off-catalog", Tier.T3, "crypto", "solve it",
                  r"CTF2\{[^}]+\}", "fail"),
    ]


def test_seed_corpus_loads_and_has_t0_anchors():
    anchors = load_corpus(tiers=["T0"])
    assert anchors, "seed corpus must ship T0 anchors"
    assert all(c.tier is Tier.T0 for c in anchors)
    assert {"dasctf_easysql"} <= {c.id for c in anchors}


def test_load_corpus_rejects_duplicate_ids(tmp_path: Path):
    dup = tmp_path / "dup.json"
    dup.write_text(json.dumps({"challenges": [
        {"id": "x", "title": "a", "tier": "T1", "type": "web", "task": "t",
         "flag_pattern": "f", "expected_verdict": "solved"},
        {"id": "x", "title": "b", "tier": "T1", "type": "web", "task": "t",
         "flag_pattern": "f", "expected_verdict": "solved"},
    ]}), encoding="utf-8")
    try:
        load_corpus(dup)
        assert False, "duplicate id must raise"
    except ValueError as exc:
        assert "duplicate" in str(exc)


def test_extract_flag_rejects_placeholder_bodies():
    assert extract_flag("goal: flag{...}", r"flag\{[^}]*\}") is None
    assert extract_flag("captured CTF2{r3al}", r"CTF2\{[^}]+\}") == "CTF2{r3al}"


def test_extract_flag_known_flag_requires_exact():
    text = "somewhere CTF2{abc} here"
    assert extract_flag(text, r"CTF2\{[^}]+\}", known_flag="CTF2{abc}") == "CTF2{abc}"
    assert extract_flag(text, r"CTF2\{[^}]+\}", known_flag="CTF2{zzz}") is None


def test_judge_timeout_is_error():
    ch = _corpus()[0]
    res = judge_run(ch, stdout="", timed_out=True)
    assert res.verdict is Verdict.ERROR


def test_judge_near_cue_without_flag():
    ch = _corpus()[1]
    res = judge_run(ch, stdout="candidate flag found but unverified (near-solve)")
    assert res.verdict is Verdict.NEAR
    assert res.matched_expectation  # T2 predicts near


def test_dry_run_pipeline_matches_every_tier_expectation():
    rows = run_baseline(_corpus(), {}, dry_run=True)
    by_id = {r.challenge_id: r for r in rows}
    assert by_id["t1_web"].verdict == "solved"
    assert by_id["t2_edge"].verdict == "near"
    assert by_id["t3_off"].verdict == "fail"
    # Every dry-run outcome is shaped to its tier's prediction.
    assert all(r.matched_expectation for r in rows)
    assert all(r.error.startswith("dry-run") for r in rows)


def test_missing_target_is_skipped_not_passed():
    # No targets + not dry-run → every challenge SKIPPED (never silently solved).
    rows = run_baseline(_corpus(), {}, dry_run=False)
    assert all(r.verdict == "skipped" for r in rows)
    summ = summarize(rows)
    assert summ["total_scored"] == 0 and summ["skipped"] == 3


def test_report_renders_tiers_and_cold_warm_delta():
    cold = run_baseline(_corpus(), {}, dry_run=True, memory_mode="cold")
    warm = run_baseline(_corpus(), {}, dry_run=True, memory_mode="warm")
    md = format_markdown(cold + warm)
    assert "solve@1" in md
    assert "分层" in md
    assert "冷 vs 暖记忆" in md  # both modes present → delta section rendered
