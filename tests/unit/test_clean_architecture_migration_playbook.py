"""Tests for the clean architecture migration playbook status ledger."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK_PATH = (
    REPO_ROOT
    / "docs"
    / "dev"
    / "FlagHunter_Clean_Architecture_Migration_Playbook_v0.1_2026-07-04.md"
)


def _playbook_text() -> str:
    return PLAYBOOK_PATH.read_text(encoding="utf-8")


def test_playbook_tracks_completed_phase4_application_services() -> None:
    text = _playbook_text()

    assert "## 7. Current Execution Status" in text
    assert "Phase 4 application service skeletons completed" in text
    for service_name in (
        "BuildChallengeRunSnapshot",
        "RecordTaskReceipt",
        "BuildEvidenceSnapshot",
        "ReviewClaim",
        "RecordToolReceipt",
        "DispatchWorkerTask",
    ):
        assert service_name in text


def test_playbook_records_next_approval_gate_after_phase4_skeletons() -> None:
    text = _playbook_text()

    assert "Next approval gate" in text
    assert "production wiring" in text
    assert "composition root" in text
    assert "CTFTaskDispatcher" in text
    assert "ToolExecutor" in text
    assert "WorkerPool" in text
    assert "MCP production wiring" in text


def test_playbook_records_phase4_verification_baseline() -> None:
    text = _playbook_text()

    assert "tests/unit/test_import_layers.py" in text
    assert "tests/unit/test_application_worker_task_service.py" in text
    assert "application-service-boundary" in text


def test_playbook_records_read_only_presentation_candidate_audit() -> None:
    text = _playbook_text()

    assert "Read-only presentation/query path candidate audit" in text
    assert "flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot" in text
    assert (
        "flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events"
        in text
    )
    assert "flaghunter/interface/web_serialize_task.py::_serialize_task" in text
    assert "flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision" in text
    assert "flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines" in text
    assert "Candidate A" in text
    assert "Candidate B" in text
    assert "Candidate C" in text


def test_playbook_records_read_path_approval_plan_requirements() -> None:
    text = _playbook_text()

    assert "First read-path switch approval plan must include" in text
    assert "file list" in text
    assert "risk" in text
    assert "rollback point" in text
    assert "representative fixture" in text
    assert "no proof writes" in text
    assert "no dispatcher loop changes" in text
    assert "MCP production wiring remains out of scope" in text


def test_playbook_records_candidate_b_approval_plan() -> None:
    text = _playbook_text()

    assert "Candidate B approval plan" in text
    assert (
        "flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events"
        in text
    )
    assert "tests/unit/web_console/test_trace_timeline_read_model_switch.py" in text
    assert "representative fixture" in text
    assert "old/new output equivalence" in text
    assert "rollback point" in text
    assert "no proof writes" in text
    assert "no dispatcher loop changes" in text
    assert "no ToolExecutor changes" in text
    assert "no WorkerPool/CrewOrchestrator changes" in text
    assert "no MCP production wiring" in text
    assert "approval required before implementation" in text


def test_playbook_records_candidate_b_characterization_baseline() -> None:
    text = _playbook_text()

    assert "Candidate B characterization baseline" in text
    assert "tests/unit/web_console/test_trace_timeline_read_model_switch.py" in text
    assert "existing control-observation timeline output" in text
    assert "no production path switch" in text
    assert "no dispatcher loop changes" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_b_source_guard_baseline() -> None:
    text = _playbook_text()

    assert "Candidate B source guard baseline" in text
    assert "_build_control_observation_timeline_events" in text
    assert "no concrete execution imports" in text
    assert "no side-effect sinks" in text
    assert "no proof upgrade surfaces" in text


def test_playbook_records_candidate_a_source_guard_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A source guard baseline" in text
    assert "flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot" in text
    assert "tests/unit/interface/test_blackboard_lite.py" in text
    assert "no execution/runtime imports beyond existing read-side projection dependencies" in text
    assert "no proof upgrade surfaces" in text
    assert "no production path switch" in text


def test_playbook_records_candidate_a_approval_plan() -> None:
    text = _playbook_text()

    assert "Candidate A approval plan" in text
    assert "flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot" in text
    assert "tests/unit/interface/test_blackboard_lite.py" in text
    assert "neutral blackboard projection builder" in text
    assert "old/new output equivalence" in text
    assert "rollback point" in text
    assert "approval required before implementation" in text
    assert "no dispatcher loop changes" in text
    assert "no ToolExecutor changes" in text
    assert "no WorkerPool/CrewOrchestrator changes" in text
    assert "no MCP production wiring" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_c_approval_plan() -> None:
    text = _playbook_text()

    assert "Candidate C approval plan" in text
    assert "flaghunter/interface/web_serialize_task.py::_serialize_task" in text
    assert "flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision" in text
    assert "after Candidate A output equivalence is proven" in text
    assert "one call-site family per commit" in text
    assert "rollback point" in text
    assert "approval required before implementation" in text
    assert "no dispatcher loop changes" in text
    assert "no ToolExecutor changes" in text
    assert "no WorkerPool/CrewOrchestrator changes" in text
    assert "no MCP production wiring" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_c_source_guard_baseline() -> None:
    text = _playbook_text()

    assert "Candidate C source guard baseline" in text
    assert "flaghunter/interface/web_serialize_task.py::_serialize_task" in text
    assert "flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision" in text
    assert "tests/unit/interface/test_web_server.py" in text
    assert "no execution/runtime imports" in text
    assert "no side-effect sinks" in text
    assert "no proof upgrade surfaces" in text


def test_playbook_records_deferred_mcp_readback_approval_plan() -> None:
    text = _playbook_text()

    assert "Deferred MCP readback approval plan" in text
    assert "flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines" in text
    assert "approval required before implementation" in text
    assert "after Web read-model projection equivalence is proven" in text
    assert "no MCP production wiring" in text
    assert "no dispatcher loop changes" in text
    assert "no ToolExecutor changes" in text
    assert "no WorkerPool/CrewOrchestrator changes" in text
    assert "no proof authority behavior changes" in text
    assert "rollback point" in text
    assert "old/new output equivalence" in text
