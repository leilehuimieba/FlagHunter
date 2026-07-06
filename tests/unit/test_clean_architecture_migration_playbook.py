"""Tests for the clean architecture migration playbook status ledger."""

from __future__ import annotations

import re
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


def _heading_section_text(text: str, heading: str) -> str:
    for level in ("####", "###"):
        marker = f"{level} {heading}"
        if marker not in text:
            continue
        start = text.index(marker)
        next_same_level = text.find(f"\n{level} ", start + len(marker))
        if next_same_level == -1:
            return text[start:]
        return text[start:next_same_level]
    raise AssertionError(f"missing heading: {heading}")


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


def _inline_code_values(value: str) -> list[str]:
    return re.findall(r"`([^`]+)`", value)


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
        "SubmitTaskIngress",
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


def test_playbook_records_candidate_a_neutral_metadata_projection_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral metadata projection baseline" in text
    assert "BuildChallengeBoardReadModel" in text
    assert "decisions" in text
    assert "candidates" in text
    assert "actionResults" in text
    assert "recommendedTask" in text
    assert "test_build_promotes_neutral_board_metadata_to_read_model_fields" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_metadata_alias_projection_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral metadata alias projection baseline" in text
    assert "activeDecision" in text
    assert "recommendedAction" in text
    assert "action_results" in text
    assert "attack_surfaces" in text
    assert "test_build_promotes_board_metadata_aliases_to_read_model_fields" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_candidate_enrichment_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral candidate enrichment baseline" in text
    assert "selected candidate" in text
    assert "recommended candidate" in text
    assert "test_task_board_projection_enriches_selected_and_recommended_candidates" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_candidate_ordering_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral candidate ordering baseline" in text
    assert "priority" in text
    assert "lastResult" in text
    assert "latest matching action result" in text
    assert "test_task_board_projection_orders_candidates_and_projects_last_result" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_candidate_marker_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral candidate marker baseline" in text
    assert "recommended=False" in text
    assert "ordered neutral candidates" in text
    assert "test_task_board_projection_adds_default_recommended_marker_for_ordered_candidates" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_hypothesis_alias_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral hypothesis summary alias baseline" in text
    assert "strongest_hypothesis_kind" in text
    assert "strongestHypothesisKind" in text
    assert "test_task_board_projection_accepts_hypothesis_summary_aliases" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_source_type_alias_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral source type alias baseline" in text
    assert "source_type" in text
    assert "sourceType" in text
    assert "test_task_board_projection_accepts_candidate_source_type_alias" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_trigger_reason_alias_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral trigger reason alias baseline" in text
    assert "trigger_reason" in text
    assert "triggerReason" in text
    assert "test_task_board_projection_accepts_action_result_trigger_reason_alias" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_trigger_driver_alias_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral trigger action driver alias baseline" in text
    assert "trigger_action_driver" in text
    assert "triggerActionDriver" in text
    assert "test_task_board_projection_accepts_action_result_trigger_driver_alias" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_trigger_time_alias_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral trigger time alias baseline" in text
    assert "trigger_at" in text
    assert "triggerAt" in text
    assert "test_task_board_projection_accepts_action_result_trigger_time_alias" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_trigger_result_alias_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral trigger result alias baseline" in text
    assert "trigger_result" in text
    assert "triggerResult" in text
    assert "test_task_board_projection_accepts_action_result_trigger_result_alias" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_expected_action_alias_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral expected action alias baseline" in text
    assert "expected_action" in text
    assert "expectedAction" in text
    assert "test_task_board_projection_accepts_action_result_expected_action_alias" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_observed_action_alias_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral observed action alias baseline" in text
    assert "observed_action" in text
    assert "observedAction" in text
    assert "test_task_board_projection_accepts_action_result_observed_action_alias" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_task_action_alias_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral task action alias baseline" in text
    assert "task_action" in text
    assert "taskAction" in text
    assert "test_task_board_projection_accepts_task_action_aliases" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_next_action_alias_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral next action alias baseline" in text
    assert "next_action" in text
    assert "nextAction" in text
    assert "test_task_board_projection_accepts_active_decision_next_action_alias" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_decision_driver_alias_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral decision driver alias baseline" in text
    assert "decision_driver" in text
    assert "driver" in text
    assert "test_task_board_projection_accepts_active_decision_driver_alias" in text
    assert "tests/unit/test_application_board_read_model_service.py" in text
    assert "no production path switch" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_candidate_a_neutral_decision_kind_alias_baseline() -> None:
    text = _playbook_text()

    assert "Candidate A neutral decision kind alias baseline" in text
    assert "decision_kind" in text
    assert "decisionKind" in text
    assert "test_task_board_projection_accepts_active_decision_kind_alias" in text
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
    assert "tests/unit/test_application_task_ingress_service.py" in text
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
    assert "Status: implementation landed." in section
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

    assert "Status: implementation landed." in section
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
        "neutral metadata projection baseline",
        "neutral metadata alias projection baseline",
        "neutral candidate enrichment baseline",
        "neutral candidate ordering baseline",
        "neutral candidate marker baseline",
        "neutral hypothesis summary alias baseline",
        "neutral source type alias baseline",
        "neutral trigger reason alias baseline",
        "neutral trigger action driver alias baseline",
        "neutral trigger time alias baseline",
        "neutral trigger result alias baseline",
        "neutral expected action alias baseline",
        "neutral observed action alias baseline",
        "neutral task action alias baseline",
        "neutral next action alias baseline",
        "neutral malformed board item projection baseline",
        "neutral recommended action projection baseline",
        "neutral explicit recommendation marker baseline",
        "neutral candidate/action-result degraded baseline",
        "neutral suppressed recommendation baseline",
    ):
        assert baseline in text
    for evidence_test in (
        "test_candidate_a_pre_approval_guard_blocks_neutral_builder_wiring",
        "test_build_promotes_neutral_board_metadata_to_read_model_fields",
        "test_build_promotes_board_metadata_aliases_to_read_model_fields",
        "test_task_board_projection_enriches_selected_and_recommended_candidates",
        "test_task_board_projection_orders_candidates_and_projects_last_result",
        "test_task_board_projection_adds_default_recommended_marker_for_ordered_candidates",
        "test_task_board_projection_accepts_hypothesis_summary_aliases",
        "test_task_board_projection_accepts_candidate_source_type_alias",
        "test_task_board_projection_accepts_action_result_trigger_reason_alias",
        "test_task_board_projection_accepts_action_result_trigger_driver_alias",
        "test_task_board_projection_accepts_action_result_trigger_time_alias",
        "test_task_board_projection_accepts_action_result_trigger_result_alias",
        "test_task_board_projection_accepts_action_result_expected_action_alias",
        "test_task_board_projection_accepts_action_result_observed_action_alias",
        "test_task_board_projection_accepts_task_action_aliases",
        "test_task_board_projection_accepts_active_decision_next_action_alias",
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


def test_playbook_parses_candidate_a_approval_request_crispness_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Candidate A approval request crispness guard")

    assert "Status: crispness guard recorded, implementation not approved by this section." in section
    assert "Candidate A implementation approval request" in section
    assert "explicit human approval" in section
    assert "no implementation approval by implication" in section

    rows = {
        row["Approval package field"]: row
        for row in _markdown_table_rows(section)
    }
    expected_fields = {
        "file list": (
            "`flaghunter/interface/blackboard_lite.py`, "
            "`tests/unit/interface/test_blackboard_lite.py`, "
            "`flaghunter/application/challenge/board_read_model_service.py` only if required"
        ),
        "risk": "medium; read-only Web task detail projection",
        "rollback point": "revert the single Candidate A implementation commit",
        "equivalence tests": "`tests/unit/interface/test_blackboard_lite.py` representative and degraded fixtures",
        "non-goals": "dispatcher, state ownership, verifier, ToolExecutor, crew, MCP wiring, composition root, adapters, proof authority, P5",
        "focused commands": "blackboard focused, application projection focused, architecture/source guards, `git diff --check`",
    }

    assert rows.keys() == expected_fields.keys()
    for field, expected_detail in expected_fields.items():
        row = rows[field]
        assert row["Required detail"] == expected_detail
        assert row["Present in request"] == "true"


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
    assert (
        "after explicit Candidate C serialize-task approval is granted"
        in text.replace("\n", " ")
    )
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
    assert "Status: ready for serialize-task approval review, not approved for implementation." in text
    assert "Candidate C serialize-task and control-decision have landed" in text
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
    assert "Status: implementation landed for Deferred MCP readback." in text
    assert "Deferred MCP readback approval plan" in text
    assert "Deferred MCP source guard baseline" in text
    assert "Deferred MCP pre-approval production wiring guard" in section
    assert "test_deferred_mcp_readback_uses_neutral_projection_after_approval" in text
    assert "Deferred MCP readback formatting fixture baseline" in text
    assert "Deferred MCP empty/malformed readback fixture baseline" in text
    assert "flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines" in text
    assert "tests/unit/mcp/test_mcp_ingress_mode_contract.py" in text
    assert "Web read-model projection equivalence is proven" in text
    assert "explicit MCP production wiring approval was granted" in text
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

    assert "Status: implementation landed." in section
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
    assert "Candidates A, B, C serialize-task, C control-decision, and Deferred MCP readback have landed" in text.replace("\n", " ")
    assert "Candidate B may not be implemented before Candidate A lands" in text
    assert "Candidate C serialize-task may not be implemented before Candidate B lands" in text
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
    assert "Candidate A | implementation landed |" in text
    assert "Candidate B | implementation landed |" in text
    assert "Candidate C | implementation landed |" in text
    assert "Deferred MCP | implementation landed |" in text
    assert "blackboard_lite.py" in text
    assert "web_trace_timeline.py" in text
    assert "web_serialize_task.py and web_control_decision.py" in text
    assert "mcp_tools.py" in text
    assert "complete" in text
    assert "Web projection equivalence" in text
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
        "Candidate A: implementation landed",
        "Candidate B: implementation landed",
        "Candidate C: implementation landed",
        "Deferred MCP: implementation landed",
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
        "Candidate A | implementation landed",
        "Candidate B | implementation landed",
        "Candidate C | implementation landed",
        "Deferred MCP | implementation landed",
    ):
        assert candidate_status in text
    for required_phrase in (
        "evidence present",
        "remaining blocker",
        "implementation landed",
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
        "Candidate A": "implementation landed",
        "Candidate B": "implementation landed",
        "Candidate C": "implementation landed",
        "Deferred MCP": "implementation landed",
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


def test_playbook_parses_approval_transition_atomicity_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path approval transition atomicity guard")

    assert "Status: approval transition atomicity guard recorded, no implementation approved by this section." in section
    for required_phrase in (
        "same governance commit before implementation starts",
        "acceptance matrix row",
        "approval drift fact",
        "candidate status ledger",
        "readiness report",
        "source-map approval flag",
        "approved execution checklist",
        "verification evidence",
        "no production path switch",
    ):
        assert required_phrase in section


def test_playbook_parses_approval_transition_atomicity_location_map() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path approval transition atomicity guard")

    rows = {
        row["Atomic update"]: row["Required section"].strip("`")
        for row in _markdown_table_rows(section)
    }
    expected_sections = {
        "acceptance matrix row": "Read-path switch acceptance matrix",
        "approval drift fact": "Read-path approval drift guard",
        "candidate status ledger": "Read-path candidate status ledger",
        "readiness report": "Read-path implementation approval readiness report",
        "source-map approval flag": "Read-path pre-approval source-map guard",
        "approved execution checklist": "Read-path approved execution checklist index",
        "verification evidence": "Read-path implementation landing record template",
    }

    assert rows == expected_sections
    for heading in expected_sections.values():
        assert _section_text(text, heading)


def test_playbook_parses_approval_transition_candidate_coverage_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path approval transition candidate coverage guard")

    assert "Status: candidate coverage guard recorded, no implementation approved by this section." in section
    assert "Candidate C split source-map rows collapse to the canonical Candidate C approval state" in section
    assert "no production path switch" in section

    expected_candidates = {"Candidate A", "Candidate B", "Candidate C", "Deferred MCP"}
    coverage_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(section)
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
    ledger_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path candidate status ledger")
        )
    }
    readiness_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path implementation approval readiness report")
        )
    }
    checklist_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path approved execution checklist index")
        )
    }
    evidence_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path implementation landed evidence guard")
        )
    }
    source_candidates = {
        row["Candidate"].replace(" serialize-task", "").replace(" control-decision", "")
        for row in _markdown_table_rows(
            _section_text(text, "Read-path pre-approval source-map guard")
        )
    }

    assert set(coverage_rows) == expected_candidates
    assert set(acceptance_rows) == expected_candidates
    assert set(package_rows) == expected_candidates
    assert set(ledger_rows) == expected_candidates
    assert set(readiness_rows) == expected_candidates
    assert set(checklist_rows) == expected_candidates
    assert set(evidence_rows) == expected_candidates
    assert source_candidates == expected_candidates
    for candidate, row in coverage_rows.items():
        expected_flag = "true"
        assert row["Current implementation approval"] == expected_flag
        assert row["Required coverage"] == "acceptance, drift, package, ledger, readiness, source-map, checklist, landing evidence"
        assert ledger_rows[candidate]["approvedForImplementation"] == expected_flag
        assert readiness_rows[candidate]["Implementation approved"] == expected_flag
        assert evidence_rows[candidate]["Implementation landed"] == expected_flag


def test_playbook_parses_read_path_approval_transition_evidence_consistency_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path approval transition evidence consistency guard")

    assert "Status: approval transition evidence consistency guard recorded, no implementation approved." in section
    assert "approval evidence must be present before implementation approval changes" in section
    assert "no production path switch is authorized by this evidence guard" in section

    rows = {
        row["Evidence item"]: row
        for row in _markdown_table_rows(section)
    }
    assert rows == {
        "acceptance matrix update": {
            "Evidence item": "acceptance matrix update",
            "Required location": "`Read-path switch acceptance matrix`",
            "Current approval evidence present": "false",
        },
        "approval drift update": {
            "Evidence item": "approval drift update",
            "Required location": "`Read-path approval drift guard`",
            "Current approval evidence present": "false",
        },
        "candidate status ledger update": {
            "Evidence item": "candidate status ledger update",
            "Required location": "`Read-path candidate status ledger`",
            "Current approval evidence present": "false",
        },
        "readiness evidence update": {
            "Evidence item": "readiness evidence update",
            "Required location": "`Read-path implementation approval readiness report`",
            "Current approval evidence present": "false",
        },
        "source-map approval update": {
            "Evidence item": "source-map approval update",
            "Required location": "`Read-path pre-approval source-map guard`",
            "Current approval evidence present": "false",
        },
        "approved execution checklist update": {
            "Evidence item": "approved execution checklist update",
            "Required location": "`Read-path approved execution checklist index`",
            "Current approval evidence present": "false",
        },
        "landing record placeholder": {
            "Evidence item": "landing record placeholder",
            "Required location": "`Read-path implementation landing record template`",
            "Current approval evidence present": "false",
        },
    }

    atomicity_rows = {
        row["Atomic update"]: row["Required section"]
        for row in _markdown_table_rows(
            _section_text(text, "Read-path approval transition atomicity guard")
        )
    }
    for row in rows.values():
        assert row["Required location"] in atomicity_rows.values()
        assert row["Current approval evidence present"] == "false"


def test_playbook_records_machine_readable_read_path_candidate_status_ledger() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path candidate status ledger")

    assert "Status: machine-readable status ledger recorded, Web read paths and Deferred MCP readback landed." in section
    expected_rows = (
        "| Candidate A | implementation landed | true | complete |",
        "| Candidate B | implementation landed | true | complete |",
        "| Candidate C | implementation landed | true | complete |",
        "| Deferred MCP | implementation landed | true | complete |",
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
        assert ledger_row["canonicalStatus"] == acceptance_rows[candidate]["Status"]
        assert ledger_row["canonicalStatus"] == package_rows[candidate]["Current status"]
    assert ledger_rows["Candidate A"]["approvedForImplementation"] == "true"
    assert ledger_rows["Candidate B"]["approvedForImplementation"] == "true"
    for candidate in ("Candidate C", "Deferred MCP"):
        assert ledger_rows[candidate]["approvedForImplementation"] == "true"


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


def test_playbook_parses_deferred_mcp_explicit_wiring_approval_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Deferred MCP explicit wiring approval guard")

    assert "Status: explicit MCP approval guard recorded, Deferred MCP readback implementation landed." in section
    assert "Web projection equivalence lands plus explicit MCP production wiring approval" in section
    assert "confirm explicit MCP production wiring approval" in section
    assert "no MCP production wiring without explicit approval" in section
    assert "no task execution path switch" in section

    expected_gate = "complete"
    ledger_row = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path candidate status ledger")
        )
    }["Deferred MCP"]
    readiness_row = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path implementation approval readiness report")
        )
    }["Deferred MCP"]
    package_row = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path approval package summary")
        )
    }["Deferred MCP"]
    source_row = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path pre-approval source-map guard")
        )
    }["Deferred MCP"]
    evidence_row = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path implementation landed evidence guard")
        )
    }["Deferred MCP"]
    rollback_row = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path rollback command index")
        )
    }["Deferred MCP"]
    checklist = _section_text(text, "Deferred MCP approved execution checklist")

    assert ledger_row["nextGate"] == expected_gate
    assert readiness_row["Missing approval"] == expected_gate
    assert package_row["remaining blocker"] == expected_gate
    assert ledger_row["canonicalStatus"] == "implementation landed"
    assert readiness_row["Implementation approved"] == "true"
    assert source_row["Source path"] == "`flaghunter/mcp/server/mcp_tools.py`"
    assert source_row["Implementation approved"] == "true"
    assert evidence_row["Implementation landed"] == "true"
    assert rollback_row["Rollback command"] == "`git revert <single Deferred MCP implementation commit>`"
    assert "confirm explicit MCP production wiring approval" in checklist
    assert "no MCP production wiring without explicit approval" in text


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
        if candidate in {"Candidate B", "Deferred MCP"}:
            assert row["Checklist status"] == "implementation landed"
            assert row["Approval state"] == "implementation landed"
            assert "Status: implementation landed." in checklist_section
        else:
            assert row["Checklist status"] == "not approved; checklist only"
            assert row["Approval state"] == "implementation not approved"
            assert "Status: not approved; checklist only." in checklist_section


def test_playbook_parses_read_path_implementation_approval_readiness_report() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path implementation approval readiness report")

    assert "Status: readiness report recorded, Web read paths and Deferred MCP readback landed." in section
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
        "Candidate A": "landed; output equivalence preserved",
        "Candidate B": "landed; output equivalence preserved",
        "Candidate C": "landed; output equivalence preserved",
        "Deferred MCP": "landed; output equivalence preserved",
    }
    assert set(readiness_rows) == set(ledger_rows) == set(package_rows)
    for candidate, expected_state in expected_readiness.items():
        row = readiness_rows[candidate]
        assert row["Readiness state"] == expected_state
        assert row["Current status"] == ledger_rows[candidate]["canonicalStatus"]
        assert row["Missing approval"] == package_rows[candidate]["remaining blocker"]
        expected_flag = "true"
        assert row["Implementation approved"] == expected_flag


def test_playbook_parses_pre_approval_source_map_and_blocks_wiring() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path pre-approval source-map guard")

    assert "Status: Web read paths A, B, C1, C2, and Deferred MCP readback implementation landed." in section
    source_rows = _markdown_table_rows(section)
    expected_paths = {
        "flaghunter/interface/blackboard_lite.py",
        "flaghunter/interface/web_trace_timeline.py",
        "flaghunter/interface/web_serialize_task.py",
        "flaghunter/interface/web_control_decision.py",
        "flaghunter/mcp/server/mcp_tools.py",
    }
    expected_tokens = {
        "flaghunter.application.challenge",
        "flaghunter.domain.challenge.contracts",
        "build_task_board_projection",
        "BuildChallengeBoardReadModel",
        "ChallengeBoardReadModel",
    }

    assert {row["Source path"].strip("`") for row in source_rows} == expected_paths
    for row in source_rows:
        forbidden_tokens = _inline_code_values(row["Forbidden neutral wiring"])
        assert set(forbidden_tokens) == expected_tokens
        source_path = REPO_ROOT / row["Source path"].strip("`")
        source_text = source_path.read_text(encoding="utf-8")
        if row["Candidate"] in {
            "Candidate A",
            "Candidate B",
            "Candidate C serialize-task",
            "Candidate C control-decision",
            "Deferred MCP",
        }:
            assert row["Implementation approved"] == "true"
            assert any(token in source_text for token in forbidden_tokens)
        else:
            assert row["Implementation approved"] == "false"
            for token in forbidden_tokens:
                assert token not in source_text


def test_playbook_records_source_map_forbidden_token_single_source_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path source-map forbidden-token single-source guard")

    assert "Status: forbidden-token parser guard recorded, no implementation approved by this section." in section
    assert "Forbidden neutral wiring" in section
    assert "single source of truth" in section
    assert "no hardcoded duplicate token tuple" in section
    assert "no production path switch" in section


def test_playbook_parses_approval_package_source_map_consistency_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path approval package source-map consistency guard")

    assert "Status: approval package source-map consistency guard recorded, no implementation approved by this section." in section
    assert "evidence present" in section
    assert "source guard" in section
    assert "pre-approval guard" in section
    assert "source-map coverage" in section
    assert "no production path switch" in section

    package_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path approval package summary")
        )
    }
    source_rows = _markdown_table_rows(
        _section_text(text, "Read-path pre-approval source-map guard")
    )
    source_paths_by_candidate: dict[str, set[str]] = {}
    for row in source_rows:
        candidate = row["Candidate"].replace(" serialize-task", "").replace(" control-decision", "")
        source_paths_by_candidate.setdefault(candidate, set()).add(row["Source path"].strip("`"))

    assert set(package_rows) == set(source_paths_by_candidate)
    for candidate, package_row in package_rows.items():
        evidence = package_row["evidence present"]
        assert "source guard" in evidence
        assert "pre-approval guard" in evidence
        target_paths = {
            target.split("::", 1)[0]
            for target in _inline_code_values(package_row["Target"])
        }
        assert target_paths == source_paths_by_candidate[candidate]


def test_playbook_parses_read_path_approval_package_evidence_completeness_guard() -> None:
    text = _playbook_text()
    section = _section_text(
        text,
        "Read-path approval package evidence completeness guard",
    )

    assert "Status: evidence completeness guard recorded, no implementation approved by this section." in section
    assert "approval package readiness evidence is not implementation approval evidence" in section
    assert "no production path switch is authorized by this evidence completeness guard" in section

    rows = {
        row["Evidence group"]: row
        for row in _markdown_table_rows(section)
    }
    assert rows == {
        "candidate status ledger": {
            "Evidence group": "candidate status ledger",
            "Required section": "`Read-path candidate status ledger`",
            "Current complete": "true",
        },
        "readiness report": {
            "Evidence group": "readiness report",
            "Required section": "`Read-path implementation approval readiness report`",
            "Current complete": "true",
        },
        "source-map coverage": {
            "Evidence group": "source-map coverage",
            "Required section": "`Read-path approval package source-map consistency guard`",
            "Current complete": "true",
        },
        "approval transition evidence": {
            "Evidence group": "approval transition evidence",
            "Required section": "`Read-path approval transition evidence consistency guard`",
            "Current complete": "false",
        },
        "landing evidence": {
            "Evidence group": "landing evidence",
            "Required section": "`Read-path implementation landed evidence guard`",
            "Current complete": "false",
        },
    }

    package_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path approval package summary")
        )
    }
    assert set(package_rows) == {"Candidate A", "Candidate B", "Candidate C", "Deferred MCP"}
    for row in package_rows.values():
        assert "source guard" in row["evidence present"]
        assert "pre-approval guard" in row["evidence present"]
        assert row["remaining blocker"]

    for row in rows.values():
        assert _section_text(text, row["Required section"].strip("`"))
    assert rows["approval transition evidence"]["Current complete"] == "false"
    assert rows["landing evidence"]["Current complete"] == "false"


def test_playbook_parses_implementation_landed_evidence_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path implementation landed evidence guard")

    assert "Status: landed evidence guard recorded, Web read paths and Deferred MCP readback landed." in section
    evidence_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(section)
    }
    ledger_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path candidate status ledger")
        )
    }
    readiness_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path implementation approval readiness report")
        )
    }

    assert set(evidence_rows) == set(ledger_rows) == set(readiness_rows)
    for candidate, row in evidence_rows.items():
        if candidate in {"Candidate A", "Candidate B", "Candidate C", "Deferred MCP"}:
            assert row["Implementation landed"] == "true"
            if candidate == "Candidate C":
                assert row["Landing evidence"] == "Candidate C1 and Candidate C2 implementation landing records"
                assert row["Required before landed"] == "landing records, implementation commits, regression results"
            else:
                assert row["Landing evidence"] == f"{candidate} implementation landing record"
                assert row["Required before landed"] == "landing record, implementation commit, regression results"
            assert ledger_rows[candidate]["canonicalStatus"] == "implementation landed"
            assert readiness_rows[candidate]["Implementation approved"] == "true"

def test_playbook_parses_read_path_approval_flag_aggregate_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path approval flag aggregate guard")

    assert "Status: aggregate approval flag guard recorded, Web read paths and Deferred MCP readback landed." in section
    assert "ledger `approvedForImplementation`" in section
    assert "readiness report `Implementation approved`" in section
    assert "source-map `Implementation approved`" in section
    assert "landed evidence `Implementation landed`" in section

    ledger_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path candidate status ledger")
        )
    }
    readiness_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path implementation approval readiness report")
        )
    }
    source_rows = _markdown_table_rows(
        _section_text(text, "Read-path pre-approval source-map guard")
    )
    evidence_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path implementation landed evidence guard")
        )
    }

    source_candidates = {
        row["Candidate"].replace(" serialize-task", "").replace(" control-decision", "")
        for row in source_rows
    }
    assert set(ledger_rows) == set(readiness_rows) == set(evidence_rows)
    assert source_candidates == set(ledger_rows)
    for candidate, ledger_row in ledger_rows.items():
        expected_flag = "true"
        assert ledger_row["approvedForImplementation"] == expected_flag
        assert readiness_rows[candidate]["Implementation approved"] == ledger_row["approvedForImplementation"]
        assert evidence_rows[candidate]["Implementation landed"] == expected_flag
    for row in source_rows:
        expected_flag = (
            "true"
            if row["Candidate"] in {
                "Candidate A",
                "Candidate B",
                "Candidate C serialize-task",
                "Candidate C control-decision",
                "Deferred MCP",
            }
            else "false"
        )
        assert row["Implementation approved"] == expected_flag


def test_playbook_parses_read_path_rollback_command_index() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path rollback command index")

    assert "Status: rollback command index recorded, Web read paths and Deferred MCP readback landed." in section
    assert "placeholder only" in section
    assert "not a currently executable rollback command" in section

    rollback_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(section)
    }
    evidence_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path implementation landed evidence guard")
        )
    }
    expected_commands = {
        "Candidate A": "git revert <Candidate A implementation commit>",
        "Candidate B": "git revert <Candidate B implementation commit>",
        "Candidate C serialize-task": "git revert <single Candidate C serialize-task implementation commit>",
        "Candidate C control-decision": "git revert <single Candidate C control-decision implementation commit>",
        "Deferred MCP": "git revert <single Deferred MCP implementation commit>",
    }

    collapsed_candidates = {
        candidate.replace(" serialize-task", "").replace(" control-decision", "")
        for candidate in rollback_rows
    }
    assert collapsed_candidates == set(evidence_rows)
    assert rollback_rows.keys() == expected_commands.keys()
    for candidate, expected_command in expected_commands.items():
        row = rollback_rows[candidate]
        assert row["Rollback command"] == f"`{expected_command}`"
        assert row["Current executable"] == "false"
        if candidate in {"Candidate A", "Candidate B"}:
            assert row["Applies after"] == f"{candidate} implementation commit lands"
        else:
            assert row["Applies after"] == "candidate implementation commit lands"
        assert not re.search(r"\b[0-9a-f]{7,40}\b", row["Rollback command"])


def test_playbook_parses_landing_rollback_consistency_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path landing rollback consistency guard")

    assert "Status: landing rollback consistency guard recorded, no implementation approved by this section." in section
    assert "Rollback command: git revert <sha>" in section
    assert "placeholder rollback commands remain non-executable" in section
    assert "real implementation commit SHA" in section
    assert "no production path switch" in section

    landing_template = _section_text(text, "Read-path implementation landing record template")
    rollback_rows = _markdown_table_rows(
        _section_text(text, "Read-path rollback command index")
    )
    evidence_rows = _markdown_table_rows(
        _section_text(text, "Read-path implementation landed evidence guard")
    )

    assert "Rollback command: git revert <sha>" in landing_template
    for row in rollback_rows:
        assert row["Current executable"] == "false"
        if row["Candidate"] in {"Candidate A", "Candidate B"}:
            assert f"<{row['Candidate']} implementation commit>" in row["Rollback command"]
        else:
            assert "<single " in row["Rollback command"]
        assert not re.search(r"\b[0-9a-f]{7,40}\b", row["Rollback command"])
    for row in evidence_rows:
        if row["Candidate"] in {"Candidate A", "Candidate B", "Candidate C", "Deferred MCP"}:
            assert row["Implementation landed"] == "true"
            if row["Candidate"] == "Candidate C":
                assert row["Landing evidence"] == "Candidate C1 and Candidate C2 implementation landing records"
            else:
                assert row["Landing evidence"] == f"{row['Candidate']} implementation landing record"
        if row["Candidate"] == "Candidate A":
            assert "implementation commit" in row["Required before landed"]


def test_playbook_parses_read_path_implementation_landing_status_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path implementation landing status guard")

    assert "Status: landing status guard recorded, Web read paths and Deferred MCP readback landed." in section
    assert "no production path switch is authorized by this landing status guard" in section

    rows = {
        row["Landing surface"]: row
        for row in _markdown_table_rows(section)
    }
    assert rows == {
        "landed evidence rows": {
            "Landing surface": "landed evidence rows",
            "Required location": "`Read-path implementation landed evidence guard`",
            "Current landed": "true",
        },
        "rollback index": {
            "Landing surface": "rollback index",
            "Required location": "`Read-path rollback command index`",
            "Current landed": "false",
        },
        "landing record template": {
            "Landing surface": "landing record template",
            "Required location": "`Read-path implementation landing record template`",
            "Current landed": "true",
        },
    }

    evidence_rows = _markdown_table_rows(
        _section_text(text, "Read-path implementation landed evidence guard")
    )
    rollback_rows = _markdown_table_rows(
        _section_text(text, "Read-path rollback command index")
    )
    landing_template = _section_text(text, "Read-path implementation landing record template")

    for row in evidence_rows:
        assert row["Implementation landed"] == "true"
        if row["Candidate"] == "Candidate C":
            assert row["Landing evidence"] == "Candidate C1 and Candidate C2 implementation landing records"
        else:
            assert row["Landing evidence"] == f"{row['Candidate']} implementation landing record"
    for row in rollback_rows:
        assert row["Current executable"] == "false"
    assert "Status: landing evidence template recorded, no implementation approved by this" in landing_template
    assert "section." in landing_template


def test_playbook_parses_read_path_readiness_to_landing_transition_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path readiness-to-landing transition guard")

    assert "Status: readiness-to-landing guard recorded, Web read paths and Deferred MCP readback landed." in section
    assert "readiness complete alone must not unlock landing" in section.lower()
    assert "no production path switch is authorized by this readiness-to-landing guard" in section

    rows = {
        row["Transition checkpoint"]: row
        for row in _markdown_table_rows(section)
    }
    assert rows == {
        "readiness indexes complete": {
            "Transition checkpoint": "readiness indexes complete",
            "Required section": "`Read-path approval package evidence completeness guard`",
            "Current satisfied": "true",
        },
        "approval transition evidence complete": {
            "Transition checkpoint": "approval transition evidence complete",
            "Required section": "`Read-path approval package evidence completeness guard`",
            "Current satisfied": "false",
        },
        "implementation approval flags raised": {
            "Transition checkpoint": "implementation approval flags raised",
            "Required section": "`Read-path approval flag aggregate guard`",
            "Current satisfied": "true",
        },
        "landing evidence recorded": {
            "Transition checkpoint": "landing evidence recorded",
            "Required section": "`Read-path implementation landed evidence guard`",
            "Current satisfied": "true",
        },
        "rollback commands executable": {
            "Transition checkpoint": "rollback commands executable",
            "Required section": "`Read-path rollback command index`",
            "Current satisfied": "false",
        },
        "landing status raised": {
            "Transition checkpoint": "landing status raised",
            "Required section": "`Read-path implementation landing status guard`",
            "Current satisfied": "true",
        },
    }

    completeness_rows = {
        row["Evidence group"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path approval package evidence completeness guard")
        )
    }
    assert completeness_rows["candidate status ledger"]["Current complete"] == "true"
    assert completeness_rows["readiness report"]["Current complete"] == "true"
    assert completeness_rows["source-map coverage"]["Current complete"] == "true"
    assert completeness_rows["approval transition evidence"]["Current complete"] == "false"
    assert completeness_rows["landing evidence"]["Current complete"] == "false"

    for row in _markdown_table_rows(
        _section_text(text, "Read-path implementation landed evidence guard")
    ):
        assert row["Implementation landed"] == "true"
        if row["Candidate"] == "Candidate C":
            assert row["Landing evidence"] == "Candidate C1 and Candidate C2 implementation landing records"
        else:
            assert row["Landing evidence"] == f"{row['Candidate']} implementation landing record"
    for row in _markdown_table_rows(_section_text(text, "Read-path rollback command index")):
        assert row["Current executable"] == "false"
    for row in _markdown_table_rows(
        _section_text(text, "Read-path implementation landing status guard")
    ):
        expected_landed = "false" if row["Landing surface"] == "rollback index" else "true"
        assert row["Current landed"] == expected_landed


def test_playbook_parses_candidate_c_split_commit_consistency_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Candidate C split commit consistency guard")

    assert "Status: split commit consistency guard recorded, no implementation approved by this section." in section
    assert "two separate read-path switch commits" in section
    assert "serialize-task projection first" in section
    assert "control-decision snapshot merge second" in section
    assert "no bundled serialize-task and control-decision implementation" in section
    assert "no production path switch" in section

    source_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path pre-approval source-map guard")
        )
        if row["Candidate"].startswith("Candidate C")
    }
    rollback_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(
            _section_text(text, "Read-path rollback command index")
        )
        if row["Candidate"].startswith("Candidate C")
    }
    checklist = _section_text(text, "Candidate C approved execution checklist")

    assert set(source_rows) == {"Candidate C serialize-task", "Candidate C control-decision"}
    assert set(rollback_rows) == set(source_rows)
    assert source_rows["Candidate C serialize-task"]["Source path"] == "`flaghunter/interface/web_serialize_task.py`"
    assert source_rows["Candidate C control-decision"]["Source path"] == "`flaghunter/interface/web_control_decision.py`"
    assert rollback_rows["Candidate C serialize-task"]["Rollback command"] == "`git revert <single Candidate C serialize-task implementation commit>`"
    assert rollback_rows["Candidate C control-decision"]["Rollback command"] == "`git revert <single Candidate C control-decision implementation commit>`"
    for required_phrase in (
        "two separate",
        "one call-site family per commit",
        "serialize-task projection first",
        "control-decision snapshot merge second",
        "no bundled serialize-task and control-decision implementation",
    ):
        assert required_phrase in checklist


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


def test_playbook_records_task_ingress_adapter_skeleton_baseline() -> None:
    text = _playbook_text()

    assert "Task ingress adapter skeleton baseline" in text
    assert "TaskIngressPort" in text
    assert "TaskIngressAdapter" in text
    assert "tests/unit/test_task_ingress_adapter.py" in text
    assert "tests/unit/test_adapter_port_substitution.py" in text
    assert "delegates to injected task ingress ports" in text
    assert "no MCP production wiring" in text
    assert "no `flaghunter/mcp/server` imports" in text
    assert "no dispatcher loop changes" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_task_ingress_application_service_baseline() -> None:
    text = _playbook_text()

    assert "Task ingress application service skeleton baseline" in text
    assert "SubmitTaskIngress" in text
    assert "TaskIngressPort" in text
    assert "tests/unit/test_application_task_ingress_service.py" in text
    assert "depends only on neutral contracts and ports" in text
    assert "no MCP production wiring" in text
    assert "no concrete adapter construction" in text
    assert "no dispatcher loop changes" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_task_ingress_domain_contract_baseline() -> None:
    text = _playbook_text()

    assert "Task ingress domain contract skeleton baseline" in text
    assert "TaskIngressRequest" in text
    assert "TaskIngressReceipt" in text
    assert "flaghunter/domain/challenge/contracts/task_ingress.py" in text
    assert "tests/unit/test_domain_challenge_contracts.py" in text
    assert "schema-versioned and JSON-friendly" in text
    assert "sanitized instructions and receipt summaries" in text
    assert "no service migration" in text
    assert "no MCP production wiring" in text
    assert "no concrete adapter construction" in text
    assert "no dispatcher loop changes" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_task_ingress_readback_contract_baseline() -> None:
    text = _playbook_text()

    assert "Task ingress readback contract skeleton baseline" in text
    assert "TaskIngressReadback" in text
    assert "request and receipt summary counts" in text
    assert "task type and status counts" in text
    assert "flaghunter/domain/challenge/contracts/task_ingress.py" in text
    assert "tests/unit/test_domain_challenge_contracts.py" in text
    assert "no service migration" in text
    assert "no MCP production wiring" in text
    assert "no concrete adapter construction" in text
    assert "no dispatcher loop changes" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_task_ingress_mcp_pre_wiring_guard_baseline() -> None:
    text = _playbook_text()

    assert "Task ingress MCP pre-wiring guard baseline" in text
    assert "tests/unit/mcp/test_mcp_ingress_mode_contract.py" in text
    assert "TaskIngressAdapter" in text
    assert "SubmitTaskIngress" in text
    assert "TaskIngressPort" in text
    assert "no MCP production wiring" in text
    assert "explicit production wiring approval" in text
    assert "no dispatcher loop changes" in text
    assert "no composition root changes" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_task_ingress_production_entrypoint_guard_baseline() -> None:
    text = _playbook_text()

    assert "Task ingress production entrypoint pre-wiring guard baseline" in text
    assert "tests/unit/test_task_ingress_production_wiring_guards.py" in text
    assert "interface, MCP, agents, tools, runtime, session, workspaces, and config" in text
    assert "flaghunter/mcp/server" in text
    assert "TaskIngressAdapter" in text
    assert "SubmitTaskIngress" in text
    assert "TaskIngressPort" in text
    assert "explicit production wiring approval" in text
    assert "no production entrypoint wiring" in text
    assert "no dispatcher loop changes" in text
    assert "no ToolExecutor changes" in text
    assert "no composition root changes" in text
    assert "no proof authority behavior changes" in text


def test_playbook_records_task_ingress_service_contract_migration_plan() -> None:
    text = _playbook_text()

    assert "Task ingress service contract migration plan" in text
    assert "Status: implementation approved and landed." in text
    for file_path in (
        "flaghunter/application/challenge/task_ingress_service.py",
        "tests/unit/test_application_task_ingress_service.py",
        "tests/unit/test_application_service_source_guards.py",
        "tests/unit/test_task_ingress_adapter.py",
        "tests/unit/test_clean_architecture_migration_playbook.py",
    ):
        assert file_path in text
    assert "risk: low-medium" in text
    assert "service output shape and ingress port payload compatibility could change" in text
    assert "rollback point: revert the single service migration commit" in text
    assert "preserve current external response shape unless explicitly versioned" in text
    assert "preserve raw `instructions` in the port request if downstream compatibility still expects it" in text
    assert "no production wiring" in text
    assert "no MCP server changes" in text
    assert "no dispatcher loop changes" in text
    assert "no ToolExecutor changes" in text
    assert "no composition root changes" in text
    assert "no proof authority behavior changes" in text
    assert "no P5 implementation" in text
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_application_task_ingress_service.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_task_ingress_adapter.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_task_ingress_production_wiring_guards.py -q",
        "git diff --check",
    ):
        assert command in text


def test_playbook_records_task_ingress_service_migration_readiness_checklist() -> None:
    text = _playbook_text()

    assert "Task ingress service contract migration readiness checklist" in text
    assert "Status: implementation landed after explicit approval." in text
    for baseline in (
        "Task ingress application service skeleton baseline",
        "Task ingress domain contract skeleton baseline",
        "Task ingress readback contract skeleton baseline",
        "Task ingress service contract migration plan",
        "Task ingress service contract migration pre-approval guard retired by landing",
    ):
        assert baseline in text
    for evidence_test in (
        "test_submit_returns_pending_payload_without_ingress_port",
        "test_submit_delegates_to_task_ingress_port_only",
        "test_submit_accepts_minimal_empty_values",
        "test_task_ingress_service_contract_migration_landing_guard",
    ):
        assert evidence_test in text
    assert "explicit approval was granted before editing `flaghunter/application/challenge/task_ingress_service.py`" in text
    assert "one service migration commit only" in text
    assert "preserve current external response shape unless explicitly versioned" in text
    assert "preserve raw `instructions` in the injected port request payload" in text
    assert "old/new output equivalence must be proven in `tests/unit/test_application_task_ingress_service.py`" in text
    assert "rollback point: revert the single service migration commit" in text
    for non_goal in (
        "no production wiring",
        "no MCP server changes",
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
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_application_task_ingress_service.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_task_ingress_adapter.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_application_service_source_guards.py tests/unit/test_task_ingress_production_wiring_guards.py -q",
        "git diff --check",
    ):
        assert command in text


def test_playbook_records_post_read_side_core_decoupling_approval_queue() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Post read-side core decoupling approval queue",
    )

    assert "Status: approval queue recorded, implementation not approved by this section." in section
    assert "Web read paths and Deferred MCP readback are landed" in section
    assert "Task ingress service contract migration" in section
    assert "ToolExecutor side-effect split" in section
    assert "Verifier/proof authority boundary" in section
    assert "State ownership split" in section
    assert "Dispatcher/composition root production wiring" in section
    assert "one functional point per commit" in section
    assert "no bundled core edits" in section
    assert "no approval by implication" in section

    queue_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(section.split("Queue rules:", 1)[0])
    }
    assert list(queue_rows) == [
        "Task ingress service contract migration",
        "Task ingress production wiring",
        "Verifier/proof authority boundary",
        "State ownership split",
        "ToolExecutor side-effect split",
        "Dispatcher/composition root production wiring",
    ]
    assert queue_rows["Task ingress service contract migration"]["Risk tier"] == "low-medium"
    assert queue_rows["Task ingress service contract migration"]["Current status"] == "implementation landed"
    assert queue_rows["Task ingress service contract migration"]["Implementation approved"] == "true"
    assert queue_rows["Task ingress production wiring"]["Current status"] == "A and B landed; remaining entrypoints not approved"
    assert queue_rows["Task ingress production wiring"]["Implementation approved"] == "partial"
    for candidate, row in queue_rows.items():
        if candidate not in {
            "Task ingress service contract migration",
            "Task ingress production wiring",
        }:
            assert row["Implementation approved"] == "false"
        assert row["Required approval"]
        assert row["Required verification"]
        if candidate != "Task ingress service contract migration":
            assert row["Risk tier"] in {"high", "maximum"}

    for forbidden_scope in (
        "no MCP task execution wiring without explicit production wiring approval",
        "no ToolExecutor changes without ToolExecutor-specific approval",
        "no Verifier/proof authority behavior changes without proof-authority approval",
        "no CTFState ownership split without state-specific approval",
        "no CTFTaskDispatcher flow changes without dispatcher-specific approval",
        "no composition root changes without composition-root approval",
        "no P5 implementation",
    ):
        assert forbidden_scope in section


def test_playbook_records_verifier_proof_authority_approval_plan() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Verifier/proof authority boundary approval plan",
    )

    assert "Status: approval plan recorded, implementation not approved." in section
    assert "flaghunter/agents/pa_agent/verifier.py" in section
    assert "flaghunter/agents/pa_agent/ctf_state.py" in section
    assert "tests/unit/agents/test_p1_claim_invariants.py" in section
    assert "tests/unit/test_verifier_adapter.py" in section
    assert "proof-authority writes stay in verifier-owned code until explicitly migrated" in section
    assert "rollback point: revert the single approved proof-authority implementation commit" in section
    assert "explicit proof-authority approval required before implementation" in section
    assert "Proof authority characterization readiness aggregate" in section
    assert "readiness aggregate is approval package evidence, not implementation approval" in section
    for readiness_guard in (
        "Proof authority write surface characterization guard",
        "Verified decision reference characterization guard",
        "Proof authority port action unwired guard",
        "Proof authority adapter import unwired guard",
        "Verifier adapter import unwired guard",
    ):
        assert readiness_guard in section
    for required_surface in (
        "upgrade_claim_to_verified",
        "append_verification_record",
        "record_verification_receipt",
        "verified_flags",
        "VerificationDecision.VERIFIED",
    ):
        assert required_surface in section
    for non_goal in (
        "no ToolExecutor changes",
        "no `CTFState` ownership split",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert non_goal in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/agents/test_p1_claim_invariants.py tests/unit/test_verifier_adapter.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_adapter_boundary_skeleton.py tests/unit/test_proof_authority_adapter.py -q",
        "git diff --check",
    ):
        assert command in section


def test_playbook_records_state_ownership_split_approval_plan() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership split approval plan",
    )

    assert "Status: approval plan recorded, implementation not approved." in section
    assert "flaghunter/agents/pa_agent/ctf_state.py" in section
    assert "flaghunter/adapters/storage/state_store_adapter.py" in section
    assert "flaghunter/adapters/state/state_store_adapter.py" not in section
    assert "tests/unit/test_state_store_adapter.py" in section
    assert "tests/unit/agents/test_p1_claim_invariants.py" in section
    assert "tests/unit/agents/test_p4_task_dag_replay_audit_bundle.py" in section
    assert "state ownership stays in legacy CTFState until explicitly migrated" in section
    assert "rollback point: revert the single approved state ownership implementation commit" in section
    assert "explicit state ownership split approval required before implementation" in section
    for required_surface in (
        "claims_by_id",
        "verification_records_by_id",
        "execution_traces_by_id",
        "to_snapshot",
        "from_snapshot",
        "add_flag",
        "create_claim",
    ):
        assert required_surface in section
    for non_goal in (
        "no proof-authority behavior changes",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert non_goal in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_state_store_adapter.py tests/unit/agents/test_p1_claim_invariants.py tests/unit/agents/test_p4_task_dag_replay_audit_bundle.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_adapter_boundary_skeleton.py -q",
        "git diff --check",
    ):
        assert command in section


def test_playbook_records_ctf_state_legacy_construction_characterization_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "CTFState legacy construction characterization guard",
    )

    assert "Status: characterization guard recorded, no state ownership changed." in section
    assert (
        "tests/unit/agents/test_p1_source_guards.py::"
        "test_p1_ctf_state_construction_stays_in_current_legacy_surfaces"
    ) in section
    for allowed_surface in (
        "`flaghunter/agents/pa_agent/coordinator.py`",
        "`CTFCoordinator._bootstrap_dispatcher`",
        "`flaghunter/agents/pa_agent/ctf_crew_runner.py`",
        "`run_ctf_crew_solve`",
        "`flaghunter/interface/tui_ctf_apply.py`",
        "`CtfApplyMixin._rebuild_override_stop_report`",
        "`CtfApplyMixin._rebuild_wrong_flag_stop_report`",
        "`flaghunter/interface/tui_ctf_runners.py`",
        "`CtfRunnerMixin._run_ctf_crew_dispatcher_mode`",
        "`CTFState.from_snapshot`",
        "legacy state construction and snapshot restoration remain characterized",
    ):
        assert allowed_surface in section
    for boundary in (
        "no state ownership split",
        "no proof-authority behavior changes",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_state_store_adapter_import_unwired_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State store adapter import unwired guard",
    )

    assert "Status: source guard recorded, no production wiring approved." in section
    assert "test_p1_state_store_adapter_stays_unwired_from_production_imports" in section
    for expected in (
        "`flaghunter/adapters/storage/__init__.py`",
        "`flaghunter/adapters/storage/state_store_adapter.py`",
        "`StateStoreAdapter`",
    ):
        assert expected in section
    for boundary in (
        "no state-store production wiring",
        "no `CTFState` ownership split",
        "no dispatcher flow changes",
        "no composition root changes",
        "no proof-authority behavior changes",
    ):
        assert boundary in section


def test_playbook_records_state_store_adapter_delegate_only_guard_hardening() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State store adapter delegate-only guard hardening",
    )

    assert "Status: delegate-only guard recorded, no state ownership changed." in section
    assert "test_state_store_adapter_action_bodies_remain_direct_delegate_only" in section
    for expected in (
        "`StateStoreAdapter.load_snapshot` remains a single delegate call",
        "`StateStoreAdapter.save_snapshot` remains a single delegate call",
        "`self._store.load_snapshot`",
        "`self._store.save_snapshot`",
    ):
        assert expected in section
    for boundary in (
        "no state-store production wiring",
        "no `CTFState` ownership split",
        "no dispatcher flow changes",
        "no composition root changes",
        "no proof-authority behavior changes",
        "no ToolExecutor changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_claim_store_adapter_delegate_only_guard_hardening() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Claim store adapter delegate-only guard hardening",
    )

    assert "Status: delegate-only guard recorded, no claim ownership changed." in section
    assert "test_claim_store_adapter_action_bodies_remain_direct_delegate_only" in section
    for expected in (
        "`ClaimStoreAdapter.create_candidate_claim` remains a single delegate call",
        "`ClaimStoreAdapter.find_claims` remains a single delegate call",
        "`ClaimStoreAdapter.append_evidence_trace` remains a single delegate call",
        "`self._store.create_candidate_claim`",
        "`self._store.find_claims`",
        "`self._store.append_evidence_trace`",
    ):
        assert expected in section
    for boundary in (
        "no claim-store production wiring",
        "no `CTFState` ownership split",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no dispatcher flow changes",
        "no ToolExecutor changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_storage_adapter_namespace_reexport_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Storage adapter namespace re-export guard",
    )

    assert "Status: namespace guard landed, no state ownership changed." in section
    assert "test_storage_adapter_namespace_is_reexport_only" in section
    for locked_surface in (
        "`flaghunter/adapters/storage/__init__.py`",
        "`CheckpointStoreAdapter`",
        "`ClaimStoreAdapter`",
        "`ReadModelStoreAdapter`",
        "`StateStoreAdapter`",
        "only relative storage adapter imports",
        "no store port re-export",
        "no legacy `CTFState` import",
    ):
        assert locked_surface in section
    for boundary in (
        "no state ownership split",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no `CTFTaskDispatcher` flow changes",
        "no ToolExecutor changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_state_ownership_characterization_readiness_aggregate() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership characterization readiness aggregate",
    )

    assert "Status: aggregate guard recorded, implementation not approved." in section
    for required_guard in (
        "CTFState legacy construction characterization guard",
        "State store adapter import unwired guard",
        "State store adapter delegate-only guard hardening",
        "Claim store adapter delegate-only guard hardening",
        "Storage adapter namespace re-export guard",
    ):
        assert required_guard in section
    for focused_test in (
        "test_p1_ctf_state_construction_stays_in_current_legacy_surfaces",
        "test_p1_state_store_adapter_stays_unwired_from_production_imports",
        "test_state_store_adapter_action_bodies_remain_direct_delegate_only",
        "test_claim_store_adapter_action_bodies_remain_direct_delegate_only",
        "test_storage_adapter_namespace_is_reexport_only",
    ):
        assert focused_test in section
    assert "State ownership split implementation remains unapproved" in section
    assert "approval package evidence, not implementation approval" in section
    for boundary in (
        "no state ownership split",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no `CTFTaskDispatcher` flow changes",
        "no ToolExecutor changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_tool_executor_side_effect_split_approval_plan() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "ToolExecutor side-effect split approval plan",
    )

    assert "Status: approval plan recorded, implementation not approved." in section
    assert "flaghunter/tools/executor.py" in section
    assert "flaghunter/adapters/tools/tool_runner_adapter.py" in section
    assert "tests/unit/tools/test_executor.py" in section
    assert "tests/unit/tools/test_executor_cookie_inject.py" in section
    assert "tests/unit/tools/test_finish_control_receipt.py" in section
    assert "tests/unit/test_application_tool_receipt_service.py" in section
    assert "tool execution side effects stay in legacy ToolExecutor until explicitly migrated" in section
    assert "rollback point: revert the single approved ToolExecutor implementation commit" in section
    assert "explicit ToolExecutor side-effect split approval required before implementation" in section
    for required_surface in (
        "execute",
        "execute_batch",
        "runtime",
        "scope check",
        "cookie auto-inject",
        "stealth mode",
        "flag scanning",
        "missing-tool detection",
    ):
        assert required_surface in section
    for non_goal in (
        "no proof-authority behavior changes",
        "no `CTFState` ownership split",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert non_goal in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/tools/test_executor.py tests/unit/tools/test_executor_cookie_inject.py tests/unit/tools/test_finish_control_receipt.py tests/unit/test_application_tool_receipt_service.py tests/unit/test_tool_runner_adapter.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_adapter_boundary_skeleton.py -q",
        "git diff --check",
    ):
        assert command in section


def test_playbook_records_tool_executor_legacy_construction_characterization_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "ToolExecutor legacy construction characterization guard",
    )

    assert "Status: characterization guard recorded, no ToolExecutor behavior changed." in section
    assert (
        "tests/unit/agents/test_p1_source_guards.py::"
        "test_p1_tool_executor_construction_stays_in_base_agent_only"
    ) in section
    for allowed_surface in (
        "`flaghunter/tools/executor.py`",
        "`flaghunter/tools/__init__.py`",
        "`flaghunter/agents/base_agent.py`",
        "`BaseAgent.__init__`",
        "`ToolExecutor`",
        "BaseAgent construction remains the only production construction surface",
    ):
        assert allowed_surface in section
    for boundary in (
        "no ToolExecutor side-effect split",
        "no proof-authority behavior changes",
        "no `CTFState` ownership split",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_dispatcher_composition_root_approval_plan() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Dispatcher/composition root production wiring approval plan",
    )

    assert "Status: approval plan recorded, implementation not approved." in section
    assert "flaghunter/agents/pa_agent/ctf_dispatcher.py" in section
    assert "flaghunter/session/initializer.py" in section
    assert "flaghunter/session/agent_session.py" in section
    assert "flaghunter/interface/cli.py" in section
    assert "flaghunter/interface/web_server.py" in section
    assert "flaghunter/mcp/server/mcp_tools.py" in section
    assert "tests/unit/agents/test_ctf_dispatcher.py" in section
    assert "tests/unit/session/test_agent_session.py" in section
    assert "tests/unit/interface/test_web_server.py" in section
    assert "tests/unit/mcp/test_mcp_ingress_mode_contract.py" in section
    assert "dispatcher and composition root wiring stay in legacy entrypoints until explicitly migrated" in section
    assert "rollback point: revert the single approved dispatcher/composition-root implementation commit" in section
    assert "explicit dispatcher and composition-root approval required before implementation" in section
    for required_surface in (
        "CTFTaskDispatcher",
        "build_agent_components",
        "AgentSession.create",
        "run_task",
        "run_task_async",
        "post_task",
        "MCPRouter",
    ):
        assert required_surface in section
    for non_goal in (
        "no proof-authority behavior changes",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no MCP router changes",
        "no unapproved Web/CLI/TUI behavior changes",
        "no persisted schema compatibility changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert non_goal in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/session/test_agent_session.py tests/unit/interface/test_web_server.py tests/unit/mcp/test_mcp_ingress_mode_contract.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/agents/test_ctf_dispatcher.py tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py -q",
        "git diff --check",
    ):
        assert command in section


def test_playbook_records_dispatcher_first_wiring_approval_review_package() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Dispatcher composition root first wiring approval review package",
    )

    assert "Status: approval review package recorded, implementation not approved." in section
    assert "Recommended first candidate: session composition-root characterization only" in section
    rows = {
        row["Candidate first slice"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "session composition-root characterization": {
            "Files": "`flaghunter/session/initializer.py`; `flaghunter/session/agent_session.py`; `tests/unit/session/test_agent_session.py`; playbook",
            "Rollback point": "`git revert <single dispatcher/composition-root implementation commit>`",
            "Verification gate": "session tests; import/source guards; playbook tests; `git diff --check`",
        },
        "web task construction characterization": {
            "Files": "`flaghunter/interface/web_server.py`; `tests/unit/interface/test_web_server.py`; source guards; playbook",
            "Rollback point": "`git revert <single dispatcher/composition-root implementation commit>`",
            "Verification gate": "web tests; dispatcher tests; import/source guards; `git diff --check`",
        },
        "mcp task construction characterization": {
            "Files": "`flaghunter/mcp/server/mcp_tools.py`; `tests/unit/mcp/test_mcp_ingress_mode_contract.py`; source guards; playbook",
            "Rollback point": "`git revert <single dispatcher/composition-root implementation commit>`",
            "Verification gate": "mcp tests; dispatcher tests; import/source guards; `git diff --check`",
        },
        "cli and tui task construction characterization": {
            "Files": "`flaghunter/interface/cli.py`; `flaghunter/interface/tui_ctf_runners.py`; relevant interface tests; source guards; playbook",
            "Rollback point": "`git revert <single dispatcher/composition-root implementation commit>`",
            "Verification gate": "cli/tui tests; dispatcher tests; import/source guards; `git diff --check`",
        },
    }
    assert set(rows) == set(expected)
    for candidate, expected_values in expected.items():
        for column, value in expected_values.items():
            assert rows[candidate][column] == value
        assert rows[candidate]["Implementation approved"] == "false"
    for invariant in (
        "one candidate first slice per implementation commit",
        "no candidate may switch MCP/Web/CLI/TUI task execution without explicit approval",
        "session characterization is the recommended first review because it can avoid entrypoint behavior changes",
        "approval review package is not implementation approval",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFTaskDispatcher` flow changes",
        "no composition root production wiring",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no ToolExecutor changes",
        "no `CTFState` ownership split",
        "no proof-authority behavior changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_ctf_task_dispatcher_legacy_construction_characterization_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "CTFTaskDispatcher legacy construction characterization guard",
    )

    assert "Status: characterization guard recorded, no dispatcher flow changed." in section
    assert (
        "tests/unit/agents/test_p1_source_guards.py::"
        "test_p1_ctf_task_dispatcher_construction_stays_in_current_legacy_entrypoints"
    ) in section
    for allowed_surface in (
        "`flaghunter/agents/pa_agent/ctf_dispatcher.py`",
        "`flaghunter/agents/pa_agent/ctf_crew_runner.py`",
        "`flaghunter/eval/replay.py`",
        "`flaghunter/interface/cli.py`",
        "`flaghunter/interface/tui_ctf_runners.py`",
        "`flaghunter/interface/web_server.py`",
        "`flaghunter/mcp/server/mcp_tools.py`",
        "`CTFTaskDispatcher`",
        "legacy entrypoints remain the only dispatcher construction surfaces",
    ):
        assert allowed_surface in section
    for boundary in (
        "no dispatcher flow changes",
        "no composition root changes",
        "no MCP router changes",
        "no ToolExecutor changes",
        "no `CTFState` ownership split",
        "no proof-authority behavior changes",
        "no Web/CLI/TUI behavior changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_core_approval_package_aggregate_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Core production approval package aggregate guard",
    )

    assert "Status: aggregate guard recorded, implementation not approved by this section." in section
    assert "approval packages do not grant implementation approval" in section
    assert "no approval by implication" in section
    rows = {
        row["Core candidate"]: row
        for row in _markdown_table_rows(section)
    }
    assert list(rows) == [
        "Verifier/proof authority boundary",
        "State ownership split",
        "ToolExecutor side-effect split",
        "Dispatcher/composition root production wiring",
    ]
    expected_plans = {
        "Verifier/proof authority boundary": "Verifier/proof authority boundary approval plan",
        "State ownership split": "State ownership split approval plan",
        "ToolExecutor side-effect split": "ToolExecutor side-effect split approval plan",
        "Dispatcher/composition root production wiring": "Dispatcher/composition root production wiring approval plan",
    }
    expected_readiness = {
        "Verifier/proof authority boundary": "Proof authority characterization readiness aggregate",
        "State ownership split": "State ownership characterization readiness aggregate",
        "ToolExecutor side-effect split": "ToolExecutor side-effect characterization readiness aggregate",
        "Dispatcher/composition root production wiring": "Dispatcher composition root characterization readiness aggregate",
    }
    for candidate, plan_heading in expected_plans.items():
        assert rows[candidate]["Approval package"] == f"`{plan_heading}`"
        assert rows[candidate]["Implementation approved"] == "false"
        assert rows[candidate]["Current implementation state"] == "not approved"
        assert plan_heading in text
        readiness_heading = expected_readiness[candidate]
        assert rows[candidate]["Readiness evidence"] == f"`{readiness_heading}`"
        assert readiness_heading in text
    for invariant in (
        "every core package must remain implementation approved = false until explicit human approval lands",
        "approval package status must not be used as implementation approval",
        "readiness evidence must not be used as implementation approval",
        "each future implementation must update exactly one package and add a landing record",
        "rollback point remains the single approved implementation commit",
    ):
        assert invariant in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py -q",
        "git diff --check",
    ):
        assert command in section


def test_playbook_core_approval_queue_matches_aggregate_guard() -> None:
    text = _playbook_text()
    queue_section = _heading_section_text(
        text,
        "Post read-side core decoupling approval queue",
    )
    aggregate_section = _heading_section_text(
        text,
        "Core approval queue aggregate consistency guard",
    )

    assert "Status: queue aggregate consistency guard recorded, implementation not approved by this section." in aggregate_section
    assert "queue rows and aggregate rows must stay aligned" in aggregate_section

    queue_rows = {
        row["Candidate"]: row
        for row in _markdown_table_rows(queue_section.split("Queue rules:", 1)[0])
    }
    aggregate_rows = {
        row["Core candidate"]: row
        for row in _markdown_table_rows(
            _heading_section_text(
                text,
                "Core production approval package aggregate guard",
            )
        )
    }

    core_candidates = [
        "Verifier/proof authority boundary",
        "State ownership split",
        "ToolExecutor side-effect split",
        "Dispatcher/composition root production wiring",
    ]
    assert list(aggregate_rows) == core_candidates
    for candidate in core_candidates:
        assert queue_rows[candidate]["Current status"] == aggregate_rows[candidate]["Current implementation state"]
        assert queue_rows[candidate]["Implementation approved"] == aggregate_rows[candidate]["Implementation approved"]
        assert queue_rows[candidate]["Required approval"] in aggregate_section

    for invariant in (
        "queue rows and aggregate rows must stay aligned",
        "required approval text must remain visible before implementation",
        "required verification text must remain visible before implementation",
        "no core implementation approval may be inferred from either table alone",
    ):
        assert invariant in aggregate_section


def test_playbook_records_core_readiness_aggregate_acceptance_matrix() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Core readiness aggregate acceptance matrix",
    )

    assert "Status: readiness matrix recorded, no production implementation approved." in section
    rows = {
        row["Core candidate"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "Verifier/proof authority boundary": {
            "Readiness aggregate": "`Proof authority characterization readiness aggregate`",
            "Readiness accepted": "true",
            "Implementation approved": "false",
            "Next gate": "explicit Verifier/proof authority boundary implementation approval",
        },
        "State ownership split": {
            "Readiness aggregate": "`State ownership characterization readiness aggregate`",
            "Readiness accepted": "true",
            "Implementation approved": "false",
            "Next gate": "explicit State ownership split implementation approval",
        },
        "ToolExecutor side-effect split": {
            "Readiness aggregate": "`ToolExecutor side-effect characterization readiness aggregate`",
            "Readiness accepted": "true",
            "Implementation approved": "false",
            "Next gate": "explicit ToolExecutor side-effect split implementation approval",
        },
        "Dispatcher/composition root production wiring": {
            "Readiness aggregate": "`Dispatcher composition root characterization readiness aggregate`",
            "Readiness accepted": "true",
            "Implementation approved": "false",
            "Next gate": "explicit Dispatcher/composition root production wiring implementation approval",
        },
    }
    assert set(rows) == set(expected)
    for candidate, expected_values in expected.items():
        for column, value in expected_values.items():
            assert rows[candidate][column] == value
    for aggregate_heading in (
        "Proof authority characterization readiness aggregate",
        "State ownership characterization readiness aggregate",
        "ToolExecutor side-effect characterization readiness aggregate",
        "Dispatcher composition root characterization readiness aggregate",
    ):
        assert aggregate_heading in text
        assert aggregate_heading in section
    for invariant in (
        "readiness accepted means characterization evidence exists, not that production migration is approved",
        "implementation approved must remain false until a user-approved implementation slice lands",
        "next gate text must name the exact high-risk boundary requiring approval",
        "every future implementation must update one row and add one landing record in the same functional commit",
    ):
        assert invariant in section
    for boundary in (
        "no proof-authority behavior changes",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root production wiring",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_dispatcher_composition_root_readiness_characterization_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Dispatcher composition root readiness characterization guard",
    )

    assert "Status: readiness characterization guard recorded, no production wiring." in section
    assert "test_p1_composition_root_readiness_stays_unwired_from_new_public_surfaces" in section
    assert "test_p1_ctf_task_dispatcher_construction_stays_in_current_legacy_entrypoints" in section
    for guarded_name in (
        "CompositionRoot",
        "ProductionCompositionRoot",
        "build_composition_root",
        "create_composition_root",
        "wire_production",
    ):
        assert guarded_name in section
    for invariant in (
        "new public composition-root surfaces remain absent until explicit approval",
        "current `CTFTaskDispatcher` production construction surfaces stay characterized as legacy entrypoints",
        "readiness evidence is not implementation approval",
        "future production wiring must name exactly one entrypoint family and one rollback commit",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFTaskDispatcher` flow changes",
        "no composition root production wiring",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no ToolExecutor changes",
        "no `CTFState` ownership split",
        "no proof-authority behavior changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_dispatcher_production_wiring_approval_package_consistency_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Dispatcher production wiring approval package consistency guard",
    )

    assert "Status: approval package consistency guard recorded, no production wiring." in section
    rows = {
        row["Governance surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected_rows = {
        "approval plan": "Dispatcher/composition root production wiring approval plan",
        "readiness aggregate": "Dispatcher composition root characterization readiness aggregate",
        "approval text template": "Dispatcher composition root first slice approval text template",
        "aggregate row": "Core production approval package aggregate guard",
        "landing evidence template": "Core implementation landing evidence template",
    }
    assert set(rows) == set(expected_rows)
    for surface, heading in expected_rows.items():
        assert rows[surface]["Required heading"] == f"`{heading}`"
        assert rows[surface]["Required before approval transition"] == "true"
        assert rows[surface]["Current implementation approved"] == "false"
        assert heading in text
    for invariant in (
        "dispatcher production wiring approval requires every governance surface to agree",
        "readiness aggregate evidence must match the aggregate row and approval text template",
        "landing evidence remains template-only until a real implementation commit exists",
        "no dispatcher/composition-root production wiring may be inferred from this consistency guard",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFTaskDispatcher` flow changes",
        "no composition root production wiring",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no ToolExecutor changes",
        "no `CTFState` ownership split",
        "no proof-authority behavior changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_dispatcher_approval_transition_atomicity_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Dispatcher approval transition atomicity guard",
    )

    assert "Status: approval transition atomicity guard recorded, no production wiring approved." in section
    rows = {
        row["Transition surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected_rows = {
        "approval plan state": "Dispatcher/composition root production wiring approval plan",
        "approval package consistency": "Dispatcher production wiring approval package consistency guard",
        "aggregate approval flag": "Core production approval package aggregate guard",
        "first-slice approval text": "Dispatcher composition root first slice approval text template",
        "landing evidence": "Core implementation landing evidence template",
    }
    assert set(rows) == set(expected_rows)
    for surface, heading in expected_rows.items():
        assert rows[surface]["Required heading"] == f"`{heading}`"
        assert rows[surface]["Current transition complete"] == "false"
        assert heading in text
    for invariant in (
        "dispatcher approval transitions must update every listed surface in the same governance commit",
        "partial approval transitions must fail review",
        "approval transition evidence must land before any production wiring commit",
        "landing evidence must stay incomplete until a real implementation commit SHA exists",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFTaskDispatcher` flow changes",
        "no composition root production wiring",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no ToolExecutor changes",
        "no `CTFState` ownership split",
        "no proof-authority behavior changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_core_implementation_landing_evidence_completeness_matrix() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Core implementation landing evidence completeness matrix",
    )

    assert "Status: landing evidence matrix recorded; proof completion transitioned without production behavior approval." in section
    rows = {
        row["Core candidate"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "Verifier/proof authority boundary": "`Verifier proof authority core landing completion transition record`",
        "State ownership split": "`State ownership split implementation landing record`",
        "ToolExecutor side-effect split": "`ToolExecutor side-effect split implementation landing record`",
        "Dispatcher/composition root production wiring": "`Dispatcher/composition root production wiring implementation landing record`",
    }
    assert set(rows) == set(expected)
    for candidate, landing_record in expected.items():
        row = rows[candidate]
        assert row["Required landing record"] == landing_record
        if candidate == "Verifier/proof authority boundary":
            assert row["Implementation approved"] == "governance-only completion"
            assert row["Landing evidence complete"] == "true"
            assert row["Rollback executable"] == "true"
        else:
            assert row["Implementation approved"] == "false"
            assert row["Landing evidence complete"] == "false"
            assert row["Rollback executable"] == "false"
    for required_field in (
        "implementation commit SHA",
        "approved scope",
        "readiness evidence reviewed",
        "files changed",
        "red test evidence",
        "focused regression result",
        "architecture/source-guard result",
        "git diff --check result",
        "post-push branch status",
        "rollback command",
        "boundary confirmation",
    ):
        assert required_field in section
    for invariant in (
        "proof completion landing evidence is governance-only and does not approve production behavior",
        "later landing evidence complete stays false until the matching implementation commit is pushed",
        "later rollback executable stays false until a real commit SHA replaces the placeholder",
        "each landing record must name exactly one core candidate",
        "implementation approval and landing evidence must move together for one functional point",
    ):
        assert invariant in section
    for boundary in (
        "no proof-authority behavior changes",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root production wiring",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_session_composition_root_characterization_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Session composition root characterization guard",
    )

    assert "Status: session composition-root characterization recorded, no production wiring." in section
    assert "test_session_composition_root_characterizes_current_assembly_owner" in section
    for expected in (
        "`AgentSession.create` lazily imports `build_agent_components` from `flaghunter.session.initializer`",
        "`flaghunter.session.initializer` remains the current assembly owner",
        "`flaghunter.interface.initializer` remains a compatibility re-export",
        "entrypoint production wiring remains unchanged",
    ):
        assert expected in section
    for boundary in (
        "no `CTFTaskDispatcher` flow changes",
        "no composition root production wiring changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no ToolExecutor changes",
        "no runtime construction changes",
        "no `CTFState` ownership split",
        "no proof-authority behavior changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_entrypoint_composition_root_usage_characterization_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Entrypoint composition root usage characterization guard",
    )

    assert "Status: entrypoint usage characterization recorded, no production wiring." in section
    assert "test_presentation_entrypoints_currently_use_agent_session_create" in section
    assert "test_web_entrypoint_still_uses_compatibility_initializer_seam" in section
    assert "test_mcp_task_execution_routes_construction_through_agent_session_after_approval" in section
    for expected in (
        "CLI, TUI, Web, and MCP server bootstrap currently use `AgentSession.create`",
        "Web still uses `flaghunter.interface.initializer` as a compatibility builder seam",
        "MCP task execution now routes construction through `AgentSession.create` in `flaghunter.mcp.server.mcp_tools`",
        "MCP task execution keeps a MCP-specific builder to preserve legacy runtime, LLM, and tool compatibility",
    ):
        assert expected in section
    for boundary in (
        "no `CTFTaskDispatcher` flow changes",
        "no composition root production wiring changes",
        "no MCP task execution wiring changes",
        "no Web/CLI/TUI task wiring changes",
        "no ToolExecutor changes",
        "no runtime construction changes",
        "no `CTFState` ownership split",
        "no proof-authority behavior changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_mcp_task_execution_composition_root_approval_package() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "MCP task execution composition-root approval package",
    )

    assert "Status: approval package characterized, first wiring slice landed." in section
    assert "MCP task execution now routes construction through `AgentSession.create`" in section
    assert "test_mcp_task_execution_routes_construction_through_agent_session_after_approval" in section
    rows = {
        row["Item"]: row
        for row in _markdown_table_rows(section)
    }
    expected_rows = {
        "target production file": "`flaghunter/mcp/server/mcp_tools.py`",
        "allowed test files": "`tests/unit/mcp`; `tests/unit/test_entrypoint_composition_root_characterization.py`; `tests/unit/test_clean_architecture_migration_playbook.py`",
        "governance record": "`docs/dev/FlagHunter_Clean_Architecture_Migration_Playbook_v0.1_2026-07-04.md`",
        "rollback point": "single future MCP task execution wiring commit",
    }
    for item, expected_value in expected_rows.items():
        assert rows[item]["Required value"] == expected_value
    for required_gate in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/mcp/test_mcp_ingress_mode_contract.py tests/unit/mcp/test_mcp_tools.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_entrypoint_composition_root_characterization.py tests/unit/test_clean_architecture_migration_playbook.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py -q",
        "git diff --check",
    ):
        assert required_gate in section
    for forbidden in (
        "禁止 MCP router changes",
        "禁止 ToolExecutor changes",
        "禁止 Verifier or proof authority behavior changes",
        "禁止 CTFState ownership split",
        "禁止 Dispatcher flow changes",
        "禁止 Web/CLI/TUI task wiring changes",
        "禁止 composition-root production wiring outside MCP task execution",
        "禁止 P5、crew/recovery",
    ):
        assert forbidden in section
    for invariant in (
        "approval package evidence is not implementation approval",
        "future implementation must preserve MCP external response shape",
        "future implementation must preserve task entry lifecycle and async/blocking behavior",
        "future implementation must update exactly one production wiring surface",
    ):
        assert invariant in section


def test_playbook_records_mcp_task_execution_composition_root_wiring_landing() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "MCP task execution composition-root wiring landing record",
    )

    assert "Status: first wiring slice landed." in section
    assert "approved scope: MCP task execution agent/runtime construction path only" in section
    assert "`flaghunter/mcp/server/mcp_tools.py::_make_agent` now calls `AgentSession.create`" in section
    assert "`_build_mcp_task_components` preserves legacy `_LLMClass`, `_RuntimeClass`, primary tools, and max iterations" in section
    assert "CTF dispatcher handoff remains in `_drive_task`" in section
    for evidence in (
        "test_mcp_make_agent_routes_task_construction_through_agent_session",
        "test_mcp_task_execution_routes_construction_through_agent_session_after_approval",
    ):
        assert evidence in section
    for boundary in (
        "no MCP router changes",
        "no MCP server bootstrap changes",
        "no Web/CLI/TUI task wiring changes",
        "no ToolExecutor changes",
        "no Verifier or proof authority behavior changes",
        "no CTFState ownership split",
        "no Dispatcher flow changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_mcp_task_execution_behavior_equivalence_hardening() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "MCP task execution behavior equivalence hardening record",
    )

    assert "Status: behavior equivalence hardening landed, no production changes." in section
    assert "test_mcp_task_execution_behavior_equivalence_survives_session_construction" in section
    for locked_surface in (
        "run_task blocking response shape",
        "run_task_async accepted response shape",
        "TaskEntry lifecycle fields",
        "status/result/readback fields",
        "ingressHandoff and controlDecision payload compatibility",
        "notes snapshot, thinking, tool call, and tool result readback semantics",
    ):
        assert locked_surface in section
    for boundary in (
        "no `flaghunter/mcp/server/mcp_tools.py` production changes",
        "no MCP router changes",
        "no MCP server bootstrap changes",
        "no Web/CLI/TUI task wiring changes",
        "no ToolExecutor changes",
        "no Verifier or proof authority behavior changes",
        "no CTFState ownership split",
        "no Dispatcher flow changes",
        "no composition-root production wiring changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_mcp_task_execution_post_wiring_source_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "MCP task execution post-wiring source guard",
    )

    assert "Status: source guard landed, no production changes." in section
    assert "test_mcp_task_execution_session_wiring_stays_inside_mcp_tools" in section
    for locked_scope in (
        "`AgentSession` task construction wiring stays in `flaghunter/mcp/server/mcp_tools.py`",
        "`_build_mcp_task_components` stays in `flaghunter/mcp/server/mcp_tools.py`",
        "MCP router and transport modules stay free of task execution construction",
        "CTF dispatcher handoff stays in `mcp_tools.py::_drive_task`",
    ):
        assert locked_scope in section
    for forbidden in (
        "no MCP router changes",
        "no MCP transport changes",
        "no MCP server bootstrap changes",
        "no Web/CLI/TUI task wiring changes",
        "no ToolExecutor changes",
        "no Verifier or proof authority behavior changes",
        "no CTFState ownership split",
        "no Dispatcher flow changes",
        "no composition-root production wiring changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert forbidden in section


def test_playbook_records_dispatcher_composition_root_characterization_readiness_aggregate() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Dispatcher composition root characterization readiness aggregate",
    )

    assert "Status: aggregate guard recorded, production wiring not approved." in section
    for required_guard in (
        "Dispatcher composition root readiness characterization guard",
        "CTFTaskDispatcher legacy construction characterization guard",
        "Session composition root characterization guard",
        "Entrypoint composition root usage characterization guard",
        "MCP task execution composition-root wiring landing record",
        "MCP task execution behavior equivalence hardening record",
        "MCP task execution post-wiring source guard",
    ):
        assert required_guard in section
    for focused_test in (
        "test_p1_composition_root_readiness_stays_unwired_from_new_public_surfaces",
        "test_p1_ctf_task_dispatcher_construction_stays_in_current_legacy_entrypoints",
        "test_session_composition_root_characterizes_current_assembly_owner",
        "test_presentation_entrypoints_currently_use_agent_session_create",
        "test_mcp_task_execution_routes_construction_through_agent_session_after_approval",
        "test_mcp_make_agent_routes_task_construction_through_agent_session",
        "test_mcp_task_execution_behavior_equivalence_survives_session_construction",
        "test_mcp_task_execution_session_wiring_stays_inside_mcp_tools",
    ):
        assert focused_test in section
    for retained_surface in (
        "`CTFTaskDispatcher` legacy construction surfaces",
        "`AgentSession.create` entrypoint usage",
        "MCP task execution `_make_agent` session construction",
        "MCP external response shape and TaskEntry lifecycle",
        "MCP router, transport, and bootstrap stay unwired from task construction",
    ):
        assert retained_surface in section
    assert "Dispatcher/composition root production wiring remains unapproved" in section
    assert "approval package evidence, not production wiring approval" in section
    for boundary in (
        "no `CTFTaskDispatcher` flow changes",
        "no composition root production wiring",
        "no MCP router changes",
        "no MCP server bootstrap changes",
        "no unapproved MCP task execution wiring changes",
        "no Web/CLI/TUI task wiring changes",
        "no ToolExecutor changes",
        "no `CTFState` ownership split",
        "no proof-authority behavior changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_state_ownership_first_slice_approval_text_template() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership first slice approval text template",
    )

    assert "Status: approval text template recorded, implementation not approved by this section." in section
    assert "批准 State ownership split 第一刀" in section
    assert "one state snapshot or claim-store ownership characterization seam" in section
    for required_clause in (
        "candidate: State ownership split",
        "first slice: state snapshot or claim-store ownership characterization with no storage ownership migration",
        "scope: state boundary characterization only",
        "rollback: revert the single implementation commit",
        "readiness evidence: CTFState legacy construction characterization guard reviewed",
        "landing evidence: required",
    ):
        assert required_clause in section
    for forbidden_clause in (
        "禁止 CTFState ownership migration",
        "禁止 CTFVerifier decision behavior change",
        "禁止 proof authority behavior change",
        "禁止 Dispatcher、ToolExecutor、MCP production wiring、Web/CLI/TUI task wiring、composition root、P5、crew/recovery",
    ):
        assert forbidden_clause in section
    for invariant in (
        "this template is not approval by itself",
        "approval must be sent as a user message",
        "state-store adapter evidence does not approve production state ownership migration",
        "state ownership work must not move proof upgrade authority",
    ):
        assert invariant in section


def test_playbook_records_state_ownership_implementation_approval_package_aggregate_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership implementation approval package aggregate guard",
    )

    assert "Status: aggregate guard recorded, State implementation not approved." in section
    rows = {
        row["Approval package surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "approval plan": "`State ownership split approval plan`",
        "readiness aggregate": "`State ownership characterization readiness aggregate`",
        "approval text template": "`State ownership first slice approval text template`",
        "proof completion prerequisite": "`Verifier proof authority core landing completion transition record`",
        "sequence gate": "`Core implementation sequence gate`",
        "landing evidence matrix": "`Core implementation landing evidence completeness matrix`",
    }
    assert set(rows) == set(expected)
    for surface, heading in expected.items():
        assert rows[surface]["Required heading"] == heading
        assert rows[surface]["Current ready"] == "true"
        assert rows[surface]["Implementation approved"] == "false"
        assert heading.strip("`") in text
    for invariant in (
        "State approval package readiness does not grant implementation approval",
        "State implementation requires a separate explicit user approval",
        "State first slice must remain one functional point per commit",
        "State implementation must not move proof authority or verifier decisions",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFState` ownership migration",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_state_ownership_approval_transition_atomicity_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership approval transition atomicity guard",
    )

    assert "Status: transition atomicity guard recorded, State implementation not approved." in section
    rows = {
        row["Transition surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "approval package": "`State ownership implementation approval package aggregate guard`",
        "approval plan": "`State ownership split approval plan`",
        "landing matrix row": "`Core implementation landing evidence completeness matrix` State row",
        "sequence gate row": "`Core implementation sequence gate` State row",
        "landing evidence": "`State ownership split implementation landing record`",
    }
    assert set(rows) == set(expected)
    for surface, heading in expected.items():
        assert rows[surface]["Required heading"] == heading
        assert rows[surface]["Current transition complete"] == "false"
        assert heading.split("`")[1] in text
    for invariant in (
        "State approval transition must update every listed surface in the same commit",
        "partial State approval transitions must fail review",
        "approval transition evidence must land before any State implementation commit",
        "State landing evidence must stay incomplete until a real implementation commit exists",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFState` ownership migration",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_state_ownership_approval_transition_coverage_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership approval transition coverage guard",
    )

    assert "Status: coverage guard recorded, State implementation not approved." in section
    rows = {
        row["Governance surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "approval package",
        "approval plan",
        "readiness aggregate",
        "approval text template",
        "proof completion prerequisite",
        "sequence gate",
        "landing evidence matrix",
        "landing evidence",
    }
    assert set(rows) == expected
    for surface, row in rows.items():
        assert row["Required before approval transition"] == "true"
        assert row["Current implementation approved"] == "false"
        assert surface in text
    for invariant in (
        "every State approval transition table must keep the same canonical governance surface set",
        "State approval transition coverage must include proof completion prerequisite evidence",
        "State approval transition coverage must include landing evidence before implementation",
        "coverage evidence must not be treated as State implementation approval",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFState` ownership migration",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_state_ownership_approval_transition_evidence_consistency_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership approval transition evidence consistency guard",
    )

    assert "Status: evidence consistency guard recorded, State implementation not approved." in section
    assert "State implementation evidence remains absent until explicit approval lands" in section
    rows = {
        row["Evidence item"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "approval package evidence": {
            "Required location": "`State ownership implementation approval package aggregate guard`",
            "Current implementation evidence present": "true",
        },
        "approval transition atomicity evidence": {
            "Required location": "`State ownership approval transition atomicity guard`",
            "Current implementation evidence present": "true",
        },
        "approval transition coverage evidence": {
            "Required location": "`State ownership approval transition coverage guard`",
            "Current implementation evidence present": "true",
        },
        "red test evidence": {
            "Required location": "`State ownership split implementation landing record`",
            "Current implementation evidence present": "false",
        },
        "green focused regression": {
            "Required location": "`State ownership split implementation landing record`",
            "Current implementation evidence present": "false",
        },
        "architecture/source regression": {
            "Required location": "`State ownership split implementation landing record`",
            "Current implementation evidence present": "false",
        },
        "post-push branch status": {
            "Required location": "`State ownership split implementation landing record`",
            "Current implementation evidence present": "false",
        },
    }
    assert set(rows) == set(expected)
    for item, expected_row in expected.items():
        assert rows[item]["Required location"] == expected_row["Required location"]
        assert (
            rows[item]["Current implementation evidence present"]
            == expected_row["Current implementation evidence present"]
        )
        assert expected_row["Required location"].strip("`") in text
    for invariant in (
        "State implementation evidence must remain false until explicit approval and implementation land",
        "approval transition evidence must not be substituted for implementation evidence",
        "landing evidence must include red, green, architecture regression, and post-push status before State implementation approved changes",
        "evidence consistency must not authorize State ownership migration",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFState` ownership migration",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_state_ownership_implementation_landing_status_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership implementation landing status guard",
    )

    assert "Status: landing status guard recorded, State implementation not landed." in section
    assert "State ownership split remains unlanded until an approved implementation commit exists" in section
    rows = {
        row["Landing surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "landing record": "`State ownership split implementation landing record`",
        "landing evidence matrix": "`Core implementation landing evidence completeness matrix` State row",
        "sequence gate": "`Core implementation sequence gate` State row",
        "approval evidence": "`State ownership approval transition evidence consistency guard`",
    }
    assert set(rows) == set(expected)
    for surface, location in expected.items():
        assert rows[surface]["Required location"] == location
        assert rows[surface]["Current landed"] == "false"
        assert rows[surface]["Current implementation approved"] == "false"
        assert location.split("`")[1] in text
    for invariant in (
        "State landing status must remain false until explicit approval and implementation evidence land",
        "State landing status must not be raised by approval package readiness alone",
        "State landing status must move together with the matrix and sequence gate in the implementation commit",
        "State landing status must not authorize proof authority or verifier behavior changes",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFState` ownership migration",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_state_ownership_rollback_placeholder_consistency_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership rollback placeholder consistency guard",
    )

    assert "Status: rollback placeholder guard recorded, State implementation not approved." in section
    assert "Rollback remains a placeholder until a single approved State implementation commit lands" in section
    rows = {
        row["Rollback surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "approval package": "`State ownership implementation approval package aggregate guard`",
        "approval transition evidence": "`State ownership approval transition evidence consistency guard`",
        "landing status": "`State ownership implementation landing status guard`",
        "implementation landing record": "`State ownership split implementation landing record`",
    }
    assert set(rows) == set(expected)
    for surface, location in expected.items():
        assert rows[surface]["Required location"] == location
        assert rows[surface]["Rollback command present"] == "false"
        assert rows[surface]["Current implementation approved"] == "false"
        assert location.split("`")[1] in text
    for invariant in (
        "State rollback point must be the single approved implementation commit",
        "rollback placeholder must remain false before State implementation approval",
        "rollback evidence must land with the implementation landing record",
        "rollback placeholder must not authorize State ownership migration",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFState` ownership migration",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_state_ownership_verification_gate_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership implementation verification gate guard",
    )

    assert "Status: verification gate guard recorded, State implementation not approved." in section
    assert "Future State implementation must pass every listed verification gate before landing status changes" in section
    rows = {
        row["Verification gate"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "red test evidence": "focused State ownership implementation test",
        "green focused regression": "state snapshot fixtures and state-store adapter tests",
        "proof/source regression": "proof guards, claim invariants, verifier/proof adapter tests",
        "architecture regression": "import layers and clean architecture playbook tests",
        "diff hygiene": "`git diff --check`",
        "post-push status": "`git status --short --branch` plus remote branch SHA",
    }
    assert set(rows) == set(expected)
    for gate, required_evidence in expected.items():
        assert rows[gate]["Required evidence"] == required_evidence
        assert rows[gate]["Current complete"] == "false"
        assert rows[gate]["Current implementation approved"] == "false"
    for invariant in (
        "State verification gates must all be complete before implementation approved changes",
        "focused State tests cannot replace proof/source regression",
        "green tests cannot replace rollback and post-push evidence",
        "verification gate readiness must not authorize State ownership migration",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFState` ownership migration",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_state_ownership_implementation_approval_readiness_completeness_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership implementation approval readiness completeness guard",
    )

    assert "Status: readiness completeness guard recorded, State implementation not approved." in section
    assert "State ownership implementation approval readiness is complete as governance evidence only" in section
    rows = {
        row["Readiness surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "approval package": "`State ownership implementation approval package aggregate guard`",
        "transition atomicity": "`State ownership approval transition atomicity guard`",
        "transition coverage": "`State ownership approval transition coverage guard`",
        "transition evidence": "`State ownership approval transition evidence consistency guard`",
        "landing status": "`State ownership implementation landing status guard`",
        "rollback placeholder": "`State ownership rollback placeholder consistency guard`",
        "verification gates": "`State ownership implementation verification gate guard`",
    }
    assert set(rows) == set(expected)
    for surface, heading in expected.items():
        assert rows[surface]["Required heading"] == heading
        assert rows[surface]["Governance ready"] == "true"
        assert rows[surface]["Implementation approved"] == "false"
        assert heading.strip("`") in text
    for invariant in (
        "State readiness completeness is not State implementation approval",
        "explicit user approval is still required before any State implementation commit",
        "future State implementation must update exactly one implementation landing record",
        "readiness completeness must not authorize State ownership migration",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFState` ownership migration",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_state_ownership_first_slice_characterization_landing() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership first slice characterization landing record",
    )

    assert "Status: first slice characterization landed; no ownership migration." in section
    assert "State ownership split 第一刀: formally approved" in section
    assert "test_p1_ctf_state_snapshot_ownership_stays_in_legacy_state_only" in section
    assert "test_p1_ctf_state_construction_stays_in_current_legacy_surfaces" in section
    for expected in (
        "`CTFState.to_snapshot` remains the only production snapshot export owner",
        "`CTFState.from_snapshot` remains the only production snapshot restore owner",
        "`flaghunter/agents/pa_agent/ctf_state.py`",
        "state snapshot ownership characterization",
        "claim-store ownership migration remains unstarted",
    ):
        assert expected in section
    for boundary in (
        "no `CTFState` ownership migration",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no Dispatcher changes",
        "no ToolExecutor changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_state_ownership_characterization_landing_reconciliation_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership characterization landing reconciliation guard",
    )

    assert "Status: reconciliation guard recorded, State core landing remains incomplete." in section
    for required_heading in (
        "State ownership first slice characterization landing record",
        "State ownership unlock blocked until proof completion guard",
        "Core implementation landing evidence completeness matrix",
        "Core implementation sequence gate",
    ):
        assert required_heading in section
    rows = {
        row["Evidence surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected_rows = {
        "first slice characterization": {
            "Required heading": "`State ownership first slice characterization landing record`",
            "Counts as State core landing complete": "false",
        },
        "unlock blocked guard": {
            "Required heading": "`State ownership unlock blocked until proof completion guard`",
            "Counts as State core landing complete": "false",
        },
        "core landing matrix row": {
            "Required heading": "`Core implementation landing evidence completeness matrix`",
            "Counts as State core landing complete": "false",
        },
        "sequence gate row": {
            "Required heading": "`Core implementation sequence gate`",
            "Counts as State core landing complete": "false",
        },
    }
    assert set(rows) == set(expected_rows)
    for surface, expected_values in expected_rows.items():
        for column, value in expected_values.items():
            assert rows[surface][column] == value
    for invariant in (
        "State characterization landing does not complete the State core implementation landing row",
        "State implementation landing requires explicit approval after proof completion unlocks the sequence gate",
        "State snapshot ownership characterization is readiness evidence, not storage ownership migration",
        "State unlock blocked guard remains authoritative while proof completion is pending",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFState` ownership migration",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no ToolExecutor changes",
        "no CTFTaskDispatcher flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_tool_executor_first_slice_approval_text_template() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "ToolExecutor first slice approval text template",
    )

    assert "Status: approval text template recorded, implementation not approved by this section." in section
    assert "批准 ToolExecutor side-effect split 第一刀" in section
    assert "one tool receipt or tool-runner side-effect characterization seam" in section
    for required_clause in (
        "candidate: ToolExecutor side-effect split",
        "first slice: tool receipt or tool-runner side-effect characterization with no executor production wiring",
        "scope: ToolExecutor boundary characterization only",
        "rollback: revert the single implementation commit",
        "readiness evidence: ToolExecutor legacy construction characterization guard reviewed",
        "landing evidence: required",
    ):
        assert required_clause in section
    for forbidden_clause in (
        "禁止 ToolExecutor side-effect migration",
        "禁止 tool-runner production wiring",
        "禁止 runtime construction changes",
        "禁止 CTFState ownership migration",
        "禁止 proof authority behavior change",
        "禁止 Dispatcher、MCP production wiring、Web/CLI/TUI task wiring、composition root、P5、crew/recovery",
    ):
        assert forbidden_clause in section
    for invariant in (
        "this template is not approval by itself",
        "approval must be sent as a user message",
        "tool-runner adapter evidence does not approve production ToolExecutor migration",
        "ToolExecutor work must not move proof upgrade or state ownership authority",
    ):
        assert invariant in section


def test_playbook_records_tool_executor_first_slice_characterization_landing() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "ToolExecutor first slice characterization landing record",
    )

    assert "Status: first slice characterization landed; no side-effect migration." in section
    assert "ToolExecutor side-effect split 第一刀: formally approved" in section
    assert "test_tool_executor_execute_retains_legacy_side_effect_surface_markers" in section
    assert "test_tool_executor_batch_still_delegates_through_legacy_execute" in section
    assert "test_tool_executor_module_does_not_import_tool_runner_adapter" in section
    for expected in (
        "`ToolExecutor.execute` retains legacy scope check ownership",
        "`ToolExecutor.execute` retains legacy cookie auto-inject ownership",
        "`ToolExecutor.execute` retains legacy stealth mode ownership",
        "`ToolExecutor.execute` retains legacy flag scanning ownership",
        "`ToolExecutor.execute` retains legacy missing-tool detection ownership",
        "`ToolExecutor.execute_batch` still delegates through `self.execute`",
        "tool-runner production wiring remains unstarted",
    ):
        assert expected in section
    for boundary in (
        "no ToolExecutor production behavior changes",
        "no tool-runner production wiring",
        "no runtime construction changes",
        "no `CTFState` ownership migration",
        "no `CTFVerifier` decision behavior changes",
        "no proof-authority behavior changes",
        "no Dispatcher changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_tool_executor_namespace_reexport_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "ToolExecutor namespace re-export guard",
    )

    assert "Status: namespace guard landed, no ToolExecutor behavior changed." in section
    assert "test_tools_namespace_keeps_tool_executor_legacy_reexport_only" in section
    for locked_surface in (
        "`flaghunter/tools/__init__.py`",
        "`ToolExecutor`",
        "`flaghunter.tools.executor.ToolExecutor`",
        "no `ToolRunnerAdapter` re-export",
        "no `ToolRunnerPort` re-export",
        "no `ExecutionResult` namespace expansion",
    ):
        assert locked_surface in section
    for boundary in (
        "no ToolExecutor production behavior changes",
        "no ToolExecutor side-effect split",
        "no tool-runner production wiring",
        "no runtime construction changes",
        "no `CTFState` ownership migration",
        "no `CTFVerifier` decision behavior changes",
        "no proof-authority behavior changes",
        "no Dispatcher changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_tool_runner_adapter_delegate_only_guard_hardening() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Tool runner adapter delegate-only guard hardening",
    )

    assert "Status: delegate-only guard recorded, no production wiring." in section
    assert "test_tool_runner_adapter_run_tool_body_remains_direct_delegate_only" in section
    for expected in (
        "`ToolRunnerAdapter.run_tool` remains a single awaited delegate call",
        "`self._runner.run_tool`",
        "ToolExecutor production path remains unwired from `ToolRunnerAdapter`",
    ):
        assert expected in section
    for boundary in (
        "no ToolExecutor production behavior changes",
        "no tool-runner production wiring",
        "no runtime construction changes",
        "no `CTFState` ownership migration",
        "no `CTFVerifier` decision behavior changes",
        "no proof-authority behavior changes",
        "no Dispatcher changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_tool_executor_side_effect_characterization_readiness_aggregate() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "ToolExecutor side-effect characterization readiness aggregate",
    )

    assert "Status: aggregate guard recorded, production migration not approved." in section
    for required_guard in (
        "ToolExecutor legacy construction characterization guard",
        "ToolExecutor first slice characterization landing record",
        "ToolExecutor namespace re-export guard",
        "Tool runner adapter delegate-only guard hardening",
    ):
        assert required_guard in section
    for focused_test in (
        "test_p1_tool_executor_construction_stays_in_base_agent_only",
        "test_tool_executor_execute_retains_legacy_side_effect_surface_markers",
        "test_tool_executor_batch_still_delegates_through_legacy_execute",
        "test_tool_executor_module_does_not_import_tool_runner_adapter",
        "test_tools_namespace_keeps_tool_executor_legacy_reexport_only",
        "test_tool_runner_adapter_run_tool_body_remains_direct_delegate_only",
    ):
        assert focused_test in section
    for retained_surface in (
        "scope check",
        "cookie auto-inject",
        "stealth mode",
        "flag scanning",
        "missing-tool detection",
        "`execute_batch`",
    ):
        assert retained_surface in section
    assert "ToolExecutor side-effect migration remains unapproved" in section
    assert "approval package evidence, not production migration approval" in section
    for boundary in (
        "no ToolExecutor side-effect migration",
        "no tool-runner production wiring",
        "no runtime construction changes",
        "no `CTFState` ownership migration",
        "no `CTFVerifier` decision behavior changes",
        "no proof-authority behavior changes",
        "no Dispatcher changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_tool_executor_approval_transition_atomicity_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "ToolExecutor approval transition atomicity guard",
    )

    assert "Status: approval transition atomicity guard recorded, ToolExecutor migration not approved." in section
    rows = {
        row["Transition surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "approval plan": "`ToolExecutor side-effect split approval plan`",
        "readiness aggregate": "`ToolExecutor side-effect characterization readiness aggregate`",
        "approval text template": "`ToolExecutor first slice approval text template`",
        "landing matrix row": "`Core implementation landing evidence completeness matrix` ToolExecutor row",
        "sequence gate row": "`Core implementation sequence gate` ToolExecutor row",
        "landing evidence": "`ToolExecutor side-effect split implementation landing record`",
    }
    assert set(rows) == set(expected)
    for surface, heading in expected.items():
        assert rows[surface]["Required heading"] == heading
        assert rows[surface]["Current transition complete"] == "false"
        assert heading.split("`")[1] in text
    for invariant in (
        "ToolExecutor approval transition must update every listed surface in the same commit",
        "partial ToolExecutor approval transitions must fail review",
        "approval transition evidence must land before any ToolExecutor migration commit",
        "ToolExecutor landing evidence must stay incomplete until a real implementation commit exists",
    ):
        assert invariant in section
    for boundary in (
        "no ToolExecutor side-effect migration",
        "no tool-runner production wiring",
        "no runtime construction changes",
        "no `CTFState` ownership migration",
        "no `CTFVerifier` decision behavior changes",
        "no proof-authority behavior changes",
        "no Dispatcher changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_tool_executor_approval_transition_coverage_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "ToolExecutor approval transition coverage guard",
    )

    assert "Status: coverage guard recorded, ToolExecutor migration not approved." in section
    rows = {
        row["Governance surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "approval plan",
        "readiness aggregate",
        "approval text template",
        "transition atomicity",
        "landing evidence matrix",
        "sequence gate",
        "landing evidence",
        "verification evidence",
    }
    assert set(rows) == expected
    for surface, row in rows.items():
        assert row["Required before approval transition"] == "true"
        assert row["Current implementation approved"] == "false"
        assert surface in section
    for invariant in (
        "every ToolExecutor approval transition table must keep the same canonical governance surface set",
        "ToolExecutor approval transition coverage must include current side-effect characterization evidence",
        "ToolExecutor approval transition coverage must include landing evidence before migration",
        "coverage evidence must not be treated as ToolExecutor migration approval",
    ):
        assert invariant in section
    for boundary in (
        "no ToolExecutor side-effect migration",
        "no tool-runner production wiring",
        "no runtime construction changes",
        "no `CTFState` ownership migration",
        "no `CTFVerifier` decision behavior changes",
        "no proof-authority behavior changes",
        "no Dispatcher changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_tool_executor_approval_transition_evidence_consistency_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "ToolExecutor approval transition evidence consistency guard",
    )

    assert "Status: evidence consistency guard recorded, ToolExecutor migration not approved." in section
    assert "ToolExecutor migration evidence remains absent until explicit approval lands" in section
    rows = {
        row["Evidence item"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "readiness aggregate evidence": {
            "Required location": "`ToolExecutor side-effect characterization readiness aggregate`",
            "Current migration evidence present": "true",
        },
        "approval transition atomicity evidence": {
            "Required location": "`ToolExecutor approval transition atomicity guard`",
            "Current migration evidence present": "true",
        },
        "approval transition coverage evidence": {
            "Required location": "`ToolExecutor approval transition coverage guard`",
            "Current migration evidence present": "true",
        },
        "red test evidence": {
            "Required location": "`ToolExecutor side-effect split implementation landing record`",
            "Current migration evidence present": "false",
        },
        "green focused regression": {
            "Required location": "`ToolExecutor side-effect split implementation landing record`",
            "Current migration evidence present": "false",
        },
        "architecture/source regression": {
            "Required location": "`ToolExecutor side-effect split implementation landing record`",
            "Current migration evidence present": "false",
        },
        "post-push branch status": {
            "Required location": "`ToolExecutor side-effect split implementation landing record`",
            "Current migration evidence present": "false",
        },
    }
    assert set(rows) == set(expected)
    for item, expected_row in expected.items():
        assert rows[item]["Required location"] == expected_row["Required location"]
        assert rows[item]["Current migration evidence present"] == expected_row["Current migration evidence present"]
        assert expected_row["Required location"].strip("`") in text
    for invariant in (
        "ToolExecutor migration evidence must remain false until explicit approval and implementation land",
        "approval transition evidence must not be substituted for migration evidence",
        "landing evidence must include red, green, architecture regression, and post-push status before ToolExecutor migration approved changes",
        "evidence consistency must not authorize ToolExecutor side-effect migration",
    ):
        assert invariant in section
    for boundary in (
        "no ToolExecutor side-effect migration",
        "no tool-runner production wiring",
        "no runtime construction changes",
        "no `CTFState` ownership migration",
        "no `CTFVerifier` decision behavior changes",
        "no proof-authority behavior changes",
        "no Dispatcher changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_dispatcher_composition_root_first_slice_approval_text_template() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Dispatcher composition root first slice approval text template",
    )

    assert "Status: approval text template recorded, implementation not approved by this section." in section
    assert "批准 Dispatcher/composition root production wiring 第一刀" in section
    assert "composition-root wiring only after proof, state, and executor seams land" in section
    for required_clause in (
        "candidate: Dispatcher/composition root production wiring",
        "first slice: composition-root characterization or wiring plan with no production entrypoint switch",
        "scope: dispatcher/composition-root boundary characterization only",
        "rollback: revert the single implementation commit",
        "readiness evidence: Dispatcher composition root readiness characterization guard reviewed",
        "landing evidence: required",
    ):
        assert required_clause in section
    for forbidden_clause in (
        "禁止 CTFTaskDispatcher flow change",
        "禁止 composition root production wiring",
        "禁止 MCP/Web/CLI/TUI task execution path switch",
        "禁止 ToolExecutor side-effect migration",
        "禁止 CTFState ownership migration",
        "禁止 proof authority behavior change",
        "禁止 P5、crew/recovery",
    ):
        assert forbidden_clause in section
    for invariant in (
        "this template is not approval by itself",
        "approval must be sent as a user message",
        "dispatcher/composition-root work must stay last until proof, state, and executor seams land",
        "composition-root planning does not approve production entrypoint wiring",
    ):
        assert invariant in section


def test_playbook_records_core_first_slice_template_coverage_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Core first slice approval template coverage guard",
    )

    assert "Status: aggregate approval-template coverage guard recorded." in section
    expected_templates = {
        "Verifier/proof authority boundary": "Core first slice approval text template",
        "State ownership split": "State ownership first slice approval text template",
        "ToolExecutor side-effect split": "ToolExecutor first slice approval text template",
        "Dispatcher/composition root production wiring": "Dispatcher composition root first slice approval text template",
    }
    rows = {
        row["Core candidate"]: row
        for row in _markdown_table_rows(section)
    }
    assert rows.keys() == expected_templates.keys()
    for candidate, template in expected_templates.items():
        assert rows[candidate]["Approval template"] == f"`{template}`"
        assert rows[candidate]["Coverage required"] == "true"
        assert template in text
    for invariant in (
        "all core candidates must keep one copyable first-slice approval template",
        "templates do not approve implementation by themselves",
        "dispatcher/composition-root remains last until proof, state, and executor seams land",
        "missing or renamed templates must fail review",
    ):
        assert invariant in section


def test_playbook_records_core_implementation_landing_evidence_template() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Core implementation landing evidence template",
    )

    assert "Status: landing evidence template recorded, no core implementation approved by this section." in section
    assert "future approved core implementation" in section
    assert "must add a candidate-specific landing record" in section
    for field in (
        "core candidate",
        "implementation commit SHA",
        "approved scope",
        "readiness evidence reviewed",
        "files changed",
        "red test evidence",
        "focused regression result",
        "architecture/source-guard result",
        "git diff --check result",
        "post-push branch status",
        "rollback command",
        "boundary confirmation",
    ):
        assert field in section
    for candidate in (
        "Verifier/proof authority boundary",
        "State ownership split",
        "ToolExecutor side-effect split",
        "Dispatcher/composition root production wiring",
    ):
        assert candidate in section
    for boundary in (
        "one core functional point per commit",
        "no bundled proof, state, executor, dispatcher, composition-root, MCP, and entrypoint changes",
        "no implementation approval by this template",
        "readiness evidence must match the core aggregate row for the approved candidate",
        "rollback command must use the real implementation commit SHA",
    ):
        assert boundary in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py -q",
        "git diff --check",
    ):
        assert command in section


def test_playbook_records_dispatcher_landing_evidence_rollback_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Dispatcher landing evidence rollback guard",
    )

    assert "Status: rollback guard recorded, no production wiring approved." in section
    rows = {
        row["Landing field"]: row
        for row in _markdown_table_rows(section)
    }
    expected_rows = {
        "implementation commit SHA": "real full commit SHA",
        "rollback command": "`git revert <dispatcher production wiring implementation commit>`",
        "post-push branch status": "`git status --short --branch` after push",
        "scope confirmation": "one dispatcher/composition-root functional point",
    }
    assert set(rows) == set(expected_rows)
    for field, requirement in expected_rows.items():
        assert rows[field]["Required value"] == requirement
        assert rows[field]["Current complete"] == "false"
    for invariant in (
        "placeholder rollback commands are not executable rollback evidence",
        "rollback command must point at the same real implementation commit SHA",
        "dispatcher landing evidence cannot be recorded before explicit production wiring approval",
        "landing evidence must remain incomplete until implementation is pushed",
    ):
        assert invariant in section
    for boundary in (
        "no `CTFTaskDispatcher` flow changes",
        "no composition root production wiring",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no ToolExecutor changes",
        "no `CTFState` ownership split",
        "no proof-authority behavior changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_core_first_slice_recommendation_gate() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Core first implementation slice recommendation",
    )

    assert "Status: recommendation recorded, implementation not approved by this section." in section
    assert "Recommended first approval review: State ownership split" in section
    assert "Dispatcher/composition root production wiring remains last" in section
    rows = _markdown_table_rows(section)
    assert [row["Order"] for row in rows] == ["1", "2", "3", "4"]
    assert [row["Core candidate"] for row in rows] == [
        "Verifier/proof authority boundary",
        "State ownership split",
        "ToolExecutor side-effect split",
        "Dispatcher/composition root production wiring",
    ]
    for row in rows:
        if row["Core candidate"] == "Verifier/proof authority boundary":
            assert row["Implementation approved"] == "governance-only completion"
        else:
            assert row["Implementation approved"] == "false"
        assert row["First approved slice to request"]
        assert row["Why this order"]
    assert rows[0]["Implementation approved"] == "governance-only completion"
    assert rows[1]["First approved slice to request"] == "one state snapshot or claim-store ownership seam after proof authority completion"
    assert rows[3]["First approved slice to request"] == "composition-root wiring only after proof, state, and executor seams land"
    for invariant in (
        "recommendation does not approve implementation",
        "human approval must name exactly one core candidate and one first slice",
        "dispatcher/composition root work must stay last until narrower core seams land",
    ):
        assert invariant in section


def test_playbook_records_core_implementation_sequence_gate() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Core implementation sequence gate",
    )

    assert "Status: sequence gate recorded; proof completion landed, State is next approvable." in section
    rows = {
        row["Core candidate"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "Verifier/proof authority boundary": {
            "Order": "1",
            "Current gate": "governance-only completion landed",
            "Blocked by": "none",
            "Required before next candidate": "complete",
        },
        "State ownership split": {
            "Order": "2",
            "Current gate": "next approvable implementation review",
            "Blocked by": "none",
            "Required before next candidate": "landing evidence complete",
        },
        "ToolExecutor side-effect split": {
            "Order": "3",
            "Current gate": "sequence-blocked",
            "Blocked by": "Verifier/proof authority and State ownership landing evidence",
            "Required before next candidate": "landing evidence complete",
        },
        "Dispatcher/composition root production wiring": {
            "Order": "4",
            "Current gate": "sequence-blocked",
            "Blocked by": "Verifier/proof authority, State ownership, and ToolExecutor landing evidence",
            "Required before next candidate": "landing evidence complete",
        },
    }
    assert set(rows) == set(expected)
    for candidate, expected_values in expected.items():
        for column, value in expected_values.items():
            assert rows[candidate][column] == value
    for invariant in (
        "only the first unlanded candidate may be reviewed for implementation approval",
        "a later core candidate cannot skip an incomplete earlier landing record",
        "sequence gate changes require a dedicated governance commit before implementation",
        "sequence gate is not implementation approval",
    ):
        assert invariant in section
    for boundary in (
        "no proof-authority behavior changes",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root production wiring",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_core_first_slice_approval_text_template() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Core first slice approval text template",
    )

    assert "Status: approval text template recorded, implementation not approved by this section." in section
    assert "Copyable approval text for the recommended first slice" in section
    assert "批准 Verifier/proof authority boundary 第一刀" in section
    assert "proof-authority boundary characterization or adapter wrapper with no decision behavior change" in section
    assert "独立 TDD、独立 commit/push" in section
    assert "禁止 State ownership split、ToolExecutor、Dispatcher、composition root、MCP production wiring、Web/CLI/TUI task wiring、proof behavior change、P5、crew/recovery" in section
    for required_clause in (
        "candidate: Verifier/proof authority boundary",
        "first slice: proof-authority boundary characterization or adapter wrapper with no decision behavior change",
        "scope: verifier/proof-authority boundary only",
        "rollback: revert the single implementation commit",
        "readiness evidence: Proof authority characterization readiness aggregate reviewed",
        "landing evidence: required",
    ):
        assert required_clause in section
    for invariant in (
        "this template is not approval by itself",
        "approval must be sent as a user message",
        "approval text must not authorize bundled core changes",
        "readiness evidence does not approve implementation by itself",
    ):
        assert invariant in section


def test_playbook_core_first_slice_template_blocks_adapter_production_wiring() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Core first slice approval text template",
    )

    for readiness_guard in (
        "Proof authority adapter import unwired guard",
        "Verifier adapter import unwired guard",
    ):
        assert readiness_guard in section

    for forbidden_clause in (
        "禁止 proof authority production wiring",
        "禁止 verifier production wiring",
        "禁止 verifier decision behavior change",
    ):
        assert forbidden_clause in section

    assert "adapter wrapper does not mean production wiring approval" in section
    assert "verifier/proof-authority adapter import guards must remain green" in section


def test_playbook_records_proof_adapter_wrapper_delegate_only_preapproval_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Proof adapter wrapper delegate-only pre-approval guard",
    )

    assert "Status: delegate-only guard recorded, implementation not approved." in section
    for adapter_scope in (
        "VerifierAdapter.review_claim",
        "ProofAuthorityAdapter.append_proof_record",
        "ProofAuthorityAdapter.confirm_claim",
    ):
        assert adapter_scope in section
    for invariant in (
        "adapter wrappers remain delegate-only skeletons",
        "adapter wrapper approval is not production wiring approval",
        "no verifier decision behavior changes",
        "no proof-authority behavior changes",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no composition root changes",
    ):
        assert invariant in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_verifier_adapter.py tests/unit/test_proof_authority_adapter.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/agents/test_p1_source_guards.py tests/unit/test_clean_architecture_migration_playbook.py -q",
        "git diff --check",
    ):
        assert command in section


def test_playbook_records_verifier_proof_authority_first_slice_landing() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Verifier proof authority boundary first slice landing record",
    )

    assert "Status: first slice landed after explicit approval." in section
    assert "Verifier/proof authority boundary: first slice landed" in section
    for approved_scope in (
        "proof-authority boundary characterization",
        "adapter wrappers remain delegate-only",
        "VerifierAdapter.review_claim",
        "ProofAuthorityAdapter.append_proof_record",
        "ProofAuthorityAdapter.confirm_claim",
    ):
        assert approved_scope in section
    for forbidden_scope in (
        "no proof authority production wiring",
        "no verifier production wiring",
        "no verifier decision behavior changes",
        "no proof-authority behavior changes",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no composition root changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert forbidden_scope in section
    for required_evidence in (
        "Proof authority characterization readiness aggregate reviewed",
        "Proof adapter wrapper delegate-only pre-approval guard reviewed",
        "Rollback command: git revert <Verifier proof authority first slice commit>",
    ):
        assert required_evidence in section


def test_playbook_records_p1b_proof_adapter_delegate_guard_hardening_landing() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "P1-B proof adapter delegate guard hardening landing record",
    )

    assert "Status: guard hardening landed after explicit approval." in section
    assert "Candidate P1-B Verifier/proof authority boundary second slice: landed" in section
    for guarded_scope in (
        "VerifierAdapter.review_claim remains a single awaited delegate call",
        "ProofAuthorityAdapter.append_proof_record remains a single delegate call",
        "ProofAuthorityAdapter.confirm_claim remains a single delegate call",
        "no legacy `CTFVerifier` construction",
        "no legacy `CTFState` calls",
        "no proof authority production wiring",
        "no verifier production wiring",
        "no verifier decision behavior changes",
        "no proof-authority behavior changes",
    ):
        assert guarded_scope in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_verifier_adapter.py tests/unit/test_proof_authority_adapter.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/agents/test_p1_source_guards.py tests/unit/agents/test_p1_claim_invariants.py tests/unit/test_adapter_boundary_skeleton.py tests/unit/test_clean_architecture_migration_playbook.py -q",
        "git diff --check",
    ):
        assert command in section


def test_playbook_records_verifier_proof_authority_partial_landing_reconciliation_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Verifier proof authority partial landing reconciliation guard",
    )

    assert "Status: reconciliation guard resolved by governance-only completion transition." in section
    for required_heading in (
        "Verifier proof authority boundary first slice landing record",
        "P1-B proof adapter delegate guard hardening landing record",
        "Core implementation landing evidence completeness matrix",
        "Core implementation sequence gate",
    ):
        assert required_heading in section
    rows = {
        row["Evidence surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected_rows = {
        "first slice landing": {
            "Required heading": "`Verifier proof authority boundary first slice landing record`",
            "Counts as core landing complete": "false",
        },
        "P1-B delegate hardening": {
            "Required heading": "`P1-B proof adapter delegate guard hardening landing record`",
            "Counts as core landing complete": "false",
        },
        "core landing matrix row": {
            "Required heading": "`Core implementation landing evidence completeness matrix`",
            "Counts as core landing complete": "false",
        },
        "sequence gate row": {
            "Required heading": "`Core implementation sequence gate`",
            "Counts as core landing complete": "false",
        },
    }
    assert set(rows) == set(expected_rows)
    for surface, expected_values in expected_rows.items():
        for column, value in expected_values.items():
            assert rows[surface][column] == value
    for invariant in (
        "adapter and guard hardening landings do not complete the core production landing row",
        "State ownership split remained sequence-blocked until Verifier/proof authority boundary landing evidence was complete",
        "the proof boundary unblocks State only through the dedicated governance update that sets the matching matrix row complete",
        "partial landing reconciliation is not implementation approval",
    ):
        assert invariant in section
    for boundary in (
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no proof authority production wiring",
        "no verifier production wiring",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_verifier_proof_authority_core_landing_completion_transition_record() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Verifier proof authority core landing completion transition record",
    )

    assert "Status: governance-only completion transition landed after explicit approval." in section
    assert "Verifier/proof authority boundary core landing completion: approved" in section
    for expected in (
        "approval type: governance-only completion transition",
        "no production proof behavior changed",
        "no verifier decision behavior changed",
        "no proof authority production wiring",
        "State ownership split is next approvable for review only",
        "Rollback command: git revert <Verifier proof authority core landing completion transition commit>",
    ):
        assert expected in section
    for evidence in (
        "Verifier proof authority core landing completion approval checklist",
        "Verifier proof authority completion approval package aggregate guard",
        "Core implementation landing evidence completeness matrix",
        "Core implementation sequence gate",
        "State ownership unlock blocked until proof completion guard",
    ):
        assert evidence in section
    for command in (
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py -q",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/unit/agents/test_p1_source_guards.py tests/unit/agents/test_p1_claim_invariants.py tests/unit/test_adapter_boundary_skeleton.py tests/unit/test_state_store_adapter.py tests/unit/test_claim_store_adapter.py tests/unit/test_verifier_adapter.py tests/unit/test_proof_authority_adapter.py -q",
        "git diff --check",
    ):
        assert command in section


def test_playbook_records_verifier_proof_authority_core_landing_completion_approval_checklist() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Verifier proof authority core landing completion approval checklist",
    )

    assert "Status: governance-only completion approved and transitioned." in section
    rows = {
        row["Review surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "core landing matrix proof row": {
            "Required evidence": "`Core implementation landing evidence completeness matrix` proof row",
            "Current state": "complete",
        },
        "sequence gate proof row": {
            "Required evidence": "`Core implementation sequence gate` proof row",
            "Current state": "landed",
        },
        "partial landing reconciliation": {
            "Required evidence": "`Verifier proof authority partial landing reconciliation guard`",
            "Current state": "reconciled",
        },
        "human approval decision": {
            "Required evidence": "explicit proof-boundary completion approval or next implementation slice approval",
            "Current state": "approved governance-only completion",
        },
    }
    assert set(rows) == set(expected)
    for surface, expected_values in expected.items():
        for column, value in expected_values.items():
            assert rows[surface][column] == value
    for required_phrase in (
        "批准 Verifier/proof authority boundary core landing completion",
        "批准 Verifier/proof authority boundary next implementation slice",
        "completion approval must name whether it is governance-only completion or implementation work",
        "completion approval must not unlock State ownership without updating the matrix and sequence gate in the same functional commit",
    ):
        assert required_phrase in section
    for boundary in (
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no proof authority production wiring",
        "no verifier production wiring",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_verifier_proof_authority_completion_transition_atomicity_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Verifier proof authority completion transition atomicity guard",
    )

    assert "Status: transition complete; governance-only completion landed." in section
    for required_heading in (
        "Verifier proof authority core landing completion approval checklist",
        "Verifier proof authority partial landing reconciliation guard",
        "Core implementation landing evidence completeness matrix",
        "Core implementation sequence gate",
        "State ownership unlock blocked until proof completion guard",
    ):
        assert required_heading in section
    rows = {
        row["Transition surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "proof completion approval": {
            "Required update in same commit": "explicit approval state recorded",
            "Current transition complete": "true",
        },
        "proof landing matrix row": {
            "Required update in same commit": "proof row complete",
            "Current transition complete": "true",
        },
        "sequence gate proof row": {
            "Required update in same commit": "proof row landed",
            "Current transition complete": "true",
        },
        "State unlock guard": {
            "Required update in same commit": "State impact reconciled",
            "Current transition complete": "true",
        },
    }
    assert set(rows) == set(expected)
    for surface, expected_values in expected.items():
        for column, value in expected_values.items():
            assert rows[surface][column] == value
    for invariant in (
        "proof completion cannot be marked complete by updating only the checklist",
        "proof completion transition must update matrix, sequence gate, and State unlock guard together",
        "partial completion transitions must fail review",
        "State remains blocked until the proof completion transition commit is complete",
    ):
        assert invariant in section
    for boundary in (
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no proof authority production wiring",
        "no verifier production wiring",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_verifier_proof_authority_completion_rollback_evidence_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Verifier proof authority completion rollback evidence guard",
    )

    assert "Status: rollback evidence complete for governance-only completion." in section
    for required_heading in (
        "Verifier proof authority core landing completion approval checklist",
        "Verifier proof authority completion transition atomicity guard",
        "Core implementation landing evidence completeness matrix",
        "Core implementation sequence gate",
    ):
        assert required_heading in section
    rows = {
        row["Landing evidence field"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "implementation commit SHA": {
            "Required value": "reported in completion report for this commit",
            "Current complete": "true",
        },
        "rollback command": {
            "Required value": "`git revert <proof completion implementation commit>`",
            "Current complete": "true",
        },
        "post-push branch status": {
            "Required value": "`git status --short --branch` after push",
            "Current complete": "true",
        },
        "State unlock impact": {
            "Required value": "matrix and sequence gate updated in same commit",
            "Current complete": "true",
        },
    }
    assert set(rows) == set(expected)
    for field, expected_values in expected.items():
        for column, value in expected_values.items():
            assert rows[field][column] == value
    for invariant in (
        "placeholder rollback commands are not proof completion evidence",
        "rollback command must point at the same real proof completion commit SHA",
        "proof completion landing evidence cannot be recorded before explicit completion approval",
        "State unlock impact remains incomplete until proof completion is pushed",
    ):
        assert invariant in section
    for boundary in (
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no proof authority production wiring",
        "no verifier production wiring",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_verifier_proof_authority_completion_approval_package_aggregate_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Verifier proof authority completion approval package aggregate guard",
    )

    assert "Status: aggregate complete for governance-only proof completion." in section
    required_surfaces = {
        "partial landing reconciliation": "`Verifier proof authority partial landing reconciliation guard`",
        "completion checklist": "`Verifier proof authority core landing completion approval checklist`",
        "transition atomicity": "`Verifier proof authority completion transition atomicity guard`",
        "rollback evidence": "`Verifier proof authority completion rollback evidence guard`",
        "completion transition record": "`Verifier proof authority core landing completion transition record`",
        "State unlock guard": "`State ownership unlock blocked until proof completion guard`",
    }
    rows = {
        row["Approval package surface"]: row
        for row in _markdown_table_rows(section)
    }
    assert set(rows) == set(required_surfaces)
    for surface, heading in required_surfaces.items():
        assert rows[surface]["Required heading"] == heading
        assert rows[surface]["Current complete"] == "true"
    for invariant in (
        "proof completion approval package is not implementation approval",
        "all package surfaces must be complete before State can be unblocked",
        "completion approval must preserve proof-authority and verifier behavior unless separately approved",
        "package aggregate evidence cannot replace a real proof completion landing commit",
    ):
        assert invariant in section
    for boundary in (
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no proof authority production wiring",
        "no verifier production wiring",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_verifier_proof_authority_completion_approval_text_template() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Verifier proof authority completion approval text template",
    )

    assert "Status: approval text template recorded, completion approval not granted by this section." in section
    for required_phrase in (
        "批准 Verifier/proof authority boundary core landing completion",
        "candidate: Verifier/proof authority boundary",
        "approval type: governance-only completion transition",
        "scope: mark proof boundary core landing complete only if the aggregate package is complete",
        "required same-commit updates: completion checklist, completion aggregate, landing matrix, sequence gate, State unlock guard",
        "rollback: revert the single proof completion transition commit",
        "verification: playbook tests, proof/source guards, adapter tests, git diff --check",
    ):
        assert required_phrase in section
    for forbidden_clause in (
        "禁止 proof-authority behavior changes",
        "禁止 verifier decision behavior changes",
        "禁止 proof authority production wiring",
        "禁止 verifier production wiring",
        "禁止 CTFState ownership split",
        "禁止 ToolExecutor、Dispatcher、MCP/Web/CLI/TUI、composition root、P5、crew/recovery",
    ):
        assert forbidden_clause in section
    for invariant in (
        "this template is not approval by itself",
        "completion transition is governance-only unless the user separately approves implementation work",
        "State remains blocked unless the same commit updates the matrix and sequence gate",
        "approval must not bundle a next implementation slice",
    ):
        assert invariant in section


def test_playbook_records_state_unlock_blocked_until_proof_completion_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "State ownership unlock blocked until proof completion guard",
    )

    assert "Status: proof completion landed; State ownership review is next approvable." in section
    for required_heading in (
        "Verifier proof authority core landing completion approval checklist",
        "Verifier proof authority partial landing reconciliation guard",
        "Core implementation landing evidence completeness matrix",
        "Core implementation sequence gate",
        "State ownership characterization readiness aggregate",
    ):
        assert required_heading in section
    rows = {
        row["Gate surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected = {
        "proof completion approval": {
            "Current state": "approved governance-only completion",
            "State impact": "unblocks State review",
        },
        "proof core landing row": {
            "Current state": "complete",
            "State impact": "unblocks State review",
        },
        "sequence gate proof row": {
            "Current state": "landed",
            "State impact": "unblocks State review",
        },
        "State ownership split": {
            "Current state": "next approvable implementation review",
            "State impact": "requires separate State approval",
        },
    }
    assert set(rows) == set(expected)
    for surface, expected_values in expected.items():
        for column, value in expected_values.items():
            assert rows[surface][column] == value
    for invariant in (
        "State ownership split can now be reviewed for implementation after proof completion",
        "State unlock required proof completion approval and matrix/sequence gate update in the same functional commit",
        "State readiness aggregate is not State implementation approval",
        "partial proof landings do not unlock State",
    ):
        assert invariant in section
    for boundary in (
        "no State ownership split",
        "no state-store production wiring",
        "no claim-store production wiring",
        "no proof-authority behavior changes",
        "no verifier decision behavior changes",
        "no ToolExecutor changes",
        "no CTFTaskDispatcher flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_task_ingress_production_wiring_a_landing() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Task ingress production wiring A implementation landing record",
    )

    assert "Status: implementation landed for MCP task submission ingress only." in section
    assert "Task ingress production wiring A: implementation landed" in section
    assert "flaghunter/mcp/server/mcp_tools.py::run_task" in section
    assert "flaghunter/mcp/server/mcp_tools.py::run_task_async" in section
    assert "SubmitTaskIngress" in section
    assert "raw instructions" in section
    assert "do not add ingress text to external MCP" in section
    for boundary in (
        "no MCP router changes",
        "no `_drive_task` changes",
        "no `_make_agent` changes",
        "no Web/CLI/TUI production wiring",
        "no ToolExecutor changes",
        "no `CTFVerifier` proof behavior changes",
        "no `CTFState` ownership split",
        "no `CTFTaskDispatcher` flow changes",
        "no composition root changes",
        "no proof authority behavior changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_task_ingress_production_wiring_b_landing() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Task ingress production wiring B implementation landing record",
    )

    assert "Status: implementation landed for Web post_task task creation ingress only." in section
    assert "Task ingress production wiring B: implementation landed" in section
    assert "flaghunter/interface/web_server.py::post_task" in section
    assert "SubmitTaskIngress" in section
    assert "raw" in section
    assert "does not add ingress fields to the external response" in section
    for boundary in (
        "no MCP follow-up changes",
        "no MCP router changes",
        "no `_drive_task` changes",
        "no `_make_agent` changes",
        "no CLI/TUI production wiring",
        "no other Web handler production wiring",
        "no ToolExecutor changes",
        "no `CTFVerifier` proof behavior changes",
        "no `CTFState` ownership split",
        "no `CTFTaskDispatcher` flow changes",
        "no composition root changes",
        "no proof authority behavior changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_parses_task_ingress_service_migration_approval_flag_consistency_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Task ingress service contract migration approval flag consistency guard",
    )

    assert "Status: approval consistency guard updated, implementation landed." in section
    assert "Task ingress service contract migration plan" in section
    assert "Task ingress service contract migration pre-approval guard" in section
    assert "Task ingress service contract migration readiness checklist" in section
    assert "no production wiring approval by implication" in section
    assert "no production wiring" in section

    plan = _heading_section_text(text, "Task ingress service contract migration plan")
    pre_approval = _heading_section_text(
        text,
        "Task ingress service contract migration pre-approval guard",
    )
    readiness = _heading_section_text(
        text,
        "Task ingress service contract migration readiness checklist",
    )

    assert "Status: implementation approved and landed." in plan
    assert "Status: retired by task ingress service contract migration landing." in pre_approval
    assert "Status: implementation landed after explicit approval." in readiness

    status_rows = {
        row["Governance surface"]: row
        for row in _markdown_table_rows(section)
    }
    expected_surfaces = {
        "plan",
        "pre-approval guard",
        "readiness checklist",
    }
    assert set(status_rows) == expected_surfaces
    for row in status_rows.values():
        assert row["Implementation approved"] == "true"
        assert row["Service migration landed"] == "true"

    assert "no production wiring approval by implication" in section


def test_playbook_records_task_ingress_service_migration_landing_record_template() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Task ingress service contract migration landing record template",
    )

    assert "Status: implementation landing record completed." in section
    assert "Task ingress service contract migration implementation landing record" in section
    assert "Task ingress service contract migration: implementation landed" in section
    for required_field in (
        "Implementation commit SHA",
        "Target",
        "Behavior equivalence evidence",
        "Port payload compatibility evidence",
        "Neutral service contract evidence",
        "Pre-approval guard update",
        "Focused regression result",
        "Architecture/source-guard result",
        "git diff --check result",
        "Post-push branch status",
        "Rollback command",
        "Boundary confirmation",
    ):
        assert required_field in section
    assert "Rollback command: git revert <Task ingress service contract migration implementation commit>" in section
    assert "old/new output equivalence" in section
    assert "raw `instructions` in the injected port request payload" in section
    assert "does not authorize task ingress production wiring" in section
    for boundary in (
        "no production wiring",
        "no MCP server changes",
        "no dispatcher loop changes",
        "no ToolExecutor changes",
        "no composition root changes",
        "no proof authority behavior changes",
        "no P5 implementation",
    ):
        assert boundary in section


def test_playbook_parses_task_ingress_service_rollback_placeholder_consistency_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Task ingress service rollback placeholder consistency guard",
    )

    assert "Status: rollback placeholder guard updated, implementation landed." in section
    assert "rollback scoped to the single task ingress service migration" in section
    assert "exact commit SHA is reported in the completion report" in section

    rows = {
        row["Scope"]: row
        for row in _markdown_table_rows(section)
    }
    assert set(rows) == {"task ingress service migration"}

    row = rows["task ingress service migration"]
    assert row["Rollback command"] == "`git revert <Task ingress service contract migration implementation commit>`"
    assert row["Applies after"] == "service migration commit lands"
    assert row["Current executable"] == "true"
    assert not re.search(r"\b[0-9a-f]{7,40}\b", row["Rollback command"])

    landing_template = _heading_section_text(
        text,
        "Task ingress service contract migration landing record template",
    )
    assert "Rollback command: git revert <Task ingress service contract migration implementation commit>" in landing_template


def test_playbook_parses_task_ingress_service_approval_transition_atomicity_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Task ingress service approval transition atomicity guard",
    )

    assert "Status: approval transition atomicity guard recorded, implementation not approved." in section
    assert "approval transition evidence must land before implementation" in section
    assert "partial approval updates must fail review" in section
    assert "no service migration is authorized by this atomicity guard" in section

    required_rows = {
        row["Atomic update"]: row["Required section"]
        for row in _markdown_table_rows(section)
    }
    assert required_rows == {
        "plan approval status": "`Task ingress service contract migration plan`",
        "pre-approval guard status": "`Task ingress service contract migration pre-approval guard`",
        "readiness approval status": "`Task ingress service contract migration readiness checklist`",
        "approval flag table": "`Task ingress service contract migration approval flag consistency guard`",
        "landing evidence template": "`Task ingress service contract migration landing record template`",
        "rollback placeholder": "`Task ingress service rollback placeholder consistency guard`",
        "verification evidence": "`Task ingress service contract migration readiness checklist`",
    }

    for heading in (
        "Task ingress service contract migration plan",
        "Task ingress service contract migration pre-approval guard",
        "Task ingress service contract migration readiness checklist",
        "Task ingress service contract migration approval flag consistency guard",
        "Task ingress service contract migration landing record template",
        "Task ingress service rollback placeholder consistency guard",
    ):
        assert heading in text


def test_playbook_parses_task_ingress_service_approval_transition_coverage_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Task ingress service approval transition coverage guard",
    )

    assert "Status: approval transition coverage guard recorded, implementation not approved." in section
    assert "every approval transition table must keep the same canonical governance surface set" in section
    assert "no service migration is authorized by this coverage guard" in section

    rows = {
        row["Governance surface"]: row
        for row in _markdown_table_rows(section)
    }
    assert rows == {
        "plan approval status": {
            "Governance surface": "plan approval status",
            "Required before approval transition": "true",
            "Current implementation approved": "false",
        },
        "pre-approval guard status": {
            "Governance surface": "pre-approval guard status",
            "Required before approval transition": "true",
            "Current implementation approved": "false",
        },
        "readiness approval status": {
            "Governance surface": "readiness approval status",
            "Required before approval transition": "true",
            "Current implementation approved": "false",
        },
        "approval flag table": {
            "Governance surface": "approval flag table",
            "Required before approval transition": "true",
            "Current implementation approved": "false",
        },
        "landing evidence template": {
            "Governance surface": "landing evidence template",
            "Required before approval transition": "true",
            "Current implementation approved": "false",
        },
        "rollback placeholder": {
            "Governance surface": "rollback placeholder",
            "Required before approval transition": "true",
            "Current implementation approved": "false",
        },
        "verification evidence": {
            "Governance surface": "verification evidence",
            "Required before approval transition": "true",
            "Current implementation approved": "false",
        },
    }

    atomicity_guard = _heading_section_text(
        text,
        "Task ingress service approval transition atomicity guard",
    )
    for surface in rows:
        assert surface in atomicity_guard


def test_playbook_parses_task_ingress_service_approval_transition_evidence_consistency_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Task ingress service approval transition evidence consistency guard",
    )

    assert "Status: approval transition evidence consistency guard updated, implementation landed." in section
    assert "Approval evidence is present for the approved task ingress service migration" in section
    assert "no task ingress production wiring is authorized by this evidence guard" in section

    rows = {
        row["Evidence item"]: row
        for row in _markdown_table_rows(section)
    }
    assert rows == {
        "red test evidence": {
            "Evidence item": "red test evidence",
            "Required location": "`Task ingress service contract migration readiness checklist`",
            "Current approval evidence present": "true",
        },
        "green focused regression": {
            "Evidence item": "green focused regression",
            "Required location": "`Task ingress service contract migration readiness checklist`",
            "Current approval evidence present": "true",
        },
        "architecture/source regression": {
            "Evidence item": "architecture/source regression",
            "Required location": "`Task ingress service contract migration readiness checklist`",
            "Current approval evidence present": "true",
        },
        "approval flag update evidence": {
            "Evidence item": "approval flag update evidence",
            "Required location": "`Task ingress service contract migration approval flag consistency guard`",
            "Current approval evidence present": "true",
        },
        "landing record placeholder": {
            "Evidence item": "landing record placeholder",
            "Required location": "`Task ingress service contract migration landing record template`",
            "Current approval evidence present": "true",
        },
        "rollback placeholder evidence": {
            "Evidence item": "rollback placeholder evidence",
            "Required location": "`Task ingress service rollback placeholder consistency guard`",
            "Current approval evidence present": "true",
        },
        "post-push branch status": {
            "Evidence item": "post-push branch status",
            "Required location": "`Task ingress service contract migration readiness checklist`",
            "Current approval evidence present": "true",
        },
    }

    for forbidden in (
        "Task ingress production wiring | true",
        "MCP production wiring | true",
    ):
        assert forbidden not in section


def test_playbook_parses_task_ingress_service_landing_status_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Task ingress service landing status guard",
    )

    assert "Status: landing status guard updated, service migration landed." in section
    assert "no task ingress production wiring is authorized by this landing status guard" in section

    rows = {
        row["Landing surface"]: row
        for row in _markdown_table_rows(section)
    }
    assert rows == {
        "landing record template": {
            "Landing surface": "landing record template",
            "Required location": "`Task ingress service contract migration landing record template`",
            "Current landed": "true",
        },
        "rollback placeholder": {
            "Landing surface": "rollback placeholder",
            "Required location": "`Task ingress service rollback placeholder consistency guard`",
            "Current landed": "true",
        },
        "approval evidence": {
            "Landing surface": "approval evidence",
            "Required location": "`Task ingress service approval transition evidence consistency guard`",
            "Current landed": "true",
        },
    }

    landing_template = _heading_section_text(
        text,
        "Task ingress service contract migration landing record template",
    )
    rollback_guard = _heading_section_text(
        text,
        "Task ingress service rollback placeholder consistency guard",
    )
    evidence_guard = _heading_section_text(
        text,
        "Task ingress service approval transition evidence consistency guard",
    )

    assert "Status: implementation landing record completed." in landing_template
    rollback_rows = _markdown_table_rows(rollback_guard)
    assert rollback_rows[0]["Current executable"] == "true"
    for row in _markdown_table_rows(evidence_guard):
        assert row["Current approval evidence present"] == "true"


def test_playbook_records_proof_authority_write_surface_characterization_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Proof authority write surface characterization guard",
    )

    assert "Status: characterization guard recorded, no proof behavior changed." in section
    assert (
        "tests/unit/agents/test_p1_source_guards.py::"
        "test_p1_proof_authority_write_calls_stay_in_verifier_and_state_only"
    ) in section
    for allowed_surface in (
        "`CTFVerifier._sync_flag_claim` -> `CTFState.upgrade_claim_to_verified`",
        "`CTFVerifier._append_flag_verification_record` -> "
        "`CTFState.append_verification_record`",
        "`CTFVerifier._ensure_result_trace` -> `CTFState.record_verification_receipt`",
        "`flaghunter/agents/pa_agent/verifier.py`",
        "`flaghunter/agents/pa_agent/ctf_state.py`",
        "`upgrade_claim_to_verified`",
        "`append_verification_record`",
        "`record_verification_receipt`",
    ):
        assert allowed_surface in section
    for boundary in (
        "no proof-authority behavior changes",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_verified_decision_reference_characterization_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Verified decision reference characterization guard",
    )

    assert "Status: characterization guard recorded, no proof behavior changed." in section
    assert (
        "tests/unit/agents/test_p1_source_guards.py::"
        "test_p1_verified_decision_references_stay_in_verifier_and_state_only"
    ) in section
    for allowed_surface in (
        "`CTFVerifier._append_flag_verification_record`",
        "`CTFVerifier._record_decision_for_result`",
        "`CTFState._has_sufficient_verified_record`",
        "`VerificationDecision.VERIFIED`",
        "`flaghunter/agents/pa_agent/verifier.py`",
        "`flaghunter/agents/pa_agent/ctf_state.py`",
    ):
        assert allowed_surface in section
    for boundary in (
        "no proof-authority behavior changes",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_proof_authority_port_action_unwired_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Proof authority port action unwired guard",
    )

    assert "Status: source guard recorded, no production wiring approved." in section
    assert (
        "tests/unit/agents/test_p1_source_guards.py::"
        "test_p1_proof_authority_port_actions_remain_unwired_outside_port_and_adapter"
    ) in section
    for allowed_surface in (
        "`ProofAuthorityPort.append_proof_record`",
        "`ProofAuthorityPort.confirm_claim`",
        "`ProofAuthorityAdapter.append_proof_record`",
        "`ProofAuthorityAdapter.confirm_claim`",
        "`flaghunter/ports/proof_authority.py`",
        "`flaghunter/adapters/proof/proof_authority_adapter.py`",
        "`append_proof_record`",
        "`confirm_claim`",
    ):
        assert allowed_surface in section
    for boundary in (
        "no proof-authority behavior changes",
        "no proof authority production wiring",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_proof_authority_adapter_import_unwired_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Proof authority adapter import unwired guard",
    )

    assert "Status: source guard recorded, no production wiring approved." in section
    assert (
        "tests/unit/agents/test_p1_source_guards.py::"
        "test_p1_proof_authority_adapter_stays_unwired_from_production_imports"
    ) in section
    for allowed_surface in (
        "`flaghunter/adapters/proof/__init__.py`",
        "`flaghunter/adapters/proof/proof_authority_adapter.py`",
        "`ProofAuthorityAdapter`",
        "`ProofAuthorityPort`",
    ):
        assert allowed_surface in section
    for boundary in (
        "no proof-authority behavior changes",
        "no proof authority production wiring",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_verifier_adapter_import_unwired_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Verifier adapter import unwired guard",
    )

    assert "Status: source guard recorded, no production wiring approved." in section
    assert (
        "tests/unit/agents/test_p1_source_guards.py::"
        "test_p1_verifier_adapter_stays_unwired_from_production_imports"
    ) in section
    for allowed_surface in (
        "`flaghunter/adapters/proof/__init__.py`",
        "`flaghunter/adapters/proof/verifier_adapter.py`",
        "`VerifierAdapter`",
        "`VerifierPort` remains allowed through approved application-service ports",
    ):
        assert allowed_surface in section
    for boundary in (
        "no verifier production wiring",
        "no proof-authority behavior changes",
        "no proof authority production wiring",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_proof_adapter_namespace_reexport_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Proof adapter namespace re-export guard",
    )

    assert "Status: namespace guard landed, no production wiring approved." in section
    assert "test_proof_adapter_namespace_is_reexport_only" in section
    for locked_surface in (
        "`flaghunter/adapters/proof/__init__.py`",
        "`ProofAuthorityAdapter`",
        "`VerifierAdapter`",
        "`__all__ = [\"ProofAuthorityAdapter\", \"VerifierAdapter\"]`",
        "only relative adapter-module imports",
        "no `ProofAuthorityPort` re-export",
        "no `VerifierPort` re-export",
    ):
        assert locked_surface in section
    for boundary in (
        "no verifier production wiring",
        "no proof authority production wiring",
        "no proof-authority behavior changes",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_ctf_verifier_legacy_construction_characterization_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "CTFVerifier legacy construction characterization guard",
    )

    assert "Status: characterization guard recorded, no verifier behavior changed." in section
    assert (
        "tests/unit/agents/test_p1_source_guards.py::"
        "test_p1_ctf_verifier_construction_stays_legacy_dispatcher_only"
    ) in section
    for allowed_surface in (
        "`flaghunter/agents/pa_agent/ctf_dispatcher.py`",
        "`CTFTaskDispatcher.__init__`",
        "`CTFVerifier`",
        "legacy dispatcher construction remains the only production construction surface",
    ):
        assert allowed_surface in section
    for boundary in (
        "no verifier production wiring",
        "no proof-authority behavior changes",
        "no proof authority production wiring",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_proof_authority_characterization_readiness_aggregate() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Proof authority characterization readiness aggregate",
    )

    assert "Status: aggregate guard recorded, implementation not approved." in section
    for required_guard in (
        "Proof authority write surface characterization guard",
        "Verified decision reference characterization guard",
        "Proof authority port action unwired guard",
        "Proof authority adapter import unwired guard",
        "Verifier adapter import unwired guard",
        "CTFVerifier legacy construction characterization guard",
    ):
        assert required_guard in section
    for focused_test in (
        "test_p1_proof_authority_write_calls_stay_in_verifier_and_state_only",
        "test_p1_verified_decision_references_stay_in_verifier_and_state_only",
        "test_p1_proof_authority_port_actions_remain_unwired_outside_port_and_adapter",
        "test_p1_proof_authority_adapter_stays_unwired_from_production_imports",
        "test_p1_verifier_adapter_stays_unwired_from_production_imports",
        "test_p1_ctf_verifier_construction_stays_legacy_dispatcher_only",
    ):
        assert focused_test in section
    assert "Verifier/proof authority boundary implementation remains unapproved" in section
    assert "approval package evidence, not implementation approval" in section
    for boundary in (
        "no proof-authority behavior changes",
        "no proof authority production wiring",
        "no `CTFState` ownership split",
        "no ToolExecutor changes",
        "no `CTFTaskDispatcher` flow changes",
        "no MCP production wiring",
        "no Web/CLI/TUI task wiring changes",
        "no composition root changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section


def test_playbook_records_web_provenance_trace_payload_debt_characterization() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Web provenance/trace payload test debt characterization landing record",
    )

    assert "Status: characterization debt fixed for Web provenance and trace payload read paths." in section
    assert "Web provenance/trace payload test debt characterization: implementation landed" in section
    assert "flaghunter/interface/blackboard_lite.py" in section
    assert "tests/unit/interface/test_web_server.py" in section
    assert "`artifactUrl` and `exploitType`" in section
    assert "10 existing" in section
    for evidence in (
        "test_task_detail_surfaces_exploit_provenance_from_source_leak_observation",
        "test_task_detail_surfaces_exploit_provenance_from_local_source_hint",
        "test_build_trace_payload_projects_artifacts_checkpoint_and_outcomes_from_session_context",
        "test_build_trace_payload_projects_dispatcher_started_outcome_event",
        "test_build_trace_payload_projects_dispatcher_started_summary_with_local_source_exploit_truth",
        "test_build_trace_payload_projects_control_action_outcome_events",
        "test_build_trace_payload_surfaces_exploit_provenance_summary",
        "test_build_trace_payload_keeps_local_source_hint_exploit_provenance_in_outcome_events",
        "test_build_trace_payload_projects_verification_and_finish_summaries_with_local_source_exploit_truth",
        "test_build_trace_payload_projects_recovery_decision_summary_with_local_source_exploit_truth",
    ):
        assert evidence in section
    for boundary in (
        "no Task ingress wiring expansion",
        "no MCP changes",
        "no ToolExecutor changes",
        "no `CTFVerifier` proof behavior changes",
        "no `CTFState` ownership split",
        "no `CTFTaskDispatcher` flow changes",
        "no composition root changes",
        "no proof authority behavior changes",
        "no P5 implementation",
        "no crew/recovery changes",
    ):
        assert boundary in section
