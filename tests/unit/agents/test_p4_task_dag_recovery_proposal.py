from __future__ import annotations

from dataclasses import asdict, fields

import pytest

from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.solve_node import SolveNodeReceipt
from flaghunter.agents.pa_agent.task_dag_plan import (
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
)
from flaghunter.agents.pa_agent.task_dag_recovery_proposal import (
    TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION,
    TaskDAGRecoveryProposal,
    TaskDAGRecoveryProposalError,
    propose_task_dag_recovery,
)


def _plan_with_status(status: TaskDAGStatus, *, task_id: str = "task-a") -> TaskDAGPlan:
    plan = TaskDAGPlan(id=f"plan-{task_id}")
    plan.add_node(
        TaskDAGNode(
            id=task_id,
            kind="exploit",
            title="Dry task",
            goal="Use password=task-password",
            status=status,
            trace_ids=["trace-node"],
            claim_ids=["claim-node"],
            metadata={"session": "node-session"},
        )
    )
    return plan


def _receipt(
    status: str,
    *,
    receipt_id: str = "receipt-a",
    error_class: str = "",
    error_summary: str = "",
    output_summary: str = "",
    metadata: dict[str, object] | None = None,
) -> SolveNodeReceipt:
    return SolveNodeReceipt(
        id=receipt_id,
        node_id="node-a",
        run_id="run-a",
        worker_id="worker-a",
        worker_type="dry",
        status=status,
        duration_ms=123,
        input_brief_id="brief-a",
        output_summary=output_summary,
        trace_ids=["trace-receipt"],
        claim_ids=["claim-receipt"],
        artifact_refs=["artifact-a"],
        error_class=error_class,
        error_summary=error_summary,
        metadata=metadata or {"task_dag_task_id": "task-a", "exit_code": 7},
    )


def test_p4c_b_no_plan_state_or_receipt_returns_compact_no_action() -> None:
    proposal = propose_task_dag_recovery()

    assert isinstance(proposal, TaskDAGRecoveryProposal)
    assert proposal.schema_version == TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION
    assert proposal.recommended_action == "no_action"
    assert proposal.action == "propose_recovery"
    assert proposal.recovery_reason == "no_recovery_source"
    assert "no_recovery_source" in proposal.warnings


def test_p4c_b_recovery_reason_is_explicit_public_dataclass_field() -> None:
    field_names = {field.name for field in fields(TaskDAGRecoveryProposal)}

    assert "recovery_reason" in field_names
    assert "reason" not in field_names


def test_p4c_b_succeeded_dag_and_completed_receipt_returns_no_action() -> None:
    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(TaskDAGStatus.SUCCEEDED),
        task_id="task-a",
        receipt=_receipt("completed", receipt_id="receipt-done"),
    )

    assert proposal.recommended_action == "no_action"
    assert proposal.source_status == "succeeded"
    assert proposal.source_receipt_id == "receipt-done"
    assert proposal.recovery_reason == "terminal_success"


def test_p4c_b_failed_dag_and_failed_receipt_proposes_retry_task() -> None:
    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(TaskDAGStatus.FAILED),
        task_id="task-a",
        receipt=_receipt(
            "failed",
            receipt_id="receipt-failed",
            error_class="ExploitError",
            error_summary="failed compactly",
        ),
    )

    assert proposal.recommended_action == "retry_task"
    assert proposal.task_id == "task-a"
    assert proposal.source_receipt_id == "receipt-failed"
    assert proposal.source_status == "failed"
    assert proposal.priority == "high"
    assert proposal.confidence > 0
    assert "trace-receipt" in proposal.evidence_refs
    assert "claim-receipt" in proposal.evidence_refs
    assert "artifact-a" in proposal.evidence_refs
    assert proposal.metadata["error_class"] == "ExploitError"
    assert proposal.metadata["exit_code"] == 7
    assert proposal.metadata["duration_ms"] == 123


def test_p4c_b_failed_receipt_preserves_bounded_redacted_error_context() -> None:
    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(TaskDAGStatus.FAILED),
        task_id="task-a",
        receipt=_receipt(
            "failed",
            error_class="X" * 200,
            error_summary="Authorization: Bearer receipt-auth " + ("E" * 300),
            output_summary="password=output-password " + ("O" * 300),
            metadata={
                "task_dag_task_id": "task-a",
                "source_kind": "dry token=metadata-token",
            },
        ),
    )
    text = repr(proposal.to_dict())

    assert len(proposal.recovery_reason) <= 160
    assert proposal.metadata["error_class"] == "X" * 80
    assert len(proposal.metadata["error_summary"]) <= 160
    assert len(proposal.metadata["output_summary"]) <= 160
    assert "<redacted>" in text
    for leaked in ("receipt-auth", "output-password", "metadata-token"):
        assert leaked not in text


@pytest.mark.parametrize(
    ("node_status", "receipt_status"),
    [
        (TaskDAGStatus.INSUFFICIENT, "partial"),
        (TaskDAGStatus.FAILED, "partial"),
    ],
)
def test_p4c_b_insufficient_or_partial_without_refs_requests_more_evidence(
    node_status: TaskDAGStatus,
    receipt_status: str,
) -> None:
    receipt = _receipt(receipt_status, metadata={"task_dag_task_id": "task-a"})
    receipt.trace_ids = []
    receipt.claim_ids = []
    receipt.artifact_refs = []

    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(node_status),
        task_id="task-a",
        receipt=receipt,
    )

    assert proposal.recommended_action == "request_more_evidence"
    assert proposal.source_status in {"insufficient", "partial"}
    assert proposal.evidence_refs == []


def test_p4c_b_timeout_metadata_maps_to_evidence_proposal_not_proof() -> None:
    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(TaskDAGStatus.INSUFFICIENT),
        task_id="task-a",
        receipt=_receipt(
            "partial",
            error_class="TimeoutError",
            error_summary="timeout after dry run",
            metadata={"task_dag_task_id": "task-a", "exit_code": 124},
        ),
    )
    serialized = repr(proposal.to_dict())

    assert proposal.recommended_action == "request_more_evidence"
    assert proposal.metadata["exit_code"] == 124
    assert "verification_decision" not in serialized
    assert "verified_flags" not in serialized
    assert 'level="verified"' not in serialized


def test_p4c_b_blocked_node_proposes_manual_review() -> None:
    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(TaskDAGStatus.BLOCKED),
        task_id="task-a",
        receipt=_receipt("blocked"),
    )

    assert proposal.recommended_action == "manual_review"
    assert proposal.recovery_reason == "task_blocked"


def test_p4c_b_skipped_node_maps_to_no_action() -> None:
    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(TaskDAGStatus.SKIPPED),
        task_id="task-a",
        receipt=_receipt("skipped"),
    )

    assert proposal.recommended_action == "no_action"
    assert proposal.recovery_reason == "task_skipped"


def test_p4c_b_failed_node_without_receipt_returns_manual_review_warning() -> None:
    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(TaskDAGStatus.FAILED),
        task_id="task-a",
    )

    assert proposal.recommended_action == "manual_review"
    assert "missing_source_receipt" in proposal.warnings


@pytest.mark.parametrize("attempt_key", ["retry_count", "attempt_count", "previous_proposal_count"])
def test_p4c_b_repeated_attempt_metadata_avoids_infinite_retry(attempt_key: str) -> None:
    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(TaskDAGStatus.FAILED),
        task_id="task-a",
        receipt=_receipt(
            "failed",
            metadata={"task_dag_task_id": "task-a", attempt_key: 3},
        ),
    )

    assert proposal.recommended_action == "manual_review"
    assert "retry_limit_reached" in proposal.warnings


def test_p4c_b_input_like_failure_proposes_adjust_inputs() -> None:
    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(TaskDAGStatus.FAILED),
        task_id="task-a",
        receipt=_receipt(
            "failed",
            error_class="InvalidInputError",
            error_summary="missing required input",
        ),
    )

    assert proposal.recommended_action == "adjust_inputs"
    assert proposal.recovery_reason == "input_problem"


def test_p4c_b_same_input_produces_deterministic_proposal_id() -> None:
    kwargs = {
        "plan": _plan_with_status(TaskDAGStatus.FAILED),
        "task_id": "task-a",
        "receipt": _receipt("failed", receipt_id="receipt-stable"),
    }

    first = propose_task_dag_recovery(**kwargs)
    second = propose_task_dag_recovery(**kwargs)

    assert first.proposal_id == second.proposal_id


@pytest.mark.parametrize(
    "raw_key",
    [
        "stdout",
        "stderr",
        "body",
        "http_body",
        "prompt",
        "completion",
        "tool_result",
        "request",
        "response",
        "full_command",
        "raw_args",
    ],
)
def test_p4c_b_raw_keys_reject(raw_key: str) -> None:
    with pytest.raises(TaskDAGRecoveryProposalError, match="raw field"):
        propose_task_dag_recovery(
            plan=_plan_with_status(TaskDAGStatus.FAILED),
            task_id="task-a",
            receipt={"id": "receipt-a", "status": "failed", raw_key: "secret=raw"},
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
def test_p4c_b_proof_like_keys_reject(proof_key: str) -> None:
    with pytest.raises(TaskDAGRecoveryProposalError, match="proof-like field"):
        propose_task_dag_recovery(
            plan=_plan_with_status(TaskDAGStatus.FAILED),
            task_id="task-a",
            receipt={"id": "receipt-a", "status": "failed", proof_key: "verified"},
        )


def test_p4c_b_verified_level_shaped_values_reject() -> None:
    for value in ('level="verified"', "level='verified'"):
        with pytest.raises(TaskDAGRecoveryProposalError, match="proof-like value"):
            propose_task_dag_recovery(
                plan=_plan_with_status(TaskDAGStatus.FAILED),
                task_id="task-a",
                receipt={"id": "receipt-a", "status": "failed", "metadata": {"level": value}},
            )


def test_p4c_b_to_dict_round_trips_as_compact_schema_versioned_dict() -> None:
    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(TaskDAGStatus.FAILED),
        task_id="task-a",
        receipt=_receipt("failed"),
    )
    payload = proposal.to_dict()

    assert payload["schemaVersion"] == TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION
    assert payload["proposalId"] == proposal.proposal_id
    assert payload["recoveryReason"] == proposal.recovery_reason
    assert payload["recommendedAction"] == proposal.recommended_action
    assert payload["metadata"]["schema_version"] == TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION
    assert "plan" not in payload
    assert "receipt" not in payload


def test_p4c_b_output_excludes_full_objects_raw_bodies_and_secrets() -> None:
    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(TaskDAGStatus.FAILED),
        task_id="task-a",
        receipt=_receipt(
            "failed",
            error_summary="HTTP/1.1 500 ERROR\n<html>secret=body-secret</html>",
            metadata={
                "task_dag_task_id": "task-a",
                "authorization": "Bearer metadata-auth",
                "long_json": "{" + ("x" * 300) + "}",
            },
        ),
    )
    text = repr(proposal.to_dict())

    for forbidden in (
        "task-password",
        "node-session",
        "body-secret",
        "metadata-auth",
        "HTTP/1.1 500",
        "<html>",
    ):
        assert forbidden not in text


def test_p4c_b_state_input_is_read_only_and_does_not_mutate_snapshot() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = _plan_with_status(TaskDAGStatus.FAILED)
    receipt = _receipt("failed", receipt_id="receipt-state")
    state.set_task_dag_plan(plan)
    state.record_solve_node_receipt(receipt)
    state.get_task_dag_plan().get_node("task-a").receipt_ids.append("receipt-state")
    before = state.to_snapshot()

    proposal = propose_task_dag_recovery(state=state, task_id="task-a")

    assert proposal.recommended_action == "retry_task"
    assert state.to_snapshot() == before


def test_p4c_b_dict_inputs_are_accepted_without_serializing_full_objects() -> None:
    proposal = propose_task_dag_recovery(
        plan=_plan_with_status(TaskDAGStatus.FAILED).to_dict(),
        task_id="task-a",
        receipt=_receipt("failed").to_dict(),
    )
    text = repr(asdict(proposal))

    assert proposal.recommended_action == "retry_task"
    assert "Dry task" not in text
    assert "Use password=task-password" not in text
