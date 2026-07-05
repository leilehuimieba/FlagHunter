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
        assert row["Current implementation approval"] == "false"
        assert row["Required coverage"] == "acceptance, drift, package, ledger, readiness, source-map, checklist, landing evidence"
        assert ledger_rows[candidate]["approvedForImplementation"] == "false"
        assert readiness_rows[candidate]["Implementation approved"] == "false"
        assert evidence_rows[candidate]["Implementation landed"] == "false"


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


def test_playbook_parses_deferred_mcp_explicit_wiring_approval_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Deferred MCP explicit wiring approval guard")

    assert "Status: explicit MCP approval guard recorded, no implementation approved by this section." in section
    assert "Web projection equivalence lands plus explicit MCP production wiring approval" in section
    assert "confirm explicit MCP production wiring approval" in section
    assert "no MCP production wiring without explicit approval" in section
    assert "no production path switch" in section

    expected_gate = "Web projection equivalence lands plus explicit MCP production wiring approval"
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
    assert "explicit MCP approval, not approved" in ledger_row["canonicalStatus"]
    assert readiness_row["Implementation approved"] == "false"
    assert source_row["Source path"] == "`flaghunter/mcp/server/mcp_tools.py`"
    assert source_row["Implementation approved"] == "false"
    assert evidence_row["Implementation landed"] == "false"
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


def test_playbook_parses_pre_approval_source_map_and_blocks_wiring() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path pre-approval source-map guard")

    assert "Status: source-map guard recorded, no implementation approved by this section." in section
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
        assert row["Implementation approved"] == "false"
        forbidden_tokens = _inline_code_values(row["Forbidden neutral wiring"])
        assert set(forbidden_tokens) == expected_tokens
        source_path = REPO_ROOT / row["Source path"].strip("`")
        source_text = source_path.read_text(encoding="utf-8")
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

    assert "Status: landed evidence guard recorded, no implementation approved by this section." in section
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
        assert row["Implementation landed"] == "false"
        assert row["Landing evidence"] == "none"
        assert row["Required before landed"] == "landing record, commit SHA, regression results"
        assert "implementation landed" not in ledger_rows[candidate]["canonicalStatus"]
        assert readiness_rows[candidate]["Implementation approved"] == "false"


def test_playbook_parses_read_path_approval_flag_aggregate_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path approval flag aggregate guard")

    assert "Status: aggregate approval flag guard recorded, no implementation approved by this section." in section
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
        assert ledger_row["approvedForImplementation"] == "false"
        assert readiness_rows[candidate]["Implementation approved"] == ledger_row["approvedForImplementation"]
        assert evidence_rows[candidate]["Implementation landed"] == "false"
    for row in source_rows:
        assert row["Implementation approved"] == "false"


def test_playbook_parses_read_path_rollback_command_index() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path rollback command index")

    assert "Status: rollback command index recorded, no implementation approved by this section." in section
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
        "Candidate A": "git revert <single Candidate A implementation commit>",
        "Candidate B": "git revert <single Candidate B implementation commit>",
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
        assert "<single " in row["Rollback command"]
        assert not re.search(r"\b[0-9a-f]{7,40}\b", row["Rollback command"])
    for row in evidence_rows:
        assert row["Implementation landed"] == "false"
        assert row["Landing evidence"] == "none"
        assert "commit SHA" in row["Required before landed"]


def test_playbook_parses_read_path_implementation_landing_status_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path implementation landing status guard")

    assert "Status: landing status guard recorded, no implementation landed." in section
    assert "no production path switch is authorized by this landing status guard" in section

    rows = {
        row["Landing surface"]: row
        for row in _markdown_table_rows(section)
    }
    assert rows == {
        "landed evidence rows": {
            "Landing surface": "landed evidence rows",
            "Required location": "`Read-path implementation landed evidence guard`",
            "Current landed": "false",
        },
        "rollback index": {
            "Landing surface": "rollback index",
            "Required location": "`Read-path rollback command index`",
            "Current landed": "false",
        },
        "landing record template": {
            "Landing surface": "landing record template",
            "Required location": "`Read-path implementation landing record template`",
            "Current landed": "false",
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
        assert row["Implementation landed"] == "false"
        assert row["Landing evidence"] == "none"
    for row in rollback_rows:
        assert row["Current executable"] == "false"
    assert "Status: landing evidence template recorded, no implementation approved by this" in landing_template
    assert "section." in landing_template


def test_playbook_parses_read_path_readiness_to_landing_transition_guard() -> None:
    text = _playbook_text()
    section = _section_text(text, "Read-path readiness-to-landing transition guard")

    assert "Status: readiness-to-landing guard recorded, no implementation landed." in section
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
            "Current satisfied": "false",
        },
        "landing evidence recorded": {
            "Transition checkpoint": "landing evidence recorded",
            "Required section": "`Read-path implementation landed evidence guard`",
            "Current satisfied": "false",
        },
        "rollback commands executable": {
            "Transition checkpoint": "rollback commands executable",
            "Required section": "`Read-path rollback command index`",
            "Current satisfied": "false",
        },
        "landing status raised": {
            "Transition checkpoint": "landing status raised",
            "Required section": "`Read-path implementation landing status guard`",
            "Current satisfied": "false",
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
        assert row["Implementation landed"] == "false"
        assert row["Landing evidence"] == "none"
    for row in _markdown_table_rows(_section_text(text, "Read-path rollback command index")):
        assert row["Current executable"] == "false"
    for row in _markdown_table_rows(
        _section_text(text, "Read-path implementation landing status guard")
    ):
        assert row["Current landed"] == "false"


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
    assert "Status: plan recorded, implementation not approved." in text
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
    assert "Status: ready for approval review, not approved for implementation." in text
    for baseline in (
        "Task ingress application service skeleton baseline",
        "Task ingress domain contract skeleton baseline",
        "Task ingress readback contract skeleton baseline",
        "Task ingress service contract migration plan",
        "Task ingress service contract migration pre-approval guard",
    ):
        assert baseline in text
    for evidence_test in (
        "test_submit_returns_pending_payload_without_ingress_port",
        "test_submit_delegates_to_task_ingress_port_only",
        "test_submit_accepts_minimal_empty_values",
        "test_task_ingress_service_contract_migration_pre_approval_guard",
    ):
        assert evidence_test in text
    assert "approval is still required before editing `flaghunter/application/challenge/task_ingress_service.py`" in text
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


def test_playbook_parses_task_ingress_service_migration_approval_flag_consistency_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Task ingress service contract migration approval flag consistency guard",
    )

    assert "Status: approval consistency guard recorded, implementation not approved by this section." in section
    assert "Task ingress service contract migration plan" in section
    assert "Task ingress service contract migration pre-approval guard" in section
    assert "Task ingress service contract migration readiness checklist" in section
    assert "no implementation approval by implication" in section
    assert "no service migration" in section

    plan = _heading_section_text(text, "Task ingress service contract migration plan")
    pre_approval = _heading_section_text(
        text,
        "Task ingress service contract migration pre-approval guard",
    )
    readiness = _heading_section_text(
        text,
        "Task ingress service contract migration readiness checklist",
    )

    assert "Status: plan recorded, implementation not approved." in plan
    assert "Status: pre-approval guard active, implementation not approved." in pre_approval
    assert "Status: ready for approval review, not approved for implementation." in readiness

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
        assert row["Implementation approved"] == "false"
        assert row["Service migration landed"] == "false"

    for forbidden_phrase in (
        "approved for implementation",
        "implementation approved",
        "service migration landed",
    ):
        assert forbidden_phrase not in plan.lower()
        assert forbidden_phrase not in pre_approval.lower()


def test_playbook_records_task_ingress_service_migration_landing_record_template() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Task ingress service contract migration landing record template",
    )

    assert "Status: landing evidence template recorded, implementation not approved." in section
    for required_field in (
        "Implementation commit SHA",
        "Target",
        "Behavior equivalence evidence",
        "Port payload compatibility evidence",
        "Pre-approval guard update",
        "Focused regression result",
        "Architecture/source-guard result",
        "git diff --check result",
        "Post-push branch status",
        "Rollback command",
        "Boundary confirmation",
    ):
        assert required_field in section
    assert "Rollback command: git revert <sha>" in section
    assert "old/new output equivalence" in section
    assert "raw `instructions` in the injected port request payload" in section
    assert "no service migration is authorized by this template" in section
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

    assert "Status: rollback placeholder guard recorded, implementation not approved." in section
    assert "placeholder only" in section
    assert "not a currently executable rollback command" in section
    assert "no service migration is authorized by this rollback guard" in section

    rows = {
        row["Scope"]: row
        for row in _markdown_table_rows(section)
    }
    assert set(rows) == {"task ingress service migration"}

    row = rows["task ingress service migration"]
    assert row["Rollback command"] == "`git revert <single task ingress service migration commit>`"
    assert row["Applies after"] == "service migration commit lands"
    assert row["Current executable"] == "false"
    assert not re.search(r"\b[0-9a-f]{7,40}\b", row["Rollback command"])

    landing_template = _heading_section_text(
        text,
        "Task ingress service contract migration landing record template",
    )
    assert "Rollback command: git revert <sha>" in landing_template


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

    assert "Status: approval transition evidence consistency guard recorded, implementation not approved." in section
    assert "approval evidence must be present before implementation approval changes" in section
    assert "no service migration is authorized by this evidence guard" in section

    rows = {
        row["Evidence item"]: row
        for row in _markdown_table_rows(section)
    }
    assert rows == {
        "red test evidence": {
            "Evidence item": "red test evidence",
            "Required location": "`Task ingress service contract migration readiness checklist`",
            "Current approval evidence present": "false",
        },
        "green focused regression": {
            "Evidence item": "green focused regression",
            "Required location": "`Task ingress service contract migration readiness checklist`",
            "Current approval evidence present": "false",
        },
        "architecture/source regression": {
            "Evidence item": "architecture/source regression",
            "Required location": "`Task ingress service contract migration readiness checklist`",
            "Current approval evidence present": "false",
        },
        "approval flag update evidence": {
            "Evidence item": "approval flag update evidence",
            "Required location": "`Task ingress service contract migration approval flag consistency guard`",
            "Current approval evidence present": "false",
        },
        "landing record placeholder": {
            "Evidence item": "landing record placeholder",
            "Required location": "`Task ingress service contract migration landing record template`",
            "Current approval evidence present": "false",
        },
        "rollback placeholder evidence": {
            "Evidence item": "rollback placeholder evidence",
            "Required location": "`Task ingress service rollback placeholder consistency guard`",
            "Current approval evidence present": "false",
        },
        "post-push branch status": {
            "Evidence item": "post-push branch status",
            "Required location": "`Task ingress service contract migration readiness checklist`",
            "Current approval evidence present": "false",
        },
    }

    for forbidden in (
        "Current approval evidence present | true",
        "implementation approved",
        "service migration landed",
    ):
        assert forbidden not in section


def test_playbook_parses_task_ingress_service_landing_status_guard() -> None:
    text = _playbook_text()
    section = _heading_section_text(
        text,
        "Task ingress service landing status guard",
    )

    assert "Status: landing status guard recorded, service migration not landed." in section
    assert "no service migration is authorized by this landing status guard" in section

    rows = {
        row["Landing surface"]: row
        for row in _markdown_table_rows(section)
    }
    assert rows == {
        "landing record template": {
            "Landing surface": "landing record template",
            "Required location": "`Task ingress service contract migration landing record template`",
            "Current landed": "false",
        },
        "rollback placeholder": {
            "Landing surface": "rollback placeholder",
            "Required location": "`Task ingress service rollback placeholder consistency guard`",
            "Current landed": "false",
        },
        "approval evidence": {
            "Landing surface": "approval evidence",
            "Required location": "`Task ingress service approval transition evidence consistency guard`",
            "Current landed": "false",
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

    assert "Status: landing evidence template recorded, implementation not approved." in landing_template
    rollback_rows = _markdown_table_rows(rollback_guard)
    assert rollback_rows[0]["Current executable"] == "false"
    for row in _markdown_table_rows(evidence_guard):
        assert row["Current approval evidence present"] == "false"
