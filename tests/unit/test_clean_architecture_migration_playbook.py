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


def _section_text(text: str, heading: str) -> str:
    marker = f"#### {heading}"
    start = text.index(marker)
    next_heading = text.find("\n#### ", start + len(marker))
    if next_heading == -1:
        return text[start:]
    return text[start:next_heading]


def _markdown_table_rows(section: str) -> list[dict[str, str]]:
    table_lines = [
        line.strip()
        for line in section.splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    header = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows.append(dict(zip(header, cells)))
    return rows


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


def test_playbook_records_board_read_model_skeleton_baseline() -> None:
    text = _playbook_text()

    assert "Challenge board read-model skeleton baseline" in text
    assert "BuildChallengeBoardReadModel" in text
    assert "ChallengeBoardReadModel" in text
    assert "BoardItem" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no dispatcher loop changes" in text
    assert "no MCP production wiring" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_board_read_model_sanitization_baseline() -> None:
    text = _playbook_text()

    assert "Challenge board read-model sanitization baseline" in text
    assert "BoardItem" in text
    assert "ChallengeBoardReadModel" in text
    assert "shared sanitization helpers" in text
    assert "raw body" in text
    assert "sensitive token" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_projection_fixture_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral board projection fixture baseline" in text
    assert "build_task_board_projection" in text
    assert "ChallengeBoardReadModel" in text
    assert "Candidate A-compatible response key shape" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no MCP production wiring" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_evidence_projection_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral evidence projection baseline" in text
    assert "non-pending evidence" in text
    assert "facts" in text
    assert "pending verification" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_degraded_projection_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral degraded projection baseline" in text
    assert "empty or malformed neutral board inputs" in text
    assert "quiet empty projection" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


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


def test_playbook_records_candidate_b_implementation_readiness_checklist() -> None:
    text = _playbook_text()
    section = _section_text(text, "Candidate B implementation readiness checklist")

    assert "Candidate B implementation readiness checklist" in text
    assert "Status: ready for approval review, not approved for implementation." in text
    for baseline in (
        "Candidate B approval plan",
        "Candidate B characterization baseline",
        "Candidate B source guard baseline",
    ):
        assert baseline in text
    for evidence_test in (
        "test_control_observation_timeline_projects_supported_rows",
        "test_control_observation_timeline_handles_empty_or_malformed_input",
        "test_trace_timeline_includes_observations_without_mutating_task",
        "test_control_observation_timeline_source_stays_read_only",
    ):
        assert evidence_test in section
    assert "flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events" in text
    assert "tests/unit/web_console/test_trace_timeline_read_model_switch.py" in text
    assert "old/new output equivalence" in text
    assert "event IDs, timestamps, `kind`, `title`, `summary`, `driver`, and `input` fields" in text
    assert "approval is still required before editing `flaghunter/interface/web_trace_timeline.py`" in text
    assert "one implementation commit only" in text
    assert "rollback point: revert the single Candidate B implementation commit" in text
    for non_goal in (
        "no dispatcher loop changes",
        "no `CTFState` ownership split",
        "no `CTFVerifier` proof behavior changes",
        "no ToolExecutor changes",
        "no WorkerPool/CrewOrchestrator changes",
        "no MCP production wiring",
        "no composition root changes",
        "no concrete adapter implementation",
        "no proof authority behavior changes",
        "no P5 implementation",
    ):
        assert non_goal in text
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/web_console/test_trace_timeline_read_model_switch.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q",
        "git diff --check",
    ):
        assert command in text


def test_playbook_records_candidate_b_approved_execution_checklist() -> None:
    text = _playbook_text()
    section = _section_text(text, "Candidate B approved execution checklist")

    assert "Status: not approved; checklist only." in section
    for required_item in (
        "confirm Candidate A output equivalence has landed",
        "confirm explicit Candidate B implementation approval",
        "update the pre-approval guard in the same implementation commit",
        "edit only `flaghunter/interface/web_trace_timeline.py`",
        "preserve event IDs, timestamps, `kind`, `title`, `summary`, `driver`, and `input` fields",
        "prove old/new output equivalence",
        "record implementation landing evidence",
        "rollback point: revert the single Candidate B implementation commit",
    ):
        assert required_item in section
    for forbidden_scope in (
        "do not modify `flaghunter/interface/blackboard_lite.py`",
        "do not modify `flaghunter/mcp/server/mcp_tools.py`",
        "do not modify `flaghunter/interface/web_serialize_task.py`",
        "do not modify `flaghunter/interface/web_control_decision.py`",
        "no dispatcher loop changes",
        "no ToolExecutor changes",
        "no proof authority behavior changes",
    ):
        assert forbidden_scope in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/web_console/test_trace_timeline_read_model_switch.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q",
        "git diff --check",
    ):
        assert command in section


def test_playbook_records_candidate_a_source_guard_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A source guard baseline" in text
    assert "flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot" in text
    assert "tests/unit/interface/test_blackboard_lite.py" in text
    assert "no execution/runtime imports beyond existing read-side projection dependencies" in text
    assert "no proof upgrade surfaces" in text
    assert "no production path switch" in text


def test_playbook_records_candidate_a_representative_fixture_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A representative fixture baseline" in text
    assert "tests/unit/interface/test_blackboard_lite.py" in text
    assert "test_candidate_a_representative_fixture_locks_public_projection_shape" in text
    assert "representative existing `ctfStateSnapshot` inputs" in text
    assert "decision records, ingress handoff, session context action results" in text
    assert "candidates and attack surfaces" in text
    assert "old/new output equivalence" in text
    assert "no production path switch" in text


def test_playbook_records_candidate_a_missing_malformed_fixture_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A missing/malformed fixture baseline" in text
    assert "tests/unit/interface/test_blackboard_lite.py" in text
    assert "test_candidate_a_missing_or_malformed_state_snapshot_baseline" in text
    assert "missing or malformed state snapshots" in text
    assert "resume facts and selected ingress candidate" in text
    assert "old/new output equivalence" in text
    assert "no production path switch" in text


def test_playbook_records_candidate_a_decision_ingress_action_result_fixture_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A decision/ingress/action-result fixture baseline" in text
    assert "tests/unit/interface/test_blackboard_lite.py" in text
    assert "test_candidate_a_decision_ingress_action_result_baseline" in text
    assert "decision records, ingress handoff, and session context action results" in text
    assert "selected candidate and recommended action ordering" in text
    assert "old/new output equivalence" in text
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


def test_playbook_records_candidate_a_implementation_readiness_checklist() -> None:
    text = _playbook_text()
    section = _section_text(text, "Candidate A implementation readiness checklist")

    assert "Candidate A implementation readiness checklist" in text
    for baseline in (
        "neutral board projection fixture baseline",
        "neutral evidence projection baseline",
        "neutral degraded projection baseline",
        "neutral malformed board item projection baseline",
        "neutral recommended action projection baseline",
        "neutral explicit recommendation marker baseline",
        "neutral candidate/action-result degraded baseline",
        "neutral suppressed recommendation baseline",
    ):
        assert baseline in text
    for evidence_test in (
        "test_candidate_a_pre_approval_guard_blocks_neutral_builder_wiring",
        "test_candidate_a_representative_fixture_locks_public_projection_shape",
        "test_candidate_a_missing_or_malformed_state_snapshot_baseline",
        "test_candidate_a_decision_ingress_action_result_baseline",
    ):
        assert evidence_test in section
    assert "approval is still required before editing `flaghunter/interface/blackboard_lite.py`" in text
    assert "one implementation commit only" in text
    assert "old/new output equivalence must be proven in `tests/unit/interface/test_blackboard_lite.py`" in text
    assert "do not modify `flaghunter/mcp/server/mcp_tools.py`" in text
    assert "do not modify `flaghunter/interface/web_serialize_task.py`" in text
    assert "do not modify `flaghunter/interface/web_control_decision.py`" in text
    assert ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/interface/test_blackboard_lite.py -q" in text
    assert ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_application_board_read_model_service.py tests/unit/test_clean_architecture_migration_playbook.py -q" in text


def test_playbook_records_candidate_a_implementation_approval_request() -> None:
    text = _playbook_text()

    assert "Candidate A implementation approval request" in text
    assert "Status: approval requested, not approved" in text
    assert "flaghunter/interface/blackboard_lite.py" in text
    assert "tests/unit/interface/test_blackboard_lite.py" in text
    assert "flaghunter/application/challenge/board_read_model_service.py" in text
    assert "risk: medium" in text
    assert "read-only Web task detail projection" in text
    assert "API serialization/control-decision inputs" in text
    assert "MCP readback formatting indirectly" in text
    assert "rollback point: revert the single Candidate A implementation commit" in text
    assert "old/new output equivalence" in text
    for non_goal in (
        "no dispatcher loop changes",
        "no `CTFState` ownership split",
        "no `CTFVerifier` proof behavior changes",
        "no ToolExecutor changes",
        "no WorkerPool/CrewOrchestrator changes",
        "no MCP production wiring",
        "no composition root changes",
        "no concrete adapter implementation",
        "no proof authority behavior changes",
        "no P5 implementation",
    ):
        assert non_goal in text
    for forbidden_edit in (
        "do not modify `flaghunter/mcp/server/mcp_tools.py`",
        "do not modify `flaghunter/interface/web_serialize_task.py`",
        "do not modify `flaghunter/interface/web_control_decision.py`",
    ):
        assert forbidden_edit in text
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/interface/test_blackboard_lite.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_application_board_read_model_service.py tests/unit/test_clean_architecture_migration_playbook.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q",
        "git diff --check",
    ):
        assert command in text


def test_playbook_records_candidate_a_approved_execution_checklist() -> None:
    text = _playbook_text()
    section = _section_text(text, "Candidate A approved execution checklist")

    assert "Status: not approved; checklist only." in section
    for required_item in (
        "confirm explicit Candidate A approval",
        "update the pre-approval guard in the same implementation commit",
        "edit only `flaghunter/interface/blackboard_lite.py`",
        "preserve current public projection keys",
        "prove old/new output equivalence",
        "record implementation landing evidence",
        "rollback point: revert the single Candidate A implementation commit",
    ):
        assert required_item in section
    for forbidden_scope in (
        "do not modify `flaghunter/mcp/server/mcp_tools.py`",
        "do not modify `flaghunter/interface/web_trace_timeline.py`",
        "do not modify `flaghunter/interface/web_serialize_task.py`",
        "do not modify `flaghunter/interface/web_control_decision.py`",
        "no dispatcher loop changes",
        "no ToolExecutor changes",
        "no proof authority behavior changes",
    ):
        assert forbidden_scope in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/interface/test_blackboard_lite.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_application_board_read_model_service.py tests/unit/test_clean_architecture_migration_playbook.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q",
        "git diff --check",
    ):
        assert command in section


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


def test_playbook_records_candidate_c_implementation_readiness_checklist() -> None:
    text = _playbook_text()
    section = _section_text(text, "Candidate C implementation readiness checklist")

    assert "Candidate C implementation readiness checklist" in text
    assert "Status: blocked on Candidate A approval, not approved for implementation." in text
    assert "Candidate A output equivalence is proven" in text
    assert "Candidate C approval plan" in text
    assert "Candidate C source guard baseline" in text
    assert "Candidate C serialize-task projection fixture baseline" in section
    assert "Candidate C control-decision snapshot merge fixture baseline" in section
    assert (
        "test_candidate_c_serialize_task_fixture_preserves_snapshot_and_summaries_before_switch"
        in section
    )
    assert "test_candidate_c_control_decision_snapshot_merge_fixture_before_switch" in section
    assert "flaghunter/interface/web_serialize_task.py::_serialize_task" in text
    assert "flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision" in text
    assert "tests/unit/interface/test_blackboard_lite.py" in text
    assert "tests/unit/interface/test_web_server.py" in text
    assert "one call-site family per commit" in text
    assert "serialize-task projection first" in text
    assert "control-decision snapshot merge second" in text
    assert "old/new output equivalence" in text
    assert "preserved fallback merge behavior" in text
    assert "rollback point: revert the single Candidate C implementation commit" in text
    for non_goal in (
        "no dispatcher loop changes",
        "no `CTFState` ownership split",
        "no `CTFVerifier` proof behavior changes",
        "no ToolExecutor changes",
        "no WorkerPool/CrewOrchestrator changes",
        "no MCP production wiring",
        "no composition root changes",
        "no concrete adapter implementation",
        "no proof authority behavior changes",
        "no P5 implementation",
    ):
        assert non_goal in text
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/interface/test_blackboard_lite.py tests/unit/test_clean_architecture_migration_playbook.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/interface/test_web_server.py tests/unit/test_clean_architecture_migration_playbook.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q",
        "git diff --check",
    ):
        assert command in text


def test_playbook_records_candidate_c_approved_execution_checklist() -> None:
    text = _playbook_text()
    section = _section_text(text, "Candidate C approved execution checklist")

    assert "Status: not approved; checklist only." in section
    for required_item in (
        "confirm Candidate A output equivalence has landed",
        "confirm explicit Candidate C implementation approval",
        "one call-site family per commit",
        "serialize-task projection first",
        "control-decision snapshot merge second",
        "update the pre-approval guard in the same implementation commit",
        "prove old/new output equivalence",
        "record implementation landing evidence",
        "rollback point: revert the single Candidate C implementation commit",
    ):
        assert required_item in section
    for allowed_target in (
        "edit only `flaghunter/interface/web_serialize_task.py` for the serialize-task commit",
        "edit only `flaghunter/interface/web_control_decision.py` for the control-decision commit",
    ):
        assert allowed_target in section
    for forbidden_scope in (
        "do not modify `flaghunter/interface/blackboard_lite.py`",
        "do not modify `flaghunter/interface/web_trace_timeline.py`",
        "do not modify `flaghunter/mcp/server/mcp_tools.py`",
        "no bundled serialize-task and control-decision implementation",
        "no dispatcher loop changes",
        "no ToolExecutor changes",
        "no proof authority behavior changes",
    ):
        assert forbidden_scope in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/interface/test_blackboard_lite.py tests/unit/test_clean_architecture_migration_playbook.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/interface/test_web_server.py tests/unit/test_clean_architecture_migration_playbook.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q",
        "git diff --check",
    ):
        assert command in section


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


def test_playbook_records_deferred_mcp_source_guard_baseline() -> None:
    text = _playbook_text()

    assert "Deferred MCP source guard baseline" in text
    assert "flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines" in text
    assert "tests/unit/mcp/test_mcp_ingress_mode_contract.py" in text
    assert "no task execution or handler routing changes" in text
    assert "no side-effect sinks" in text
    assert "no proof upgrade surfaces" in text
    assert "no MCP production wiring" in text


def test_playbook_records_deferred_mcp_readback_formatting_fixture_baseline() -> None:
    text = _playbook_text()

    assert "Deferred MCP readback formatting fixture baseline" in text
    assert "tests/unit/mcp/test_mcp_ingress_mode_contract.py" in text
    assert "test_mcp_blackboard_readback_formatting_matches_candidate_a_projection" in text
    assert "representative MCP readback text" in text
    assert "old/new output equivalence" in text
    assert "no MCP production wiring" in text
    assert "no task execution or handler routing changes" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_deferred_mcp_empty_malformed_fixture_baseline() -> None:
    text = _playbook_text()

    assert "Deferred MCP empty/malformed readback fixture baseline" in text
    assert "tests/unit/mcp/test_mcp_ingress_mode_contract.py" in text
    assert "test_mcp_blackboard_readback_empty_and_malformed_inputs_are_quiet" in text
    assert "empty, missing, or malformed blackboard snapshot inputs" in text
    assert "old/new output equivalence" in text
    assert "no MCP production wiring" in text
    assert "no task execution or handler routing changes" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_deferred_mcp_implementation_readiness_checklist() -> None:
    text = _playbook_text()
    section = _section_text(text, "Deferred MCP implementation readiness checklist")

    assert "Deferred MCP implementation readiness checklist" in text
    assert "Status: blocked on Web projection equivalence and explicit MCP approval, not approved for implementation." in text
    assert "Deferred MCP readback approval plan" in text
    assert "Deferred MCP source guard baseline" in text
    assert "Deferred MCP pre-approval production wiring guard" in section
    assert "test_deferred_mcp_pre_approval_guard_blocks_neutral_projection_wiring" in section
    assert "Deferred MCP readback formatting fixture baseline" in text
    assert "Deferred MCP empty/malformed readback fixture baseline" in text
    assert "flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines" in text
    assert "tests/unit/mcp/test_mcp_ingress_mode_contract.py" in text
    assert "after Web read-model projection equivalence is proven" in text
    assert "explicit MCP production wiring approval" in text
    assert "must consume the same approved read-model projection" in text
    assert "must not become an independent projection shape" in text
    assert "old/new output equivalence" in text
    assert "preserved ordering for facts, hypotheses, pending verification items, candidates, action results, and attack surfaces" in text
    assert "rollback point: revert the single Deferred MCP implementation commit" in text
    for non_goal in (
        "no MCP production wiring without explicit approval",
        "no task execution or handler routing changes",
        "no dispatcher loop changes",
        "no `CTFState` ownership split",
        "no `CTFVerifier` proof behavior changes",
        "no ToolExecutor changes",
        "no WorkerPool/CrewOrchestrator changes",
        "no composition root changes",
        "no concrete adapter implementation",
        "no proof authority behavior changes",
        "no P5 implementation",
    ):
        assert non_goal in text
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/mcp/test_mcp_ingress_mode_contract.py tests/unit/test_clean_architecture_migration_playbook.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q",
        "git diff --check",
    ):
        assert command in text


def test_playbook_records_deferred_mcp_approved_execution_checklist() -> None:
    text = _playbook_text()
    section = _section_text(text, "Deferred MCP approved execution checklist")

    assert "Status: not approved; checklist only." in section
    for required_item in (
        "confirm Web projection equivalence has landed",
        "confirm explicit MCP production wiring approval",
        "update the pre-approval guard in the same implementation commit",
        "edit only `flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines`",
        "consume the same approved read-model projection",
        "must not become an independent projection shape",
        "preserve readback line text, ordering, and omission behavior",
        "prove old/new output equivalence",
        "record implementation landing evidence",
        "rollback point: revert the single Deferred MCP implementation commit",
    ):
        assert required_item in section
    for forbidden_scope in (
        "do not modify Candidate A, Candidate B, or Candidate C production helpers",
        "no task execution or handler routing changes",
        "no dispatcher loop changes",
        "no ToolExecutor changes",
        "no WorkerPool/CrewOrchestrator changes",
        "no composition root changes",
        "no proof authority behavior changes",
    ):
        assert forbidden_scope in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/mcp/test_mcp_ingress_mode_contract.py tests/unit/test_clean_architecture_migration_playbook.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q",
        "git diff --check",
    ):
        assert command in section


def test_playbook_records_first_read_path_switch_sequence_gate() -> None:
    text = _playbook_text()

    assert "First read-path switch sequence gate" in text
    assert "Candidate A is the only eligible first production read-path switch" in text
    assert "Candidate A approval request must be accepted before implementation" in text
    assert "Candidate B may not be implemented before Candidate A lands" in text
    assert "Candidate C may not be implemented before Candidate A lands" in text
    assert "Deferred MCP may not be implemented before Web projection equivalence lands" in text
    assert "one production call-site family per commit" in text
    assert "no bundled Web and MCP implementation commits" in text
    assert "no parallel projection shapes" in text
    assert "rollback point: revert the single implementation commit for the affected read path" in text
    for path in (
        "flaghunter/interface/blackboard_lite.py",
        "flaghunter/interface/web_trace_timeline.py",
        "flaghunter/interface/web_serialize_task.py",
        "flaghunter/interface/web_control_decision.py",
        "flaghunter/mcp/server/mcp_tools.py",
    ):
        assert path in text
    for non_goal in (
        "no dispatcher loop changes",
        "no `CTFState` ownership split",
        "no `CTFVerifier` proof behavior changes",
        "no ToolExecutor changes",
        "no WorkerPool/CrewOrchestrator changes",
        "no composition root changes",
        "no proof authority behavior changes",
        "no P5 implementation",
    ):
        assert non_goal in text


def test_playbook_records_read_path_switch_acceptance_matrix() -> None:
    text = _playbook_text()

    assert "Read-path switch acceptance matrix" in text
    assert "Candidate A | approval requested, not approved |" in text
    assert "Candidate B | ready for approval review, not approved |" in text
    assert "Candidate C | blocked on Candidate A approval, not approved |" in text
    assert "Deferred MCP | blocked on Web projection equivalence and explicit MCP approval, not approved |" in text
    assert "blackboard_lite.py" in text
    assert "web_trace_timeline.py" in text
    assert "web_serialize_task.py and web_control_decision.py" in text
    assert "mcp_tools.py" in text
    assert "Candidate A equivalence lands" in text
    assert "Web projection equivalence lands" in text
    for required_evidence in (
        "old/new output equivalence",
        "source guard remains green",
        "focused regression remains green",
        "git diff --check remains green",
    ):
        assert required_evidence in text
    for forbidden_scope in (
        "dispatcher loop",
        "CTFState ownership",
        "CTFVerifier proof behavior",
        "ToolExecutor",
        "WorkerPool/CrewOrchestrator",
        "composition root",
        "proof authority behavior",
        "P5",
    ):
        assert forbidden_scope in text


def test_playbook_records_read_path_source_guard_ledger() -> None:
    text = _playbook_text()

    assert "Read-path source guard ledger" in text
    assert "Candidate A" in text
    assert "tests/unit/interface/test_blackboard_lite.py" in text
    assert "flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot" in text
    assert "Candidate B" in text
    assert "tests/unit/web_console/test_trace_timeline_read_model_switch.py" in text
    assert (
        "flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events"
        in text
    )
    assert "Candidate C" in text
    assert "tests/unit/interface/test_web_server.py" in text
    assert "flaghunter/interface/web_serialize_task.py::_serialize_task" in text
    assert "flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision" in text
    assert "Deferred MCP" in text
    assert "tests/unit/mcp/test_mcp_ingress_mode_contract.py" in text
    assert "flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines" in text
    for guard in (
        "no execution/runtime imports",
        "no side-effect sinks",
        "no proof upgrade surfaces",
        "no production wiring",
    ):
        assert guard in text


def test_playbook_records_read_path_approval_state_transitions() -> None:
    text = _playbook_text()

    assert "Read-path approval state transitions" in text
    for state in (
        "not approved",
        "approval requested",
        "approved for implementation",
        "implementation landed",
        "blocked",
    ):
        assert state in text
    for transition in (
        "not approved -> approval requested",
        "approval requested -> approved for implementation",
        "approved for implementation -> implementation landed",
        "ready for approval review -> approval requested",
        "blocked -> approval requested",
    ):
        assert transition in text
    for forbidden_transition in (
        "not approved -> implementation landed",
        "approval requested -> implementation landed",
        "blocked -> implementation landed",
        "ready for approval review -> implementation landed",
    ):
        assert forbidden_transition in text
    assert "explicit human approval" in text
    assert "single implementation commit" in text
    assert "old/new output equivalence" in text
    assert "source guard remains green" in text


def test_playbook_records_read_path_approval_drift_guard() -> None:
    text = _playbook_text()

    assert "Read-path approval drift guard" in text
    assert "Current approval facts must not drift silently" in text
    for candidate_status in (
        "Candidate A: approval requested, not approved",
        "Candidate B: ready for approval review, not approved",
        "Candidate C: blocked on Candidate A approval, not approved",
        "Deferred MCP: blocked on Web projection equivalence and explicit MCP approval, not approved",
    ):
        assert candidate_status in text
    for required_update in (
        "the acceptance matrix row",
        "the approval state transition section",
        "the relevant implementation readiness checklist",
        "the verification evidence for that candidate",
    ):
        assert required_update in text
    assert "A status change alone is not implementation approval" in text
    assert "No candidate may be marked `implementation landed` without a commit SHA" in text


def test_playbook_records_read_path_approval_package_summary() -> None:
    text = _playbook_text()

    assert "Read-path approval package summary" in text
    for candidate_status in (
        "Candidate A | approval requested, not approved",
        "Candidate B | ready for approval review, not approved",
        "Candidate C | blocked on Candidate A approval, not approved",
        "Deferred MCP | blocked on Web projection equivalence and explicit MCP approval, not approved",
    ):
        assert candidate_status in text
    for required_phrase in (
        "evidence present",
        "remaining blocker",
        "implementation not approved",
        "no production path switch",
        "no MCP production wiring",
        "no proof authority behavior changes",
    ):
        assert required_phrase in text


def test_playbook_records_read_path_implementation_landing_record_template() -> None:
    text = _playbook_text()

    assert "Read-path implementation landing record template" in text
    for required_field in (
        "candidate",
        "implementation commit SHA",
        "old/new output equivalence",
        "pre-approval guard update",
        "focused regression result",
        "architecture/source-guard result",
        "post-push branch status",
        "rollback command",
    ):
        assert required_field in text
    for required_boundary in (
        "no bundled Web and MCP implementation",
        "no dispatcher loop changes",
        "no ToolExecutor changes",
        "no WorkerPool/CrewOrchestrator changes",
        "no composition root changes",
        "no proof authority behavior changes",
    ):
        assert required_boundary in text


def test_playbook_records_read_path_approval_status_consistency_guard() -> None:
    text = _playbook_text()

    assert "Read-path approval status consistency guard" in text
    expected_statuses = {
        "Candidate A": "approval requested, not approved",
        "Candidate B": "ready for approval review, not approved",
        "Candidate C": "blocked on Candidate A approval, not approved",
        "Deferred MCP": "blocked on Web projection equivalence and explicit MCP approval, not approved",
    }
    for candidate, status in expected_statuses.items():
        assert f"{candidate}: {status}" in text
        assert f"{candidate} | {status} |" in text
    for required_phrase in (
        "single source of approval truth",
        "same governance commit",
        "candidate-specific implementation readiness checklist",
        "no status-only implementation approval",
        "approval drift must fail review",
    ):
        assert required_phrase in text


def test_playbook_records_machine_readable_read_path_candidate_status_ledger() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path candidate status ledger")

    assert "Status: machine-readable status ledger recorded, no implementation approved by this section." in section
    expected_rows = (
        "| Candidate A | approval requested, not approved | false | explicit Candidate A implementation approval |",
        "| Candidate B | ready for approval review, not approved | false | Candidate A equivalence lands and Candidate B implementation approval |",
        "| Candidate C | blocked on Candidate A approval, not approved | false | Candidate A equivalence lands and Candidate C implementation approval |",
        "| Deferred MCP | blocked on Web projection equivalence and explicit MCP approval, not approved | false | Web projection equivalence lands plus explicit MCP production wiring approval |",
    )
    for row in expected_rows:
        assert row in section
    for required_phrase in (
        "approvedForImplementation",
        "machine-readable approval ledger",
        "must be updated in the same governance commit",
        "no implementation approval by implication",
        "no production path switch",
    ):
        assert required_phrase in section


def test_playbook_parses_read_path_candidate_status_consistently() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path parsed status consistency guard")

    assert "Status: parsed consistency guard recorded, no implementation approved by this section." in section
    assert "parse `Read-path candidate status ledger`" in section
    assert "compare it with `Read-path switch acceptance matrix`" in section
    assert "compare it with `Read-path approval package summary`" in section

    ledger_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path candidate status ledger")
        )
    }
    acceptance_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path switch acceptance matrix")
        )
    }
    package_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path approval package summary")
        )
    }

    assert set(ledger_rows) == {"Candidate A", "Candidate B", "Candidate C", "Deferred MCP"}
    assert set(ledger_rows) == set(acceptance_rows) == set(package_rows)
    for candidate, ledger_row in ledger_rows.items():
        assert ledger_row["approvedForImplementation"] == "false"
        assert ledger_row["canonicalStatus"] == acceptance_rows[candidate]["Status"]
        assert ledger_row["canonicalStatus"] == package_rows[candidate]["Current status"]


def test_playbook_parses_read_path_next_gate_consistently() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path nextGate consistency guard")

    assert "Status: nextGate consistency guard recorded, no implementation approved by this section." in section
    assert "ledger `nextGate` matches the acceptance matrix `Unblock condition`" in section
    assert "ledger `nextGate` matches the approval package `remaining blocker`" in section

    ledger_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path candidate status ledger")
        )
    }
    acceptance_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path switch acceptance matrix")
        )
    }
    package_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path approval package summary")
        )
    }

    assert set(ledger_rows) == set(acceptance_rows) == set(package_rows)
    for candidate, ledger_row in ledger_rows.items():
        assert ledger_row["nextGate"] == acceptance_rows[candidate]["Unblock condition"]
        assert ledger_row["nextGate"] == package_rows[candidate]["remaining blocker"]


def test_playbook_parses_read_path_approved_execution_checklist_index() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path approved execution checklist index")

    assert "Status: checklist index recorded, no implementation approved by this section." in section
    checklist_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(section)
    }

    expected_sections = {
        "Candidate A": "Candidate A approved execution checklist",
        "Candidate B": "Candidate B approved execution checklist",
        "Candidate C": "Candidate C approved execution checklist",
        "Deferred MCP": "Deferred MCP approved execution checklist",
    }
    assert set(checklist_rows) == set(expected_sections)
    for candidate, checklist_heading in expected_sections.items():
        row = checklist_rows[candidate]
        checklist_section = _section_text(text, checklist_heading)

        assert row["Checklist section"] == f"`{checklist_heading}`"
        assert row["Checklist status"] == "not approved; checklist only"
        assert row["Approval state"] == "implementation not approved"
        assert "Status: not approved; checklist only." in checklist_section


def test_playbook_parses_read_path_implementation_approval_readiness_report() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path implementation approval readiness report")

    assert "Status: readiness report recorded, no implementation approved by this section." in section
    readiness_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(section)
    }
    ledger_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path candidate status ledger")
        )
    }
    package_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path approval package summary")
        )
    }

    expected_readiness = {
        "Candidate A": "approval package ready; explicit implementation approval missing",
        "Candidate B": "sequence blocked; Candidate A equivalence missing",
        "Candidate C": "sequence blocked; Candidate A equivalence missing",
        "Deferred MCP": "sequence blocked; Web projection equivalence and MCP approval missing",
    }
    assert set(readiness_rows) == set(ledger_rows) == set(package_rows)
    for candidate, expected_state in expected_readiness.items():
        row = readiness_rows[candidate]
        assert row["Readiness state"] == expected_state
        assert row["Current status"] == ledger_rows[candidate]["canonicalStatus"]
        assert row["Missing approval"] == package_rows[candidate]["remaining blocker"]
        assert row["Implementation approved"] == "false"


def test_playbook_records_application_service_source_guard_baseline() -> None:
    text = _playbook_text()

    assert "Application service source guard baseline" in text
    assert "tests/unit/test_application_service_source_guards.py" in text
    assert "application services import only neutral contracts and ports" in text
    assert "no concrete execution imports" in text
    assert "no side-effect sinks" in text
    assert "no proof upgrade surfaces" in text
    assert "no production wiring" in text


def test_playbook_records_adapter_port_substitution_fixture_baseline() -> None:
    text = _playbook_text()

    assert "Adapter port substitution fixture baseline" in text
    assert "tests/unit/test_adapter_port_substitution.py" in text
    assert "injected ports can be substituted without production wiring" in text
    assert "tool runner and runtime action adapters" in text
    assert "no concrete runtime or tool executor construction" in text
    assert "no dispatcher, MCP, crew, or proof authority wiring" in text


def test_playbook_records_storage_adapter_substitution_fixture_baseline() -> None:
    text = _playbook_text()

    assert "Storage adapter substitution fixture baseline" in text
    assert "tests/unit/test_adapter_port_substitution.py" in text
    assert "state, read model, claim, and checkpoint store adapters" in text
    assert "fake injected stores can be substituted without production wiring" in text
    assert "no file-backed store construction" in text
    assert "no dispatcher, MCP, crew, or proof authority wiring" in text


def test_playbook_records_audit_artifact_adapter_substitution_fixture_baseline() -> None:
    text = _playbook_text()

    assert "Audit/artifact adapter substitution fixture baseline" in text
    assert "tests/unit/test_adapter_port_substitution.py" in text
    assert "audit and artifact store adapters" in text
    assert "fake injected stores can be substituted without production wiring" in text
    assert "no audit log or artifact file construction" in text
    assert "no dispatcher, MCP, crew, or proof authority wiring" in text


def test_playbook_records_crew_task_graph_adapter_substitution_fixture_baseline() -> None:
    text = _playbook_text()

    assert "Crew/task graph adapter substitution fixture baseline" in text
    assert "tests/unit/test_adapter_port_substitution.py" in text
    assert "crew bridge and task graph runner adapters" in text
    assert "fake injected runners can be substituted without production wiring" in text
    assert "no WorkerPool or CrewOrchestrator construction" in text
    assert "no dispatcher, MCP, runtime, or proof authority wiring" in text


def test_playbook_records_verifier_adapter_substitution_fixture_baseline() -> None:
    text = _playbook_text()

    assert "Verifier adapter substitution fixture baseline" in text
    assert "tests/unit/test_adapter_port_substitution.py" in text
    assert "fake injected reviewers can be substituted without production wiring" in text
    assert "no proof authority writes" in text
    assert "no CTFVerifier construction" in text
    assert "no dispatcher, MCP, runtime, or crew wiring" in text


def test_playbook_records_adapter_substitution_source_guard_baseline() -> None:
    text = _playbook_text()

    assert "Adapter substitution source guard baseline" in text
    assert "tests/unit/test_adapter_substitution_source_guards.py" in text
    assert "substitution fixtures do not import concrete layers" in text
    assert "no side-effect sinks" in text
    assert "no proof authority write surfaces" in text
    assert "no production wiring" in text


def test_playbook_records_adapter_substitution_runway_completed() -> None:
    text = _playbook_text()

    assert "Adapter substitution runway completed" in text
    assert "tool runner and runtime action adapters" in text
    assert "state, read model, claim, and checkpoint store adapters" in text
    assert "audit and artifact store adapters" in text
    assert "crew bridge and task graph runner adapters" in text
    assert "verifier adapter" in text
    assert "substitution source guard" in text
    assert "next adapter work requires a short plan or explicit approval" in text
    assert "no production wiring has been approved by these fixtures" in text
