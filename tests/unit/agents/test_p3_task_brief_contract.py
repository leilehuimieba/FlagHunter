from __future__ import annotations

import json

from flaghunter.agents.pa_agent.solve_node import (
    SolveNodeReceipt,
    TaskBrief,
    build_solve_node_receipt_readback,
    build_task_brief_readback,
    solve_node_receipt_from_dict,
    solve_node_receipt_to_dict,
    task_brief_from_dict,
    task_brief_to_dict,
)


def test_p3c_task_brief_default_shape_and_round_trip() -> None:
    brief = TaskBrief(
        node_id="node-a",
        run_id="run-1",
        worker_type="web",
        objective="Probe login",
    )

    payload = task_brief_to_dict(brief)
    restored = task_brief_from_dict(payload)

    assert payload["id"].startswith("brief_")
    assert payload["node_id"] == "node-a"
    assert payload["run_id"] == "run-1"
    assert payload["worker_type"] == "web"
    assert payload["objective"] == "Probe login"
    assert payload["context_summary"] == ""
    assert payload["constraints"] == []
    assert payload["allowed_tool_names"] == []
    assert payload["blocked_tool_names"] == []
    assert payload["claim_ids"] == []
    assert payload["trace_ids"] == []
    assert payload["artifact_refs"] == []
    assert isinstance(payload["created_at"], float)
    assert payload["metadata"] == {}
    assert restored.id == payload["id"]
    assert restored.node_id == "node-a"
    assert restored.worker_type == "web"


def test_p3c_task_brief_restore_ignores_future_fields_and_coerces_lists() -> None:
    restored = task_brief_from_dict(
        {
            "id": "",
            "node_id": "node-a",
            "future_field": "ignored",
            "constraints": "stay quiet",
            "allowed_tool_names": ["browser", 2, "", None],
            "blocked_tool_names": ("sqlmap",),
            "claim_ids": {"claim": "ignored"},
            "trace_ids": "trace-1",
            "artifact_refs": ["artifact-1"],
            "metadata": "not-a-dict",
        }
    )

    assert restored.id.startswith("brief_")
    assert restored.constraints == ["stay quiet"]
    assert restored.allowed_tool_names == ["browser", "2"]
    assert restored.blocked_tool_names == ["sqlmap"]
    assert restored.claim_ids == []
    assert restored.trace_ids == ["trace-1"]
    assert restored.artifact_refs == ["artifact-1"]
    assert restored.metadata == {}


def test_p3c_task_brief_readback_redacts_sensitive_content() -> None:
    brief = TaskBrief(
        id="brief-redact",
        node_id="node-a",
        worker_type="web token=worker-token",
        objective=json.dumps({"token": "objective-token"}),
        context_summary="Use password=context-password",
        constraints=[
            "avoid cookie=constraint-cookie",
            json.dumps({"secret": "constraint-secret"}),
        ],
        allowed_tool_names=["browser authorization=tool-auth"],
        blocked_tool_names=["curl api_key=blocked-key"],
        artifact_refs=["http://ctf.local/?session=artifact-session"],
        metadata={
            "note": json.dumps({"password": "metadata-pass"}),
            "authorization": "Bearer metadata-auth",
        },
    )

    readback = build_task_brief_readback([brief])
    text = repr(readback)
    item = readback["briefs"][0]

    assert item["briefId"] == "brief-redact"
    assert item["nodeId"] == "node-a"
    assert "<redacted>" in text
    for leaked in (
        "worker-token",
        "objective-token",
        "context-password",
        "constraint-cookie",
        "constraint-secret",
        "tool-auth",
        "blocked-key",
        "artifact-session",
        "metadata-pass",
        "metadata-auth",
    ):
        assert leaked not in text


def test_p3c_solve_node_receipt_default_shape_and_round_trip() -> None:
    receipt = SolveNodeReceipt(
        node_id="node-a",
        run_id="run-1",
        worker_id="worker-1",
        worker_type="web",
        output_summary="Checked endpoint",
    )

    payload = solve_node_receipt_to_dict(receipt)
    restored = solve_node_receipt_from_dict(payload)

    assert payload["id"].startswith("node_receipt_")
    assert payload["node_id"] == "node-a"
    assert payload["run_id"] == "run-1"
    assert payload["worker_id"] == "worker-1"
    assert payload["worker_type"] == "web"
    assert payload["status"] == "completed"
    assert payload["started_at"] is None
    assert payload["finished_at"] is None
    assert payload["duration_ms"] is None
    assert payload["input_brief_id"] == ""
    assert payload["output_summary"] == "Checked endpoint"
    assert payload["claim_ids"] == []
    assert payload["trace_ids"] == []
    assert payload["artifact_refs"] == []
    assert payload["error_class"] == ""
    assert payload["error_summary"] == ""
    assert payload["metadata"] == {}
    assert restored.id == payload["id"]
    assert restored.status == "completed"


def test_p3c_solve_node_receipt_restore_unknown_fields_and_status_fallback() -> None:
    restored = solve_node_receipt_from_dict(
        {
            "id": "",
            "node_id": "node-a",
            "future_field": "ignored",
            "status": "future_status",
            "duration_ms": "42",
            "claim_ids": "claim-1",
            "trace_ids": ["trace-1", None],
            "artifact_refs": ("artifact-1",),
            "metadata": "not-a-dict",
        }
    )

    assert restored.id.startswith("node_receipt_")
    assert restored.status == "partial"
    assert restored.duration_ms == 42
    assert restored.claim_ids == ["claim-1"]
    assert restored.trace_ids == ["trace-1"]
    assert restored.artifact_refs == ["artifact-1"]
    assert restored.metadata == {}


def test_p3c_solve_node_receipt_readback_redacts_sensitive_content() -> None:
    receipt = SolveNodeReceipt(
        id="node-receipt-redact",
        node_id="node-a",
        worker_id="worker password=worker-pass",
        worker_type="web token=worker-token",
        status="failed",
        input_brief_id="brief-1",
        output_summary=json.dumps({"token": "output-token"}),
        error_class="HTTPError authorization=class-auth",
        error_summary="failed with secret=error-secret",
        artifact_refs=["file://loot/password=artifact-pass.txt"],
        metadata={
            "note": json.dumps({"api_key": "metadata-key"}),
            "cookie": "metadata-cookie",
        },
    )

    readback = build_solve_node_receipt_readback([receipt])
    text = repr(readback)
    item = readback["receipts"][0]

    assert item["receiptId"] == "node-receipt-redact"
    assert item["nodeId"] == "node-a"
    assert item["status"] == "failed"
    assert "<redacted>" in text
    for leaked in (
        "worker-pass",
        "worker-token",
        "output-token",
        "class-auth",
        "error-secret",
        "artifact-pass",
        "metadata-key",
        "metadata-cookie",
    ):
        assert leaked not in text


def test_p3c_contract_readback_limits_and_counts() -> None:
    briefs = [
        TaskBrief(id=f"brief-{index}", worker_type="web" if index < 2 else "crypto")
        for index in range(3)
    ]
    receipts = [
        SolveNodeReceipt(
            id=f"receipt-{index}",
            worker_type="web" if index < 2 else "crypto",
            status="completed" if index != 1 else "failed",
        )
        for index in range(3)
    ]

    brief_readback = build_task_brief_readback(briefs, limit=2)
    receipt_readback = build_solve_node_receipt_readback(receipts, limit=2)

    assert [item["briefId"] for item in brief_readback["briefs"]] == [
        "brief-1",
        "brief-2",
    ]
    assert brief_readback["summary"]["briefCount"] == 3
    assert brief_readback["summary"]["exportedBriefCount"] == 2
    assert brief_readback["summary"]["truncatedBriefCount"] == 1
    assert brief_readback["summary"]["workerTypeCounts"] == {"crypto": 1, "web": 2}
    assert [item["receiptId"] for item in receipt_readback["receipts"]] == [
        "receipt-1",
        "receipt-2",
    ]
    assert receipt_readback["summary"]["receiptCount"] == 3
    assert receipt_readback["summary"]["exportedReceiptCount"] == 2
    assert receipt_readback["summary"]["truncatedReceiptCount"] == 1
    assert receipt_readback["summary"]["statusCounts"] == {"completed": 2, "failed": 1}
    assert receipt_readback["summary"]["workerTypeCounts"] == {"crypto": 1, "web": 2}


def test_p3c_completed_receipt_does_not_emit_proof_fields() -> None:
    receipt = SolveNodeReceipt(
        id="receipt-completed",
        node_id="node-a",
        status="completed",
        claim_ids=["claim-candidate"],
        trace_ids=["trace-tool"],
    )

    payload = solve_node_receipt_to_dict(receipt)
    readback = build_solve_node_receipt_readback([receipt])

    assert payload["status"] == "completed"
    assert payload["claim_ids"] == ["claim-candidate"]
    assert payload["trace_ids"] == ["trace-tool"]
    for forbidden in ("verificationRecords", "verifiedFlags", "verifierProof"):
        assert forbidden not in payload
        assert forbidden not in readback
