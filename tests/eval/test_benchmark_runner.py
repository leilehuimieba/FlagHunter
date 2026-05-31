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


def test_build_harness_summary_for_run_reads_session_artifacts_and_checkpoint(tmp_path: Path):
    from pentestagent.agents.pa_agent.ctf_state import CTFState
    from pentestagent.harness.artifact_registry import ArtifactRegistry
    from pentestagent.harness.checkpoint_store import CheckpointStore
    from pentestagent.harness.session_ledger import SessionLedger

    run_id = "benchmark-run-1"
    root = tmp_path
    SessionLedger(root / "loot" / "session_ledgers").append_event(
        run_id,
        "tool_called",
        {"tool_name": "proxy_action", "action": "request", "target": "http://ctf.local/login"},
    )
    ArtifactRegistry(root / "loot" / "artifact_registry").register_artifact(
        run_id=run_id,
        kind="artifact",
        title="response_dump",
        location="http://ctf.local/debug.txt",
        producer="ssti_exploit",
        metadata={"category": "exploit-output"},
    )
    ArtifactRegistry(root / "loot" / "artifact_registry").register_artifact(
        run_id=run_id,
        kind="flag",
        title="ctf_flag",
        location="notes://flags/verified",
        producer="flag_verifier",
        metadata={"level": "verified"},
    )
    ArtifactRegistry(root / "loot" / "artifact_registry").register_artifact(
        run_id=run_id,
        kind="flag",
        title="ctf_flag",
        location="notes://flags/verified/latest",
        producer="flag_verifier",
        metadata={"level": "verified"},
    )
    ArtifactRegistry(root / "loot" / "artifact_registry").register_artifact(
        run_id=run_id,
        kind="artifact",
        title="same_location_alias",
        location="http://ctf.local/debug.txt",
        producer="alias_writer",
        metadata={"category": "alias"},
    )
    ArtifactRegistry(root / "loot" / "artifact_registry").register_artifact(
        run_id=run_id,
        kind="artifact",
        title="local_dump",
        path=str(root / "loot" / "response.txt"),
        producer="file_writer",
        metadata={"category": "dump"},
    )
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_reason = "verifier_reject"
    CheckpointStore(root / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={"success": False},
    )

    summary = benchmark_runner._build_harness_summary_for_run(run_id=run_id, workspace_root=root)

    assert summary["has_session_ledger"] is True
    assert summary["run_id"] == run_id
    assert summary["ledger_path"].endswith("benchmark-run-1.jsonl")
    assert "tool_called" in summary["event_types"]
    assert summary["tool_event_count"] == 1
    assert summary["artifact_count"] == 5
    assert summary["artifact_titles"] == [
        "response_dump",
        "ctf_flag",
        "same_location_alias",
        "local_dump",
    ]
    assert summary["artifact_kinds"] == ["artifact", "flag"]
    assert summary["artifact_locations_preview"] == [
        "http://ctf.local/debug.txt",
        "notes://flags/verified",
        str(root / "loot" / "response.txt"),
    ]
    assert summary["has_checkpoint"] is True
    assert summary["latest_checkpoint_label"] == "task_finished"
    assert summary["latest_checkpoint_stop_reason"] == "verifier_reject"


@pytest.mark.asyncio
async def test_run_benchmark_attaches_harness_summary_to_result_metadata(monkeypatch, tmp_path: Path):
    async def _fake_runner(_verification_callback=None):
        from pentestagent.agents.pa_agent.ctf_dispatcher import SolveResult
        from pentestagent.agents.pa_agent.ctf_state import CTFState

        state = CTFState(target="http://ctf.local", goal="拿到flag")
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
            {
                "has_session_ledger": True,
                "run_id": "synthetic-run-1",
                "ledger_path": "loot/session_ledgers/synthetic-run-1.jsonl",
                "event_types": ["tool_called", "task_finished"],
                "tool_event_count": 1,
                "artifact_count": 1,
                "artifact_titles": ["response_dump"],
                "artifact_kinds": ["artifact"],
                "artifact_locations_preview": ["http://ctf.local/debug.txt"],
                "has_checkpoint": True,
                "latest_checkpoint_label": "task_finished",
                "latest_checkpoint_stop_reason": "flag_verified",
            },
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

    report = await benchmark_runner.run_benchmark(report_path=str(tmp_path / "benchmark.json"))

    assert report.results[0].metadata["harness"]["has_session_ledger"] is True
    assert report.results[0].metadata["harness"]["run_id"] == "synthetic-run-1"
    assert report.results[0].metadata["harness"]["artifact_count"] == 1
    assert report.results[0].metadata["harness"]["artifact_titles"] == ["response_dump"]
    assert report.results[0].metadata["harness"]["artifact_kinds"] == ["artifact"]
    assert report.results[0].metadata["harness"]["artifact_locations_preview"] == [
        "http://ctf.local/debug.txt"
    ]
    assert report.results[0].metadata["harness"]["tool_event_count"] == 1
    assert report.results[0].metadata["harness"]["has_checkpoint"] is True
    assert report.results[0].metadata["harness"]["latest_checkpoint_stop_reason"] == "flag_verified"


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


def test_aggregate_report_includes_harness_coverage_metrics() -> None:
    results = [
        ChallengeResult(
            challenge_id="a",
            solved=True,
            expected_solved=True,
            wrong_flag_count=0,
            flag_submit_attempts=0,
            chain_iterations=1,
            stop_reason="ok",
            stop_reason_class="flag_verified",
            has_source_only_stop=False,
            hypothesis_exhausted_count=0,
            hypothesis_total_count=1,
            wall_time_seconds=0.1,
            metadata={
                "harness": {
                    "has_session_ledger": True,
                    "has_checkpoint": True,
                    "artifact_count": 2,
                    "tool_event_count": 3,
                }
            },
        ),
        ChallengeResult(
            challenge_id="b",
            solved=False,
            expected_solved=True,
            wrong_flag_count=0,
            flag_submit_attempts=0,
            chain_iterations=1,
            stop_reason="stop",
            stop_reason_class="give_up",
            has_source_only_stop=False,
            hypothesis_exhausted_count=0,
            hypothesis_total_count=1,
            wall_time_seconds=0.2,
            metadata={
                "harness": {
                    "has_session_ledger": False,
                    "has_checkpoint": False,
                    "artifact_count": 0,
                    "tool_event_count": 0,
                }
            },
        ),
    ]

    report = benchmark_runner._aggregate_report(
        run_id="benchmark_cov",
        timestamp="2026-05-30T00:00:00+00:00",
        git_sha="deadbeef",
        results=results,
    )

    assert report.metadata["harness_session_coverage"] == 0.5
    assert report.metadata["harness_checkpoint_coverage"] == 0.5
    assert report.metadata["harness_artifact_coverage"] == 0.5
    assert report.metadata["harness_tool_event_coverage"] == 0.5
