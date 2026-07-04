from __future__ import annotations

from flaghunter.agents.pa_agent.task_dag_crew_bridge_admission import (
    TASK_DAG_CREW_BRIDGE_ADMISSION_SCHEMA_VERSION,
    TaskDAGCrewBridgeAdmissionItem,
    TaskDAGCrewBridgeAdmissionPackage,
    build_task_dag_crew_bridge_admission_package,
    load_task_dag_crew_bridge_admission_items,
)
from flaghunter.agents.pa_agent.task_dag_crew_bridge_handoff import (
    TASK_DAG_CREW_BRIDGE_HANDOFF_SCHEMA_VERSION,
    TaskDAGCrewBridgeHandoffEnvelope,
    TaskDAGCrewBridgeHandoffItem,
)


def _handoff_item(
    task_id: str,
    decision: str,
    *,
    worker_type: str = "web",
    status: str = "succeeded",
    has_receipt: bool = True,
    summary: str = "Useful summary",
) -> TaskDAGCrewBridgeHandoffItem:
    return TaskDAGCrewBridgeHandoffItem(
        schema_version=TASK_DAG_CREW_BRIDGE_HANDOFF_SCHEMA_VERSION,
        task_id=task_id,
        request_id=f"request-{task_id}",
        receipt_id=f"receipt-{task_id}" if has_receipt else "",
        worker_type=worker_type,
        status=status,
        handoff_decision=decision,
        goal_snippet=f"Goal for {task_id}",
        summary_snippet=summary,
        has_receipt=has_receipt,
        evidence_refs=[f"trace-{task_id}"],
        warnings=[],
        metadata={"safe": task_id},
    )


def test_p4d_d_admission_package_shape_and_decision_counts_from_handoff() -> None:
    handoff = TaskDAGCrewBridgeHandoffEnvelope(
        schema_version=TASK_DAG_CREW_BRIDGE_HANDOFF_SCHEMA_VERSION,
        envelope_id="handoff-a",
        items=[
            _handoff_item("task-complete", "completed_no_handoff", summary=""),
            _handoff_item("task-ready", "ready_for_review"),
            _handoff_item(
                "task-waiting",
                "waiting_for_receipt",
                worker_type="crypto",
                status="missing_receipt",
                has_receipt=False,
                summary="",
            ),
            _handoff_item("task-manual", "needs_manual_review", status="partial"),
            _handoff_item("task-failed", "blocked_or_failed", status="failed"),
        ],
        summary={"recordCount": 5},
        filters={},
    )

    package = build_task_dag_crew_bridge_admission_package(handoff=handoff)
    payload = package.to_dict()
    items = payload["items"]

    assert isinstance(package, TaskDAGCrewBridgeAdmissionPackage)
    assert payload["schemaVersion"] == TASK_DAG_CREW_BRIDGE_ADMISSION_SCHEMA_VERSION
    assert payload["packageId"].startswith("task_dag_crew_admission_")
    assert [item["taskId"] for item in items] == [
        "task-failed",
        "task-manual",
        "task-ready",
        "task-waiting",
        "task-complete",
    ]
    assert [item["admissionState"] for item in items] == [
        "reject_failed",
        "manual_review_required",
        "admit_dry",
        "hold_for_receipt",
        "complete_noop",
    ]
    assert payload["summary"]["handoffItemCount"] == 5
    assert payload["summary"]["exportedCount"] == 5
    assert payload["summary"]["admitDryCount"] == 1
    assert payload["summary"]["holdCount"] == 1
    assert payload["summary"]["manualReviewCount"] == 1
    assert payload["summary"]["rejectCount"] == 1
    assert payload["summary"]["completeNoopCount"] == 1
    assert payload["summary"]["decisionCounts"] == {
        "admit_dry": 1,
        "complete_noop": 1,
        "hold_for_receipt": 1,
        "manual_review_required": 1,
        "reject_failed": 1,
    }
    assert "handoff" not in payload
    assert "preview" not in payload
    assert "requests" not in payload
    assert "receipts" not in payload


def test_p4d_d_unknown_handoff_decision_fails_closed_to_manual_review() -> None:
    package = build_task_dag_crew_bridge_admission_package(
        handoff={
            "items": [
                {
                    "taskId": "task-unknown",
                    "requestId": "request-unknown",
                    "receiptId": "receipt-unknown",
                    "workerType": "web",
                    "status": "running",
                    "handoffDecision": "surprise_queue",
                    "goalSnippet": "Investigate",
                    "summarySnippet": "Needs operator choice",
                    "hasReceipt": True,
                    "warnings": [],
                    "metadata": {},
                }
            ]
        }
    )
    item = package.to_dict()["items"][0]

    assert item["handoffDecision"] == "surprise_queue"
    assert item["admissionState"] == "manual_review_required"
    assert item["reason"] == "unknown_handoff_decision"
    assert "unknown_handoff_decision" in item["warnings"]


def test_p4d_d_can_build_handoff_internally_from_preview_shape() -> None:
    package = build_task_dag_crew_bridge_admission_package(
        preview={
            "records": [
                {
                    "taskId": "task-preview",
                    "requestId": "request-preview",
                    "receiptId": "receipt-preview",
                    "taskBriefId": "brief-preview",
                    "solveNodeId": "node-preview",
                    "workerType": "web",
                    "status": "succeeded",
                    "goalSnippet": "Preview goal",
                    "summarySnippet": "Preview summary",
                    "hasReceipt": True,
                    "evidenceRefs": ["trace-preview"],
                    "warnings": [],
                    "metadata": {"safe": "ok"},
                }
            ]
        }
    )
    payload = package.to_dict()

    assert payload["items"][0]["taskId"] == "task-preview"
    assert payload["items"][0]["handoffDecision"] == "ready_for_review"
    assert payload["items"][0]["admissionState"] == "admit_dry"


def test_p4d_d_filters_sorts_and_truncates_deterministically() -> None:
    items = [
        _handoff_item("task-3", "waiting_for_receipt", worker_type="crypto", has_receipt=False),
        _handoff_item("task-1", "ready_for_review", worker_type="web"),
        _handoff_item("task-2", "blocked_or_failed", worker_type="web", status="failed"),
        _handoff_item("other-task", "ready_for_review", worker_type="web"),
    ]

    first = build_task_dag_crew_bridge_admission_package(
        handoff={"items": items},
        worker_type="web",
        task_id="task-",
        has_receipt=True,
        max_items=1,
    ).to_dict()
    second = build_task_dag_crew_bridge_admission_package(
        handoff={"items": list(reversed(items))},
        worker_type="web",
        task_id="task-",
        has_receipt=True,
        max_items=1,
    ).to_dict()

    assert first == second
    assert [item["taskId"] for item in first["items"]] == ["task-2"]
    assert first["summary"]["handoffItemCount"] == 2
    assert first["summary"]["exportedCount"] == 1
    assert first["summary"]["truncatedCount"] == 1


def test_p4d_d_filters_by_status_handoff_decision_and_admission_state() -> None:
    package = build_task_dag_crew_bridge_admission_package(
        handoff={
            "items": [
                _handoff_item("task-ready", "ready_for_review", status="succeeded"),
                _handoff_item("task-failed", "blocked_or_failed", status="failed"),
            ]
        },
        status="failed",
        handoff_decision="blocked_or_failed",
        admission_state="reject_failed",
    )
    payload = package.to_dict()

    assert [item["taskId"] for item in payload["items"]] == ["task-failed"]
    assert payload["summary"]["filters"] == {
        "workerType": "",
        "status": "failed",
        "taskId": "",
        "handoffDecision": "blocked_or_failed",
        "admissionState": "reject_failed",
        "hasReceipt": None,
    }


def test_p4d_d_load_admission_items_returns_compact_dataclasses() -> None:
    items = load_task_dag_crew_bridge_admission_items(
        handoff={"items": [_handoff_item("task-a", "ready_for_review")]}
    )

    assert len(items) == 1
    assert isinstance(items[0], TaskDAGCrewBridgeAdmissionItem)
    assert items[0].to_dict()["taskId"] == "task-a"


def test_p4d_d_direct_admission_dataclasses_strip_proof_like_and_raw_values() -> None:
    proof_like = "level='verified' flag{bad}"
    item = TaskDAGCrewBridgeAdmissionItem(
        schema_version="",
        task_id=proof_like,
        request_id=proof_like,
        receipt_id=proof_like,
        worker_type="web",
        status="succeeded",
        handoff_decision="ready_for_review",
        admission_state="admit_dry",
        reason=proof_like,
        goal_snippet=proof_like,
        summary_snippet='level="verified" CTF{bad}',
        has_receipt=True,
        evidence_refs=[proof_like],
        warnings=[proof_like],
        metadata={
            "authorization": "Bearer metadata-auth",
            "prompt": "raw prompt",
            "verification_decision": "bad",
            "verified_flags": ["flag{bad}"],
            "safe": "ok",
        },
    )
    package = TaskDAGCrewBridgeAdmissionPackage(
        schema_version="",
        package_id="package-a",
        items=[item],
        summary={
            "handoffItemCount": 1,
            "taskId": proof_like,
            "authorization": "Bearer summary-auth",
            "safeCount": 2,
        },
        filters={"taskId": proof_like, "workerType": "web"},
    )
    payload = package.to_dict()
    item_payload = payload["items"][0]
    text = repr(payload)

    assert item_payload["taskId"] == "<redacted proof-like value>"
    assert item_payload["requestId"] == "<redacted proof-like value>"
    assert item_payload["receiptId"] == "<redacted proof-like value>"
    assert item_payload["reason"] == "<redacted proof-like value>"
    assert item_payload["goalSnippet"] == "<redacted proof-like value>"
    assert item_payload["summarySnippet"] == "<redacted proof-like value>"
    assert item_payload["evidenceRefs"] == ["<redacted proof-like value>"]
    assert item_payload["warnings"] == ["<redacted proof-like value>"]
    assert item_payload["metadata"] == {"authorization": "<redacted>", "safe": "ok"}
    assert payload["summary"]["taskId"] == "<redacted proof-like value>"
    assert payload["summary"]["authorization"] == "<redacted>"
    assert payload["summary"]["safeCount"] == 2
    assert payload["filters"]["taskId"] == "<redacted proof-like value>"
    for leaked in (
        "level='verified'",
        'level="verified"',
        "flag{bad}",
        "CTF{bad}",
        "raw prompt",
        "verification_decision",
        "verified_flags",
        "metadata-auth",
        "summary-auth",
    ):
        assert leaked not in text


def test_p4d_d_package_is_deterministic_and_excludes_full_handoff_inputs() -> None:
    items = [
        _handoff_item("task-b", "ready_for_review"),
        _handoff_item("task-a", "ready_for_review"),
    ]

    first = build_task_dag_crew_bridge_admission_package(handoff={"items": items})
    second = build_task_dag_crew_bridge_admission_package(
        handoff={"items": list(reversed(items))}
    )
    payload = first.to_dict()

    assert first.package_id == second.package_id
    assert first.to_dict() == second.to_dict()
    assert "handoff" not in payload
    assert "preview" not in payload
    assert "requests" not in payload
    assert "receipts" not in payload
