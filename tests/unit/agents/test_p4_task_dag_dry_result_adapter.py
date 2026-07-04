from __future__ import annotations

from dataclasses import asdict

import pytest

from flaghunter.agents.base_agent import AgentMessage
from flaghunter.agents.pa_agent.context_assembler import ContextAssembler
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.solve_node import SolveNodeReceipt
from flaghunter.agents.pa_agent.task_dag_dry_result_adapter import (
    TaskDAGDryExecutorResult,
    TaskDAGDryResultAdapterError,
    build_task_dag_outcome_from_dry_result,
)
from flaghunter.agents.pa_agent.task_dag_local_caller import (
    local_dag_apply_receipt,
    local_dag_start_next,
)
from flaghunter.agents.pa_agent.task_dag_plan import (
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
    task_dag_plan_to_dict,
)
from flaghunter.agents.pa_agent.task_dag_receipt_factory import (
    TaskDAGReceiptOutcome,
    build_local_task_dag_receipt,
)
from flaghunter.harness.checkpoint_store import CheckpointStore


class _StubAgent:
    def __init__(self, *, project_root, run_id: str):
        self.target = "http://ctf.local"
        self.rag_engine = None
        self.run_id = run_id
        self.project_root = project_root
        self.conversation_history = [
            AgentMessage(role="user", content="continue from DAG dry adapter")
        ]


def _ready_plan() -> TaskDAGPlan:
    plan = TaskDAGPlan(id="plan-dry-adapter")
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            kind="exploit",
            title="Exploit upload",
            goal="Run upload primitive",
            status=TaskDAGStatus.READY,
        )
    )
    return plan


def _state_snapshot(state: CTFState) -> dict[str, object]:
    return {
        "plan": task_dag_plan_to_dict(state.get_task_dag_plan()),
        "solve_graph": state.solve_node_graph.to_dict(),
        "briefs": {
            key: value.to_dict()
            for key, value in sorted(state.task_briefs_by_id.items())
        },
        "receipts": {
            key: value.to_dict()
            for key, value in sorted(state.solve_node_receipts_by_id.items())
        },
    }


def test_p4b4p_empty_dry_result_rejects() -> None:
    for bad in (None, {}):
        with pytest.raises(TaskDAGDryResultAdapterError):
            build_task_dag_outcome_from_dry_result(bad)


def test_p4b4p_missing_or_empty_task_id_rejects() -> None:
    for bad in ("", "   "):
        with pytest.raises(TaskDAGDryResultAdapterError, match="task_id"):
            build_task_dag_outcome_from_dry_result({"task_id": bad, "status": "success"})
    with pytest.raises(TaskDAGDryResultAdapterError, match="task_id"):
        build_task_dag_outcome_from_dry_result({"status": "success"})


def test_p4b4p_minimal_explicit_success_result_builds_completed_outcome() -> None:
    outcome = build_task_dag_outcome_from_dry_result(
        TaskDAGDryExecutorResult(
            task_id=" task-a ",
            solve_node_id=" node-a ",
            task_brief_id=" brief-a ",
            run_id=" run-a ",
            status=" success ",
            compact_output=" completed compactly ",
            metadata={"source_kind": " dry-fixture ", "outcome_kind": " dry-exec "},
        )
    )

    assert isinstance(outcome, TaskDAGReceiptOutcome)
    assert outcome.task_id == "task-a"
    assert outcome.solve_node_id == "node-a"
    assert outcome.task_brief_id == "brief-a"
    assert outcome.run_id == "run-a"
    assert outcome.status == "completed"
    assert outcome.output_summary == "completed compactly"
    assert outcome.metadata == {
        "outcome_kind": "dry-exec",
        "source_channel": "manual_task_dag_outcome_source",
        "source_kind": "dry-fixture",
    }


def test_p4b4p_exit_code_zero_without_status_is_partial_with_warning() -> None:
    outcome = build_task_dag_outcome_from_dry_result(
        {"task_id": "task-a", "exit_code": 0, "compact_output": "finished"}
    )

    assert outcome.status == "partial"
    assert "exit_code_without_status" in outcome.warnings
    assert outcome.metadata["exit_code"] == 0
    assert outcome.metadata["source_kind"] == "dry_result_adapter"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("failed", "failed"),
        ("failure", "failed"),
        ("error", "failed"),
    ],
)
def test_p4b4p_failure_statuses_map_to_failed(status: str, expected: str) -> None:
    outcome = build_task_dag_outcome_from_dry_result(
        {"task_id": "task-a", "status": status, "compact_error": "failed"}
    )

    assert outcome.status == expected


@pytest.mark.parametrize("status", ["timeout", "timed_out", "no_evidence", "insufficient"])
def test_p4b4p_timeout_and_insufficient_statuses_map_to_partial(status: str) -> None:
    outcome = build_task_dag_outcome_from_dry_result(
        {"task_id": "task-a", "status": status}
    )

    assert outcome.status == "partial"


@pytest.mark.parametrize("status", ["blocked", "skipped"])
def test_p4b4p_blocked_and_skipped_statuses_map_directly(status: str) -> None:
    outcome = build_task_dag_outcome_from_dry_result(
        {"task_id": "task-a", "status": status}
    )

    assert outcome.status == status


def test_p4b4p_unknown_status_rejects_without_becoming_completed() -> None:
    with pytest.raises(TaskDAGDryResultAdapterError, match="invalid status"):
        build_task_dag_outcome_from_dry_result(
            {"task_id": "task-a", "status": "future-success-ish"}
        )


def test_p4b4p_compact_fields_refs_warnings_and_metadata_are_bounded_redacted() -> None:
    outcome = build_task_dag_outcome_from_dry_result(
        {
            "task_id": "task-a",
            "status": "error",
            "compact_output": "Authorization: Bearer output-auth " + ("O" * 300),
            "compact_error": "password=error-password " + ("E" * 300),
            "error_class": "X" * 200,
            "trace_ids": ["trace-a", "trace-a", "T" * 300],
            "claim_ids": ["claim-a", "claim-a", "C" * 300],
            "artifact_refs": [
                "file://loot/token=artifact-token",
                "file://loot/token=artifact-token",
            ],
            "warnings": ["cookie=warn-cookie", "session=warn-session"] * 6,
            "metadata": {
                "source_kind": "dry secret=source-secret",
                "outcome_kind": "adapter token=metadata-token",
                "raw_tool_result": "password=tool-password",
                "recovery": "switch",
            },
        }
    )
    text = repr(asdict(outcome))

    assert outcome.status == "failed"
    assert len(outcome.output_summary) <= 160
    assert len(outcome.error_summary) <= 160
    assert len(outcome.error_class) == 80
    assert outcome.trace_ids == ["trace-a", "T" * 160]
    assert outcome.claim_ids == ["claim-a", "C" * 160]
    assert len(outcome.artifact_refs) == 1
    assert len(outcome.warnings) == 10
    assert set(outcome.metadata) == {"outcome_kind", "source_channel", "source_kind"}
    assert "<redacted>" in text
    for leaked in (
        "output-auth",
        "error-password",
        "artifact-token",
        "warn-cookie",
        "warn-session",
        "source-secret",
        "metadata-token",
        "tool-password",
    ):
        assert leaked not in text


@pytest.mark.parametrize(
    "raw_key",
    [
        "stdout",
        "stderr",
        "body",
        "http_body",
        "raw_body",
        "raw_output",
        "prompt",
        "completion",
        "tool_result",
        "tool_results",
        "request",
        "response",
        "http_request",
        "http_response",
        "browser_log",
        "terminal_output",
        "full_output",
    ],
)
def test_p4b4p_raw_fields_reject(raw_key: str) -> None:
    with pytest.raises(TaskDAGDryResultAdapterError, match="raw field"):
        build_task_dag_outcome_from_dry_result(
            {"task_id": "task-a", "status": "partial", raw_key: "secret=raw-secret"}
        )


@pytest.mark.parametrize(
    "proof_key",
    [
        "verification_decision",
        "verified_flags",
        "verifierProof",
        "proof_level",
        "verificationRecordId",
        "verifiedFlag",
        "flag_level",
        "flag_verified",
        "verifier_decision",
    ],
)
def test_p4b4p_proof_like_fields_reject(proof_key: str) -> None:
    with pytest.raises(TaskDAGDryResultAdapterError, match="proof-like field"):
        build_task_dag_outcome_from_dry_result(
            {"task_id": "task-a", "status": "success", proof_key: "verified"}
        )


def test_p4b4p_exit_code_is_metadata_only_and_does_not_drive_status() -> None:
    outcome = build_task_dag_outcome_from_dry_result(
        {
            "task_id": "task-a",
            "status": "partial",
            "exit_code": 7,
            "compact_output": "HTTP/1.1 200 OK\n<html>secret=body-secret</html>",
        }
    )
    text = repr(asdict(outcome))

    assert outcome.status == "partial"
    assert outcome.output_summary == "<redacted raw body>"
    assert outcome.metadata["exit_code"] == 7
    assert outcome.metadata["source_kind"] == "dry_result_adapter"
    assert "body-secret" not in text


def test_p4b4p_duration_ms_positive_is_preserved_on_outcome() -> None:
    outcome = build_task_dag_outcome_from_dry_result(
        {
            "task_id": "task-a",
            "status": "partial",
            "duration_ms": 123,
        }
    )

    assert outcome.status == "partial"
    assert outcome.duration_ms == 123


@pytest.mark.parametrize("duration_ms", [-1, "not-an-int"])
def test_p4b4p_invalid_duration_ms_is_not_preserved(duration_ms: object) -> None:
    outcome = build_task_dag_outcome_from_dry_result(
        {
            "task_id": "task-a",
            "status": "partial",
            "duration_ms": duration_ms,
        }
    )

    assert outcome.status == "partial"
    assert outcome.duration_ms is None


def test_p4b4p_adapter_returns_only_outcome_without_mutating_state() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    before = _state_snapshot(state)

    outcome = build_task_dag_outcome_from_dry_result(
        {"task_id": "task-a", "status": "success"}
    )

    assert isinstance(outcome, TaskDAGReceiptOutcome)
    assert not isinstance(outcome, SolveNodeReceipt)
    assert _state_snapshot(state) == before


@pytest.mark.parametrize(
    ("status", "expected_dag_status"),
    [
        ("success", TaskDAGStatus.SUCCEEDED),
        ("error", TaskDAGStatus.FAILED),
        ("timeout", TaskDAGStatus.INSUFFICIENT),
    ],
)
def test_p4b4p_dry_result_integrates_externally_through_factory_and_caller(
    status: str,
    expected_dag_status: TaskDAGStatus,
) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    start = local_dag_start_next(state, plan=_ready_plan())
    outcome = build_task_dag_outcome_from_dry_result(
        {
            "task_id": "task-a",
            "solve_node_id": start.solve_node_id,
            "task_brief_id": start.task_brief_id,
            "status": status,
            "compact_output": f"{status} compactly",
        }
    )
    receipt = build_local_task_dag_receipt(outcome)

    result = local_dag_apply_receipt(state, "task-a", receipt)

    assert result.ok is True
    assert state.get_task_dag_plan().get_node("task-a").status is expected_dag_status


def test_p4b4p_readback_session_and_prompt_remain_compact(tmp_path) -> None:
    run_id = "run-p4b4p-compact"
    state = CTFState(target="http://ctf.local", goal="get flag")
    start = local_dag_start_next(state, plan=_ready_plan(), run_id=run_id)
    outcome = build_task_dag_outcome_from_dry_result(
        {
            "task_id": "task-a",
            "solve_node_id": start.solve_node_id,
            "task_brief_id": start.task_brief_id,
            "run_id": run_id,
            "status": "success",
            "compact_output": "Authorization: Bearer dry-auth",
            "metadata": {"outcome_kind": "dry token=metadata-token"},
        }
    )
    receipt = build_local_task_dag_receipt(outcome)
    local_dag_apply_receipt(state, "task-a", receipt)
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    prompt_text = ContextAssembler(
        _StubAgent(project_root=tmp_path, run_id=run_id)
    ).assemble()

    assert "node_receipts=1" in prompt_text
    assert "task_dag_statuses=succeeded:1" in prompt_text
    for forbidden in (
        "taskDagPlanReadback",
        "task_dag_plan",
        "task-a",
        "dry-auth",
        "metadata-token",
    ):
        assert forbidden not in prompt_text
