from __future__ import annotations

from flaghunter.agents.pa_agent.task_dag_crew_bridge import (
    build_task_dag_crew_bridge_request,
    normalize_task_dag_crew_bridge_receipt,
)
from flaghunter.agents.pa_agent.task_dag_crew_bridge_readback import (
    TASK_DAG_CREW_BRIDGE_PREVIEW_SCHEMA_VERSION,
    TaskDAGCrewBridgePreviewRecord,
    build_task_dag_crew_bridge_preview,
    load_task_dag_crew_bridge_preview_records,
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
            "metadata": {"source_kind": "test"},
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
            "metadata": {"source_kind": "receipt"},
        }
    )


def test_p4d_b_preview_pairs_requests_receipts_and_reports_missing_or_orphaned() -> None:
    request_a = _request("task-a", goal="Probe login")
    request_b = _request("task-b", worker_type="crypto", goal="Decode token")
    receipt_a = _receipt("task-a", summary="Login checked")
    orphan_receipt = _receipt("task-c", status="failed", summary="Orphan result")

    preview = build_task_dag_crew_bridge_preview(
        requests=[request_b.to_dict(), request_a],
        receipts=[orphan_receipt.to_dict(), receipt_a],
    )
    records = preview["records"]

    assert preview["schemaVersion"] == TASK_DAG_CREW_BRIDGE_PREVIEW_SCHEMA_VERSION
    assert [record["taskId"] for record in records] == ["task-a", "task-b", "task-c"]
    assert records[0]["requestId"] == request_a.request_id
    assert records[0]["receiptId"] == receipt_a.receipt_id
    assert records[0]["status"] == "succeeded"
    assert records[0]["goalSnippet"] == "Probe login"
    assert records[0]["summarySnippet"] == "Login checked"
    assert records[1]["status"] == "missing_receipt"
    assert records[1]["hasReceipt"] is False
    assert "missing_bridge_receipt" in records[1]["warnings"]
    assert records[2]["requestId"] == ""
    assert records[2]["status"] == "failed"
    assert "missing_bridge_request" in records[2]["warnings"]
    assert preview["summary"]["requestCount"] == 2
    assert preview["summary"]["receiptCount"] == 2
    assert preview["summary"]["matchedCount"] == 3
    assert preview["summary"]["missingReceiptCount"] == 1
    assert preview["summary"]["statusCounts"] == {
        "failed": 1,
        "missing_receipt": 1,
        "succeeded": 1,
    }
    assert preview["summary"]["workerTypeCounts"] == {"crypto": 1, "web": 2}
    assert "request" not in records[0]
    assert "receipt" not in records[0]


def test_p4d_b_preview_filters_sorts_and_truncates_deterministically() -> None:
    requests = [
        _request("task-3", worker_type="crypto"),
        _request("task-1", worker_type="web"),
        _request("task-2", worker_type="web"),
    ]
    receipts = [
        _receipt("task-2", worker_type="web", status="failed"),
        _receipt("task-1", worker_type="web", status="succeeded"),
    ]

    preview_a = build_task_dag_crew_bridge_preview(
        requests=requests,
        receipts=receipts,
        worker_type="web",
        has_receipt=True,
        max_records=1,
    )
    preview_b = build_task_dag_crew_bridge_preview(
        requests=list(reversed(requests)),
        receipts=list(reversed(receipts)),
        worker_type="web",
        has_receipt=True,
        max_records=1,
    )

    assert preview_a == preview_b
    assert [record["taskId"] for record in preview_a["records"]] == ["task-1"]
    assert preview_a["summary"]["matchedCount"] == 2
    assert preview_a["summary"]["exportedCount"] == 1
    assert preview_a["summary"]["truncatedCount"] == 1


def test_p4d_b_preview_filters_by_status_and_task_id() -> None:
    preview = build_task_dag_crew_bridge_preview(
        requests=[_request("task-web"), _request("other-task")],
        receipts=[
            _receipt("task-web", status="failed"),
            _receipt("other-task", status="succeeded"),
        ],
        status="failed",
        task_id="task-",
    )

    assert [record["taskId"] for record in preview["records"]] == ["task-web"]
    assert preview["summary"]["filters"] == {
        "workerType": "",
        "status": "failed",
        "taskId": "task-",
        "hasReceipt": None,
    }


def test_p4d_b_load_preview_records_returns_compact_dataclasses() -> None:
    records = load_task_dag_crew_bridge_preview_records(
        requests=[_request("task-a")],
        receipts=[_receipt("task-a")],
    )

    assert len(records) == 1
    assert isinstance(records[0], TaskDAGCrewBridgePreviewRecord)
    assert records[0].to_dict()["taskId"] == "task-a"


def test_p4d_b_direct_preview_record_to_dict_strips_raw_sensitive_and_proof_like_fields() -> None:
    proof_like = "level='verified' flag{bad}"
    record = TaskDAGCrewBridgePreviewRecord(
        schema_version="",
        task_id="task-a",
        request_id="request-a",
        receipt_id="receipt-a",
        task_brief_id="brief-a",
        solve_node_id="node-a",
        worker_type="web",
        status="succeeded",
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
    payload = record.to_dict()
    text = repr(payload)

    assert payload["schemaVersion"] == TASK_DAG_CREW_BRIDGE_PREVIEW_SCHEMA_VERSION
    assert payload["goalSnippet"] == "<redacted proof-like value>"
    assert payload["summarySnippet"] == "<redacted proof-like value>"
    assert payload["evidenceRefs"] == ["<redacted proof-like value>"]
    assert payload["warnings"] == ["<redacted proof-like value>"]
    assert payload["metadata"] == {"authorization": "<redacted>", "safe": "ok"}
    for leaked in (
        "level='verified'",
        'level="verified"',
        "flag{bad}",
        "CTF{bad}",
        "raw prompt",
        "verification_decision",
        "verified_flags",
        "metadata-auth",
    ):
        assert leaked not in text


def test_p4d_b_preview_excludes_full_inputs_and_raw_body_like_payloads() -> None:
    preview = build_task_dag_crew_bridge_preview(
        requests=[
            {
                "taskId": "task-a",
                "workerType": "web",
                "goal": "HTTP/1.1 200 OK\n<html>password=body-secret</html>",
                "prompt": "raw prompt",
                "request": {"body": "raw request"},
                "metadata": {"body": "raw metadata", "safe": "ok"},
            }
        ],
        receipts=[
            {
                "taskId": "task-a",
                "workerType": "web",
                "status": "failed",
                "summary": "Use compact summary",
                "stdout": "raw stdout",
                "response": {"body": "raw response"},
            }
        ],
    )
    text = repr(preview)

    assert "<redacted raw body>" in text
    for leaked in (
        "body-secret",
        "<html>",
        "raw prompt",
        "raw request",
        "raw metadata",
        "raw stdout",
        "raw response",
    ):
        assert leaked not in text
