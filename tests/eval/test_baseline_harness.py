"""Plumbing smoke for the solve-rate baseline harness.

These tests exercise the corpus → runner → judge → report pipeline entirely
offline (``dry_run=True``): no subprocess, no network, no LLM, no tools. They
prove the wiring holds and the tier/expectation/verdict logic is correct — the
*live* solve quality is measured by an operator-driven real run, not here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from flaghunter.eval.baseline.corpus import Challenge, Tier, load_corpus
from flaghunter.eval.baseline.failure_taxonomy import build_backlog, outcome_breakdown
from flaghunter.eval.baseline.judge import (
    Verdict,
    _parse_steps,
    _parse_tools,
    extract_flag,
    judge_run,
)
from flaghunter.eval.baseline.report import format_markdown, summarize
from flaghunter.eval.baseline.runner import ScorecardRow, run_baseline, run_one

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


def test_judge_rejects_unproven_flag_in_stdout():
    """A flag-shaped string with no proof-backed terminal outcome is a candidate,
    never SOLVED — this is the false-success channel D-02 closes (§6.18). The
    candidate is still surfaced so an operator can see the near-miss."""
    ch = Challenge("t0_sql", "anchor", Tier.T0, "web", "solve it",
                   r"CTF2\{[^}]+\}", "solved")
    res = judge_run(ch, stdout="somewhere printed CTF2{unverified}\n")
    assert res.verdict is Verdict.NEAR
    assert res.verdict is not Verdict.SOLVED
    assert res.flag_found == "CTF2{unverified}"


def test_judge_solved_requires_proof_backed_terminal():
    """The same flag-shaped output *with* the proof-gated terminal outcome is a
    real SOLVED — the judge consumes proof, not a raw stdout regex."""
    ch = Challenge("t0_sql", "anchor", Tier.T0, "web", "solve it",
                   r"CTF2\{[^}]+\}", "solved")
    stdout = ("somewhere printed CTF2{proven}\n"
              "[CTF dispatcher] done: stopped=goal_met steps=3 solved=True\n")
    res = judge_run(ch, stdout=stdout)
    assert res.verdict is Verdict.SOLVED
    assert res.flag_found == "CTF2{proven}"


def test_judge_false_terminal_outcome_is_not_solved():
    """A ``solved=False`` terminal outcome demotes even a flag-shaped string to a
    candidate — the run itself declared no verified solve."""
    ch = Challenge("t0_sql", "anchor", Tier.T0, "web", "solve it",
                   r"CTF2\{[^}]+\}", "solved")
    stdout = ("candidate CTF2{maybe}\n"
              "[CTF dispatcher] done: stopped=budget_exhausted steps=12 solved=False\n")
    res = judge_run(ch, stdout=stdout)
    assert res.verdict is not Verdict.SOLVED


def test_run_one_isolates_cwd_write_surfaces(tmp_path: Path, monkeypatch):
    """A run's CWD-relative writes (loot/notes.json et al.) land in a private
    per-run workdir, never the harness cwd — so a cold sweep can't leak state
    from one challenge into the next (D-03, §6.18 item 4)."""
    # A stand-in for ``flaghunter`` that does what the real tool does: write a
    # CWD-relative loot file, then print a proof-backed terminal outcome.
    script = tmp_path / "fake_fh.py"
    script.write_text(
        "import pathlib\n"
        "d = pathlib.Path('loot'); d.mkdir(exist_ok=True)\n"
        "(d / 'notes.json').write_text('leak', encoding='utf-8')\n"
        "print('[CTF dispatcher] done: stopped=goal_met steps=1 solved=True')\n",
        encoding="utf-8",
    )
    ch = Challenge("t0", "anchor", Tier.T0, "web", "solve it",
                   r"CTF2\{[^}]+\}", "solved")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.chdir(scratch)  # if cwd leaked, the fake would write here

    row = run_one(ch, "http://target", base_cmd=[sys.executable, str(script)],
                  runs_dir=tmp_path / "runs")

    assert row.verdict == "solved"  # proof-backed terminal line honored
    # The fake's loot write went to its private workdir, not the harness cwd.
    assert not (scratch / "loot" / "notes.json").exists()


def test_warm_runs_share_strategy_memory_but_not_cwd(tmp_path: Path, monkeypatch):
    """warm mode shares ONE strategy-memory file across challenges (the intended
    warm signal, kept working across per-run cwds by pinning an absolute env
    path) while each run's CWD writes stay private (D-03)."""
    script = tmp_path / "fake_fh.py"
    script.write_text(
        "import os, pathlib\n"
        "p = pathlib.Path(os.environ['FLAGHUNTER_STRATEGY_MEMORY_PATH'])\n"
        "p.parent.mkdir(parents=True, exist_ok=True)\n"
        "prev = p.read_text(encoding='utf-8') if p.exists() else ''\n"
        "p.write_text(prev + 'x', encoding='utf-8')\n"
        "pathlib.Path('leak.txt').write_text('y', encoding='utf-8')\n"
        "print('[CTF dispatcher] done: stopped=goal_met steps=1 solved=True')\n",
        encoding="utf-8",
    )
    chs = [Challenge(f"c{i}", "a", Tier.T0, "web", "s", r"CTF2\{[^}]+\}", "solved")
           for i in range(2)]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.chdir(scratch)
    runs_dir = tmp_path / "runs"

    run_baseline(chs, {"c0": "http://t", "c1": "http://t"}, memory_mode="warm",
                 base_cmd=[sys.executable, str(script)], runs_dir=runs_dir)

    # Both runs appended to the SAME shared warm store → two chars.
    assert (runs_dir / "warm_strategy_memory.json").read_text(encoding="utf-8") == "xx"
    # Neither run's private CWD write leaked into the harness cwd.
    assert not (scratch / "leak.txt").exists()


def _row(**kw) -> ScorecardRow:
    base = dict(
        challenge_id="c", tier="T1", type="web", verdict="fail",
        expected_verdict="solved", matched_expectation=False, memory_mode="cold",
    )
    base.update(kw)
    return ScorecardRow(**base)


def test_outcome_breakdown_partitions_five_classes():
    """The report must always give pass / honest-stop / false-success / infra /
    timeout (§6.18 item 3). false-success is the *caught* monitor; uncaught stays 0
    because the judge is proof-gated (D-02)."""
    rows = [
        _row(verdict="solved", stop_reason="goal_met", matched_expectation=True),
        _row(verdict="fail", stop_reason="brain_stop"),                       # honest stop
        _row(verdict="near", flag_found="CTF2{x}", stop_reason="budget_exhausted"),  # caught
        _row(verdict="error", timed_out=False),                              # infra
        _row(verdict="error", timed_out=True),                               # timeout
        _row(verdict="skipped"),                                             # excluded
    ]
    ob = outcome_breakdown(rows)
    assert ob["pass"] == 1
    assert ob["honest_stop"] == 1
    assert ob["false_success"] == 1
    assert ob["infra_failure"] == 1
    assert ob["timeout"] == 1
    assert ob["false_success_uncaught"] == 0


def test_backlog_ranks_regression_p0_and_excludes_confirmed_ceiling():
    """A T0/T1 miss that defied its prediction is a P0 regression; a T2/T3 fail that
    MATCHED its prediction is a confirmed ceiling — recorded, never backlogged
    (§6.18 item 8: data-driven backlog, no hand-picking)."""
    rows = [
        _row(challenge_id="t1_reach", tier="T1", verdict="fail",
             matched_expectation=False, diseases=["reachability"]),
        _row(challenge_id="t3_ceiling", tier="T3", verdict="fail",
             expected_verdict="fail", matched_expectation=True),
        _row(challenge_id="t2_budget", tier="T2", verdict="fail",
             matched_expectation=False, stop_reason="budget_exhausted"),
    ]
    backlog, ceilings = build_backlog(rows)
    ids = [b.challenge_id for b in backlog]
    assert "t3_ceiling" not in ids
    assert [r.challenge_id for r in ceilings] == ["t3_ceiling"]
    # P0 regression sorts first; its diagnosis names the reachability fix.
    assert backlog[0].challenge_id == "t1_reach"
    assert backlog[0].priority == "P0"
    assert backlog[0].failure_class == "reachability_gap"
    budget = next(b for b in backlog if b.challenge_id == "t2_budget")
    assert budget.priority == "P1" and budget.failure_class == "budget_waste"


def test_backlog_infra_and_timeout_are_p0():
    """Infra failure and timeout block measurement itself → always P0, split apart
    (not conflated under a single ERROR bucket)."""
    backlog, _ = build_backlog([
        _row(challenge_id="e1", verdict="error", timed_out=False),
        _row(challenge_id="e2", verdict="error", timed_out=True),
    ])
    classes = {b.challenge_id: (b.priority, b.failure_class) for b in backlog}
    assert classes["e1"] == ("P0", "infra_failure")
    assert classes["e2"] == ("P0", "timeout")


def test_report_renders_outcome_breakdown_and_backlog():
    rows = run_baseline(_corpus(), {}, dry_run=True)
    md = format_markdown(rows)
    assert "outcome breakdown" in md
    assert "优化 backlog" in md
    # dry-run is proof-gated end to end → the uncaught alarm stays clear.
    assert "false-success(uncaught) 0" in md


def test_report_renders_tiers_and_cold_warm_delta():
    cold = run_baseline(_corpus(), {}, dry_run=True, memory_mode="cold")
    warm = run_baseline(_corpus(), {}, dry_run=True, memory_mode="warm")
    md = format_markdown(cold + warm)
    assert "solve@1" in md
    assert "分层" in md
    assert "冷 vs 暖记忆" in md  # both modes present → delta section rendered
