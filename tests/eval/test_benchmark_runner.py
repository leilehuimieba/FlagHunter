from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval.benchmark_result import BenchmarkReport, ChallengeResult
from tests.eval import benchmark_runner


def test_benchmark_report_can_serialize_and_write_json(tmp_path: Path):
    report = BenchmarkReport(
        run_id="benchmark_test",
        timestamp="2026-05-24T00:00:00+00:00",
        git_sha="deadbeef",
        results=[
            ChallengeResult(
                challenge_id="easy_tornado",
                solved=True,
                expected_solved=True,
                wrong_flag_count=0,
                flag_submit_attempts=0,
                chain_iterations=1,
                stop_reason="flag verified",
                stop_reason_class="flag_verified",
                has_source_only_stop=False,
                hypothesis_exhausted_count=0,
                hypothesis_total_count=3,
                wall_time_seconds=0.1234,
                verified_flag_count=1,
                flag="flag{ok}",
                chain_used=["web"],
            )
        ],
        solve_rate=1.0,
        wrong_flag_rate=0.0,
        premature_stop_rate=0.0,
        avg_chains_to_solve=1.0,
        hypothesis_exhaustion_rate=0.0,
        total_challenges=1,
        solved_challenges=1,
        total_flag_submit_attempts=0,
        wrong_flag_submissions=0,
    )

    output_path = report.write_json(tmp_path / "benchmark.json")
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["run_id"] == "benchmark_test"
    assert payload["results"][0]["challenge_id"] == "easy_tornado"
    assert payload["results"][0]["flag"] == "flag{ok}"


@pytest.mark.asyncio
async def test_run_benchmark_subset_uses_catalog_and_writes_report(monkeypatch, tmp_path: Path):
    async def _fake_runner(_verification_callback=None):
        from pentestagent.agents.pa_agent.ctf_dispatcher import SolveResult
        from pentestagent.agents.pa_agent.ctf_state import CTFState

        state = CTFState(target="http://ctf.local", goal="拿到flag")
        state.add_flag(
            "flag{synthetic}",
            level="verified",
            evidence_source="http-response",
            rationale="synthetic benchmark",
            confidence=1.0,
        )
        state.stop_reason = "synthetic success"
        state.stop_report = {"reason": "flag_verified"}
        return (
            SolveResult(
                success=True,
                flag="flag{synthetic}",
                chain_used=["web"],
                notes=["synthetic"],
                reason="synthetic success",
            ),
            state,
        )

    fake_catalog = {
        "synthetic": benchmark_runner._ChallengeSpec(
            challenge_id="synthetic",
            expected_solved=True,
            source="tests/synthetic.py::fixture",
            runner=_fake_runner,
        )
    }
    monkeypatch.setattr(benchmark_runner, "_CHALLENGE_CATALOG", fake_catalog)
    monkeypatch.setattr(benchmark_runner, "_DEFAULT_CHALLENGE_IDS", ["synthetic"])

    report_path = tmp_path / "baseline.json"
    report = await benchmark_runner.run_benchmark(report_path=str(report_path))

    assert report.total_challenges == 1
    assert report.solved_challenges == 1
    assert report.solve_rate == 1.0
    assert report_path.exists()


# ---------------------------------------------------------------------------
# Phase 7: failure taxonomy tests (P7-EVAL-01 to P7-EVAL-04)
# ---------------------------------------------------------------------------

def _make_result(
    *,
    challenge_id: str = "test",
    solved: bool,
    wrong_flag_count: int = 0,
    stop_reason_class: str = "",
) -> ChallengeResult:
    return ChallengeResult(
        challenge_id=challenge_id,
        solved=solved,
        expected_solved=True,
        wrong_flag_count=wrong_flag_count,
        flag_submit_attempts=wrong_flag_count + (1 if solved else 0),
        chain_iterations=1,
        stop_reason="",
        stop_reason_class=stop_reason_class,
        has_source_only_stop=False,
        hypothesis_exhausted_count=0,
        hypothesis_total_count=1,
        wall_time_seconds=0.1,
        verified_flag_count=1 if solved else 0,
    )


def test_p7_eval_01_solved_challenge_has_no_taxonomy(tmp_path: Path):
    """P7-EVAL-01: solved challenge → failure_taxonomy == None"""
    result = _make_result(solved=True)
    assert result.failure_taxonomy is None


def test_p7_eval_02_wrong_flag_unsolved_has_wrong_answer_taxonomy(tmp_path: Path):
    """P7-EVAL-02: wrong_flag_count > 0 且未 solved → failure_taxonomy == "wrong_answer" """
    from tests.eval.benchmark_runner import _build_challenge_result
    from pentestagent.agents.pa_agent.ctf_dispatcher import SolveResult
    from pentestagent.agents.pa_agent.ctf_state import CTFState

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_reason = "no progress"
    result = SolveResult(success=False, reason="no progress", chain_used=["web"])

    # Manually force wrong_flag count by patching meta_reasonings
    state.meta_reasonings.append({
        "type": "flag_submit_attempt",
        "correct": False,
        "flag": "flag{wrong}",
    })

    cr = _build_challenge_result(
        challenge_id="test_wrong",
        expected_solved=True,
        source="test",
        result=result,
        state=state,
        wall_time_seconds=0.5,
    )
    assert cr.failure_taxonomy == "wrong_answer"


def test_p7_eval_03_no_progress_stop_has_give_up_taxonomy(tmp_path: Path):
    """P7-EVAL-03: no_progress_stop 且未 solved → failure_taxonomy == "give_up" """
    from tests.eval.benchmark_runner import _build_challenge_result
    from pentestagent.agents.pa_agent.ctf_dispatcher import SolveResult
    from pentestagent.agents.pa_agent.ctf_state import CTFState

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_reason = "no progress"
    state.stop_report = {"reason": "all_hypotheses_exhausted"}
    result = SolveResult(success=False, reason="all_hypotheses_exhausted", chain_used=["web"])

    cr = _build_challenge_result(
        challenge_id="test_noprogress",
        expected_solved=True,
        source="test",
        result=result,
        state=state,
        wall_time_seconds=0.5,
    )
    assert cr.failure_taxonomy == "give_up"


@pytest.mark.asyncio
async def test_p7_eval_04_failure_distribution_in_report(monkeypatch, tmp_path: Path):
    """P7-EVAL-04: BenchmarkReport.failure_distribution 包含各标签计数"""
    async def _fake_unsolved(_verification_callback=None):
        from pentestagent.agents.pa_agent.ctf_dispatcher import SolveResult
        from pentestagent.agents.pa_agent.ctf_state import CTFState

        state = CTFState(target="http://ctf.local", goal="拿到flag")
        state.stop_reason = "no progress"
        state.stop_report = {"reason": "all_hypotheses_exhausted"}
        return (
            SolveResult(success=False, reason="all_hypotheses_exhausted", chain_used=["web"]),
            state,
        )

    async def _fake_solved(_verification_callback=None):
        from pentestagent.agents.pa_agent.ctf_dispatcher import SolveResult
        from pentestagent.agents.pa_agent.ctf_state import CTFState

        state = CTFState(target="http://ctf.local", goal="拿到flag")
        state.add_flag("flag{ok}", level="verified", evidence_source="http-response",
                       rationale="test", confidence=1.0)
        state.stop_reason = "flag verified"
        state.stop_report = {"reason": "flag_verified"}
        return (
            SolveResult(success=True, flag="flag{ok}", chain_used=["web"], reason="ok"),
            state,
        )

    fake_catalog = {
        "unsolved": benchmark_runner._ChallengeSpec(
            challenge_id="unsolved",
            expected_solved=False,
            source="test",
            runner=_fake_unsolved,
        ),
        "solved": benchmark_runner._ChallengeSpec(
            challenge_id="solved",
            expected_solved=True,
            source="test",
            runner=_fake_solved,
        ),
    }
    monkeypatch.setattr(benchmark_runner, "_CHALLENGE_CATALOG", fake_catalog)
    monkeypatch.setattr(benchmark_runner, "_DEFAULT_CHALLENGE_IDS", ["unsolved", "solved"])

    report_path = tmp_path / "p7_taxonomy.json"
    report = await benchmark_runner.run_benchmark(report_path=str(report_path))

    assert report.failure_distribution.get("give_up", 0) >= 1
    assert "give_up" in report.failure_distribution
    # solved challenge should not contribute to failure_distribution
    assert report.failure_distribution.get("give_up") == 1
