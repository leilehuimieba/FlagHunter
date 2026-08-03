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
from flaghunter.eval.baseline.judge import (
    Verdict,
    _parse_steps,
    _parse_tools,
    extract_flag,
    judge_run,
)
from flaghunter.eval.baseline.report import format_markdown, summarize
from flaghunter.eval.baseline.runner import run_baseline

# A realistic slice of a fast live-solve stdout (easysql shape): the blackboard
# loop solves in 2 steps, so the Finished panel shows "Loops: 0/12" while the
# authoritative step count lives in the dispatcher "done: … steps=2" line.
_FAST_SOLVE_STDOUT = """\
[00:12] [CTF dispatcher]  step 1: call_tool lfi -> progress=true reason=commands exhausted
[00:24] [CTF dispatcher]  step 2: call_tool web -> flag=CTF2{b4e35399}
[00:24] [CTF dispatcher]  done: stopped=goal_met steps=2 solved=True
the tool will keep running for a while as it finalizes
| Loops: 0/12 |
| Tools: 67 |
"""


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
    dup.write_text(json.dumps({"schema_version": "1", "challenges": [
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


def test_load_corpus_requires_schema_version(tmp_path: Path):
    """A dict-form manifest without schema_version is rejected, not silently
    loaded with defaulted fields (D-01 versioned corpus, §13.5)."""
    bad = tmp_path / "no_version.json"
    bad.write_text(json.dumps({"challenges": [
        {"id": "x", "title": "a", "tier": "T1", "type": "web", "task": "t",
         "flag_pattern": "f", "expected_verdict": "solved"},
    ]}), encoding="utf-8")
    try:
        load_corpus(bad)
        assert False, "missing schema_version must raise"
    except ValueError as exc:
        assert "schema_version" in str(exc)


def test_load_corpus_rejects_unsupported_schema_version(tmp_path: Path):
    """An unknown schema_version fails loudly so an operator on an old build
    can't score a newer manifest against stale reader assumptions."""
    bad = tmp_path / "future_version.json"
    bad.write_text(json.dumps({"schema_version": "999", "challenges": [
        {"id": "x", "title": "a", "tier": "T1", "type": "web", "task": "t",
         "flag_pattern": "f", "expected_verdict": "solved"},
    ]}), encoding="utf-8")
    try:
        load_corpus(bad)
        assert False, "unsupported schema_version must raise"
    except ValueError as exc:
        assert "schema_version" in str(exc)


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


def test_parse_steps_uses_terminal_line_not_loop_panel():
    # Fast live solve: "Loops: 0/12" panel must NOT win over "steps=2".
    steps, max_loops = _parse_steps(_FAST_SOLVE_STDOUT)
    assert steps == 2, "step count must come from the dispatcher done: line"
    assert max_loops == 12


def test_parse_steps_falls_back_to_trace_then_blanks():
    # No terminal line but a step trace → highest step wins.
    steps, _ = _parse_steps("step 1: call_tool web\nstep 7: call_tool sqli\n")
    assert steps == 7
    # Nothing parseable → honest None, never a scraped 0.
    assert _parse_steps("no step markers here, just 0/12 noise")[0] is None


def test_parse_tools_reads_call_tool_trace_not_prose():
    tools = _parse_tools(_FAST_SOLVE_STDOUT)
    assert tools == ["lfi", "web"], "tools must come from call_tool lines, not prose"
    # Junk prose words like 'will' / 'for' must not leak in.
    assert "will" not in tools and "for" not in tools


def test_judge_run_reports_real_steps_and_tools_on_fast_solve():
    ch = Challenge("t0_sql", "anchor", Tier.T0, "web", "solve it",
                   r"CTF2\{[^}]+\}", "solved")
    res = judge_run(ch, stdout=_FAST_SOLVE_STDOUT)
    assert res.verdict is Verdict.SOLVED
    assert res.steps == 2
    assert res.tools_used == ["lfi", "web"]


def test_report_renders_tiers_and_cold_warm_delta():
    cold = run_baseline(_corpus(), {}, dry_run=True, memory_mode="cold")
    warm = run_baseline(_corpus(), {}, dry_run=True, memory_mode="warm")
    md = format_markdown(cold + warm)
    assert "solve@1" in md
    assert "分层" in md
    assert "冷 vs 暖记忆" in md  # both modes present → delta section rendered
