from __future__ import annotations

from flaghunter.agents.pa_agent.task_dag_plan import (
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
)
from flaghunter.agents.pa_agent.task_dag_recovery_proposal import (
    TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION,
    propose_task_dag_recovery,
)
from flaghunter.agents.pa_agent.task_dag_recovery_proposal_readback import (
    TASK_DAG_RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION,
    TaskDAGRecoveryProposalRecord,
    build_task_dag_recovery_proposal_readback,
    normalize_task_dag_recovery_proposal_record,
    proposal_to_readback_record,
)


def _failed_proposal(*, task_id: str = "task-a", priority: str = "high"):
    plan = TaskDAGPlan(id=f"plan-{task_id}")
    plan.add_node(
        TaskDAGNode(
            id=task_id,
            kind="exploit",
            title="Dry task",
            goal="Use password=task-password",
            status=TaskDAGStatus.FAILED,
        )
    )
    return propose_task_dag_recovery(
        plan=plan,
        task_id=task_id,
        receipt={
            "id": f"receipt-{task_id}",
            "status": "failed",
            "trace_ids": [f"trace-{task_id}"],
            "claim_ids": [f"claim-{task_id}"],
            "artifact_refs": [f"artifact-{task_id}"],
            "error_class": "ExploitError",
            "error_summary": "failed compactly",
            "metadata": {"task_dag_task_id": task_id, "priority_hint": priority},
        },
        metadata={"source_kind": "dry"},
    )


def test_p4c_c_round_trip_proposal_dict_to_compact_readback_record() -> None:
    proposal = _failed_proposal(task_id="task-a")

    record = proposal_to_readback_record(proposal.to_dict())
    payload = record.to_dict()

    assert isinstance(record, TaskDAGRecoveryProposalRecord)
    assert payload["schemaVersion"] == TASK_DAG_RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION
    assert payload["sourceSchemaVersion"] == TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION
    assert payload["proposalId"] == proposal.proposal_id
    assert payload["action"] == "propose_recovery"
    assert payload["taskId"] == "task-a"
    assert payload["sourceStatus"] == "failed"
    assert payload["recoveryReason"] == "task_failed"
    assert payload["recommendedAction"] == "retry_task"
    assert payload["confidence"] == proposal.confidence
    assert payload["priority"] == "high"
    assert payload["evidenceRefs"] == [
        "trace-task-a",
        "claim-task-a",
        "artifact-task-a",
    ]
    assert payload["warnings"] == []
    assert payload["metadata"]["error_class"] == "ExploitError"
    assert "receipt" not in payload
    assert "plan" not in payload


def test_p4c_c_accepts_snake_case_record_shape_and_outputs_camel_case() -> None:
    record = normalize_task_dag_recovery_proposal_record(
        {
            "schema_version": TASK_DAG_RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION,
            "source_schema_version": TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION,
            "proposal_id": "proposal-a",
            "action": "propose_recovery",
            "task_id": "task-a",
            "source_receipt_id": "receipt-a",
            "source_status": "failed",
            "recovery_reason": "task_failed",
            "recommended_action": "retry_task",
            "confidence": 2.0,
            "priority": "critical",
            "evidence_refs": ["trace-a"],
            "warnings": ["warn-a"],
            "metadata": {"source_kind": "dry"},
            "created_at": 42,
        }
    )
    payload = record.to_dict()

    assert payload["proposalId"] == "proposal-a"
    assert payload["recommendedAction"] == "retry_task"
    assert payload["confidence"] == 1.0
    assert payload["priority"] == "normal"
    assert payload["createdAt"] == 42.0
    assert "proposal_id" not in payload
    assert "recommended_action" not in payload


def test_p4c_c_invalid_or_missing_fields_fail_closed_without_action() -> None:
    record = normalize_task_dag_recovery_proposal_record(
        {
            "schemaVersion": "unknown",
            "proposalId": "proposal-a",
            "recommendedAction": "retry_task",
        }
    )
    payload = record.to_dict()

    assert payload["valid"] is False
    assert payload["action"] == "invalid"
    assert payload["recommendedAction"] == "no_action"
    assert "invalid_schema" in payload["warnings"]
    assert "missing_task_id" in payload["warnings"]


def test_p4c_c_bounded_output_redacts_raw_sensitive_and_long_values() -> None:
    proposal = _failed_proposal(task_id="task-a").to_dict()
    proposal["metadata"] = {
        "authorization": "Bearer metadata-auth",
        "session": "session-secret",
        "long": "L" * 300,
        "html": "HTTP/1.1 500 ERROR\n<html>password=body-secret</html>",
        "safe": "ok",
    }
    proposal["evidenceRefs"] = [f"trace-{index}-" + ("X" * 300) for index in range(25)]
    proposal["warnings"] = [f"warning-{index}-" + ("Y" * 300) for index in range(12)]

    payload = proposal_to_readback_record(proposal).to_dict()
    text = repr(payload)

    assert len(payload["evidenceRefs"]) == 20
    assert len(payload["warnings"]) == 10
    assert all(len(item) <= 160 for item in payload["evidenceRefs"])
    assert all(len(item) <= 160 for item in payload["warnings"])
    assert len(payload["metadata"]["long"]) <= 160
    assert "<redacted>" in text
    assert "<redacted raw body>" in text
    for leaked in ("metadata-auth", "session-secret", "body-secret", "<html>"):
        assert leaked not in text


def test_p4c_c_list_readback_filters_sorts_and_limits_records() -> None:
    retry = _failed_proposal(task_id="task-retry").to_dict()
    retry["createdAt"] = 30
    manual = _failed_proposal(task_id="task-manual").to_dict()
    manual["recommendedAction"] = "manual_review"
    manual["createdAt"] = 10
    other = _failed_proposal(task_id="task-other").to_dict()
    other["priority"] = "normal"
    other["createdAt"] = 20

    readback = build_task_dag_recovery_proposal_readback(
        [retry, manual, other],
        max_records=2,
        recommended_action="retry_task",
    )

    assert readback["schemaVersion"] == TASK_DAG_RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION
    assert [record["taskId"] for record in readback["records"]] == [
        "task-other",
        "task-retry",
    ]
    assert readback["summary"]["inputCount"] == 3
    assert readback["summary"]["matchedCount"] == 2
    assert readback["summary"]["exportedCount"] == 2
    assert readback["summary"]["truncatedCount"] == 0


def test_p4c_c_list_readback_supports_task_and_priority_filters_with_truncation() -> None:
    records = []
    for index in range(4):
        proposal = _failed_proposal(task_id=f"task-{index}").to_dict()
        proposal["priority"] = "high"
        proposal["createdAt"] = index
        records.append(proposal)

    readback = build_task_dag_recovery_proposal_readback(
        records,
        max_records=2,
        task_id="task-",
        priority="high",
    )

    assert [record["taskId"] for record in readback["records"]] == [
        "task-0",
        "task-1",
    ]
    assert readback["summary"]["matchedCount"] == 4
    assert readback["summary"]["truncatedCount"] == 2
