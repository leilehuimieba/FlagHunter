from __future__ import annotations

from flaghunter.agents.pa_agent.task_dag_crew_bridge import (
    build_task_dag_crew_bridge_request,
    normalize_task_dag_crew_bridge_receipt,
)
from flaghunter.agents.pa_agent.task_dag_crew_bridge_handoff import (
    TASK_DAG_CREW_BRIDGE_HANDOFF_SCHEMA_VERSION,
    TaskDAGCrewBridgeHandoffEnvelope,
    TaskDAGCrewBridgeHandoffItem,
    build_task_dag_crew_bridge_handoff_envelope,
    load_task_dag_crew_bridge_handoff_items,
)
from flaghunter.agents.pa_agent.task_dag_crew_bridge_readback import (
    build_task_dag_crew_bridge_preview,
)


def _request(task_id: str, *, worker_type: str = "web", goal: str = "Probe target"):
    return build_task_dag_crew_bridge_request(
        {
            "taskId": task_id,
            "taskBriefId": f"brief-{task_id}",
            "solveNodeId": f"node-{task_id}",
            "workerType": worker_type,
            "goal": goal,
            "traceIds": [f"trace-{task_id}"],
        }
    )


def _receipt(
    task_id: str,
    *,
    worker_type: str = "web",
    status: str = "succeeded",
    summary: str = "Worker summary",
):
    return normalize_task_dag_crew_bridge_receipt(
        {
            "taskId": task_id,
            "taskBriefId": f"brief-{task_id}",
            "solveNodeId": f"node-{task_id}",
            "workerId": f"worker-{task_id}",
            "workerType": worker_type,
            "status": status,
            "summary": summary,
            "traceIds": [f"trace-receipt-{task_id}"],
            "claimIds": [f"claim-{task_id}"],
        }
    )


def test_p4d_c_envelope_shape_and_decision_counts_from_preview() -> None:
    preview = build_task_dag_crew_bridge_preview(
        requests=[
            _request("task-ready", goal="Review web result"),
            _request("task-waiting", worker_type="crypto", goal="Wait for receipt"),
            _request("task-failed", worker_type="web", goal="Inspect failure"),
        ],
        receipts=[
            _receipt("task-ready", summary="Useful evidence found"),
            _receipt("task-failed", status="failed", summary="Worker failed"),
            _receipt("task-orphan", status="succeeded", summary="Orphan done"),
        ],
    )

    envelope = build_task_dag_crew_bridge_handoff_envelope(preview=preview)
    payload = envelope.to_dict()
    items = payload["items"]

    assert isinstance(envelope, TaskDAGCrewBridgeHandoffEnvelope)
    assert payload["schemaVersion"] == TASK_DAG_CREW_BRIDGE_HANDOFF_SCHEMA_VERSION
    assert payload["envelopeId"].startswith("task_dag_crew_handoff_")
    assert [item["taskId"] for item in items] == [
        "task-failed",
        "task-orphan",
        "task-ready",
        "task-waiting",
    ]
    assert [item["handoffDecision"] for item in items] == [
        "blocked_or_failed",
        "needs_manual_review",
        "ready_for_review",
        "waiting_for_receipt",
    ]
    assert payload["summary"]["recordCount"] == 4
    assert payload["summary"]["exportedCount"] == 4
    assert payload["summary"]["readyCount"] == 1
    assert payload["summary"]["waitingCount"] == 1
    assert payload["summary"]["manualReviewCount"] == 1
    assert payload["summary"]["blockedOrFailedCount"] == 1
    assert payload["summary"]["completedCount"] == 0
    assert payload["summary"]["statusCounts"] == {
        "failed": 1,
        "missing_receipt": 1,
        "succeeded": 2,
    }
    assert payload["summary"]["workerTypeCounts"] == {"crypto": 1, "web": 3}
    assert "preview" not in payload
    assert "records" not in payload


def test_p4d_c_can_build_preview_internally_from_requests_and_receipts() -> None:
    envelope = build_task_dag_crew_bridge_handoff_envelope(
        requests=[_request("task-a")],
        receipts=[_receipt("task-a", summary="Ready summary")],
    )
    payload = envelope.to_dict()

    assert payload["items"][0]["taskId"] == "task-a"
    assert payload["items"][0]["handoffDecision"] == "ready_for_review"
    assert payload["items"][0]["summarySnippet"] == "Ready summary"


def test_p4d_c_completed_no_handoff_when_succeeded_without_useful_refs_or_summary() -> None:
    preview = {
        "records": [
            {
                "taskId": "task-done",
                "requestId": "request-done",
                "receiptId": "receipt-done",
                "taskBriefId": "brief-done",
                "solveNodeId": "node-done",
                "workerType": "web",
                "status": "succeeded",
                "goalSnippet": "Done",
                "summarySnippet": "",
                "hasReceipt": True,
                "evidenceRefs": [],
                "warnings": [],
                "metadata": {},
            }
        ]
    }

    payload = build_task_dag_crew_bridge_handoff_envelope(preview=preview).to_dict()

    assert payload["items"][0]["handoffDecision"] == "completed_no_handoff"
    assert payload["summary"]["completedCount"] == 1
    assert payload["summary"]["readyCount"] == 0


def test_p4d_c_filters_sorts_and_truncates_deterministically() -> None:
    requests = [
        _request("task-3", worker_type="crypto"),
        _request("task-1", worker_type="web"),
        _request("task-2", worker_type="web"),
    ]
    receipts = [
        _receipt("task-2", worker_type="web", status="failed"),
        _receipt("task-1", worker_type="web", status="succeeded"),
    ]

    first = build_task_dag_crew_bridge_handoff_envelope(
        requests=requests,
        receipts=receipts,
        worker_type="web",
        has_receipt=True,
        max_items=1,
    ).to_dict()
    second = build_task_dag_crew_bridge_handoff_envelope(
        requests=list(reversed(requests)),
        receipts=list(reversed(receipts)),
        worker_type="web",
        has_receipt=True,
        max_items=1,
    ).to_dict()

    assert first == second
    assert [item["taskId"] for item in first["items"]] == ["task-2"]
    assert first["summary"]["recordCount"] == 2
    assert first["summary"]["exportedCount"] == 1
    assert first["summary"]["truncatedCount"] == 1


def test_p4d_c_filters_by_status_task_id_and_decision() -> None:
    envelope = build_task_dag_crew_bridge_handoff_envelope(
        requests=[_request("task-web"), _request("other-task")],
        receipts=[
            _receipt("task-web", status="failed"),
            _receipt("other-task", status="succeeded"),
        ],
        status="failed",
        task_id="task-",
        handoff_decision="blocked_or_failed",
    )
    payload = envelope.to_dict()

    assert [item["taskId"] for item in payload["items"]] == ["task-web"]
    assert payload["summary"]["filters"] == {
        "workerType": "",
        "status": "failed",
        "taskId": "task-",
        "handoffDecision": "blocked_or_failed",
        "hasReceipt": None,
    }


def test_p4d_c_load_handoff_items_returns_compact_dataclasses() -> None:
    items = load_task_dag_crew_bridge_handoff_items(
        requests=[_request("task-a")],
        receipts=[_receipt("task-a")],
    )

    assert len(items) == 1
    assert isinstance(items[0], TaskDAGCrewBridgeHandoffItem)
    assert items[0].to_dict()["taskId"] == "task-a"


def test_p4d_c_direct_handoff_dataclasses_strip_proof_like_and_raw_values() -> None:
    proof_like = "level='verified' flag{bad}"
    item = TaskDAGCrewBridgeHandoffItem(
        schema_version="",
        task_id="task-a",
        request_id="request-a",
        receipt_id="receipt-a",
        worker_type="web",
        status="succeeded",
        handoff_decision="ready_for_review",
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
    envelope = TaskDAGCrewBridgeHandoffEnvelope(
        schema_version="",
        envelope_id="envelope-a",
        items=[item],
        summary={
            "recordCount": 1,
            "taskId": proof_like,
            "authorization": "Bearer summary-auth",
            "safeCount": 2,
        },
        filters={"taskId": proof_like, "workerType": "web"},
    )
    payload = envelope.to_dict()
    text = repr(payload)

    assert payload["items"][0]["goalSnippet"] == "<redacted proof-like value>"
    assert payload["items"][0]["summarySnippet"] == "<redacted proof-like value>"
    assert payload["items"][0]["evidenceRefs"] == ["<redacted proof-like value>"]
    assert payload["items"][0]["warnings"] == ["<redacted proof-like value>"]
    assert payload["items"][0]["metadata"] == {"authorization": "<redacted>", "safe": "ok"}
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


def test_p4d_c_envelope_is_deterministic_and_excludes_full_preview_inputs() -> None:
    requests = [_request("task-b"), _request("task-a")]
    receipts = [_receipt("task-a"), _receipt("task-b")]

    first = build_task_dag_crew_bridge_handoff_envelope(
        requests=requests,
        receipts=receipts,
    )
    second = build_task_dag_crew_bridge_handoff_envelope(
        requests=list(reversed(requests)),
        receipts=list(reversed(receipts)),
    )
    payload = first.to_dict()

    assert first.envelope_id == second.envelope_id
    assert first.to_dict() == second.to_dict()
    assert "preview" not in payload
    assert "requests" not in payload
    assert "receipts" not in payload
