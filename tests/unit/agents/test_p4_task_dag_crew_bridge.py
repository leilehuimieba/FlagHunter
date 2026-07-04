from __future__ import annotations

from flaghunter.agents.pa_agent.solve_node import SolveNodeReceipt, TaskBrief
from flaghunter.agents.pa_agent.task_dag_crew_bridge import (
    TASK_DAG_CREW_BRIDGE_RECEIPT_SCHEMA_VERSION,
    TASK_DAG_CREW_BRIDGE_REQUEST_SCHEMA_VERSION,
    TaskDAGCrewBridgeReceipt,
    TaskDAGCrewBridgeRequest,
    build_task_dag_crew_bridge_request,
    normalize_task_dag_crew_bridge_receipt,
)


def test_p4d_a_builds_compact_request_from_task_dict() -> None:
    request = build_task_dag_crew_bridge_request(
        {
            "taskId": "task-a",
            "taskBriefId": "brief-a",
            "kind": "exploit",
            "goal": "Use password=goal-password then check one endpoint",
            "workerType": "web",
            "dependsOn": ["task-parent"],
            "allowedToolNames": ["browser", "curl"],
            "allowedToolCategories": ["browser"],
            "traceIds": ["trace-a"],
            "claimIds": ["claim-a"],
            "metadata": {"source_kind": "dag", "authorization": "Bearer secret"},
        }
    )
    payload = request.to_dict()
    same = build_task_dag_crew_bridge_request(payload)

    assert isinstance(request, TaskDAGCrewBridgeRequest)
    assert payload["schemaVersion"] == TASK_DAG_CREW_BRIDGE_REQUEST_SCHEMA_VERSION
    assert payload["requestId"] == same.request_id
    assert payload["taskId"] == "task-a"
    assert payload["taskBriefId"] == "brief-a"
    assert payload["workerType"] == "web"
    assert payload["goal"] == "Use password=<redacted> then check one endpoint"
    assert payload["dependencyTaskIds"] == ["task-parent"]
    assert payload["allowedToolNames"] == ["browser", "curl"]
    assert payload["allowedToolCategories"] == ["browser"]
    assert payload["evidenceRefs"] == ["trace-a", "claim-a"]
    assert payload["metadata"]["source_kind"] == "dag"
    assert payload["metadata"]["authorization"] == "<redacted>"
    assert "task" not in payload
    assert "brief" not in payload


def test_p4d_a_request_accepts_task_brief_and_defaults_unknown_worker_type() -> None:
    brief = TaskBrief(
        id="brief-web",
        node_id="node-a",
        run_id="run-a",
        worker_type="future-worker",
        objective="Probe login form",
        context_summary="compact context",
        allowed_tool_names=["browser"],
        blocked_tool_names=["sqlmap"],
        trace_ids=["trace-a"],
        artifact_refs=["artifact-a"],
    )

    payload = build_task_dag_crew_bridge_request(brief).to_dict()

    assert payload["taskBriefId"] == "brief-web"
    assert payload["solveNodeId"] == "node-a"
    assert payload["workerType"] == "default"
    assert payload["goal"] == "Probe login form"
    assert payload["contextSummary"] == "compact context"
    assert payload["allowedToolNames"] == ["browser"]
    assert payload["blockedToolNames"] == ["sqlmap"]
    assert payload["evidenceRefs"] == ["trace-a", "artifact-a"]


def test_p4d_a_request_direct_dataclass_to_dict_strips_raw_sensitive_and_proof_like_fields() -> None:
    request = TaskDAGCrewBridgeRequest(
        schema_version="",
        request_id="request-a",
        task_id="task-a",
        task_brief_id="brief-a",
        solve_node_id="node-a",
        worker_type="web",
        goal="HTTP/1.1 200 OK\n<html>password=body-secret</html>",
        context_summary="Authorization: Bearer context-auth",
        allowed_tool_names=["browser token=tool-token"],
        blocked_tool_names=["curl api_key=blocked-key"],
        allowed_tool_categories=["browser"],
        dependency_task_ids=["task-parent"],
        evidence_refs=["trace-a"],
        warnings=[f"warning-{index}-" + ("W" * 300) for index in range(12)],
        metadata={
            "prompt": "do not emit",
            "verification_decision": "bad",
            "verified_flags": ["flag{bad}"],
            "note": 'level="verified"',
            "safe": "ok",
        },
    )
    payload = request.to_dict()
    text = repr(payload)

    assert payload["schemaVersion"] == TASK_DAG_CREW_BRIDGE_REQUEST_SCHEMA_VERSION
    assert payload["goal"] == "<redacted raw body>"
    assert len(payload["warnings"]) == 10
    assert payload["metadata"] == {"safe": "ok"}
    for leaked in (
        "body-secret",
        "context-auth",
        "tool-token",
        "blocked-key",
        "verification_decision",
        "verified_flags",
        'level="verified"',
        "flag{bad}",
    ):
        assert leaked not in text


def test_p4d_a_direct_dataclass_top_level_scalars_strip_proof_like_values() -> None:
    proof_like_single = "level='verified' flag{bad}"
    proof_like_double = 'level="verified" CTF{bad}'
    benign_request = TaskDAGCrewBridgeRequest(
        schema_version="",
        request_id="request-benign",
        task_id="task-a",
        task_brief_id="brief-a",
        solve_node_id="node-a",
        worker_type="web",
        goal="Collect login evidence",
        context_summary="Summarize page behavior",
    )
    request = TaskDAGCrewBridgeRequest(
        schema_version="",
        request_id="request-proof",
        task_id="task-a",
        task_brief_id="brief-a",
        solve_node_id="node-a",
        worker_type="web",
        goal=proof_like_single,
        context_summary=proof_like_double,
        evidence_refs=[proof_like_single],
        warnings=[proof_like_double],
        metadata={"safe": "ok"},
    )
    benign_receipt = TaskDAGCrewBridgeReceipt(
        schema_version="",
        receipt_id="receipt-benign",
        source_receipt_id="source-a",
        task_id="task-a",
        task_brief_id="brief-a",
        solve_node_id="node-a",
        worker_id="worker-a",
        worker_type="web",
        status="succeeded",
        summary="Worker returned compact summary",
        reason="No error",
    )
    receipt = TaskDAGCrewBridgeReceipt(
        schema_version="",
        receipt_id="receipt-proof",
        source_receipt_id="source-a",
        task_id="task-a",
        task_brief_id="brief-a",
        solve_node_id="node-a",
        worker_id="worker-a",
        worker_type="web",
        status="succeeded",
        summary=proof_like_single,
        reason=proof_like_double,
        error_class=proof_like_single,
        evidence_refs=[proof_like_single],
        warnings=[proof_like_double],
        metadata={"safe": "ok"},
    )
    request_payload = request.to_dict()
    receipt_payload = receipt.to_dict()
    text = repr({"request": request_payload, "receipt": receipt_payload})

    assert benign_request.to_dict()["goal"] == "Collect login evidence"
    assert benign_request.to_dict()["contextSummary"] == "Summarize page behavior"
    assert benign_receipt.to_dict()["summary"] == "Worker returned compact summary"
    assert benign_receipt.to_dict()["reason"] == "No error"
    assert request_payload["goal"] == "<redacted proof-like value>"
    assert request_payload["contextSummary"] == "<redacted proof-like value>"
    assert request_payload["evidenceRefs"] == ["<redacted proof-like value>"]
    assert request_payload["warnings"] == ["<redacted proof-like value>"]
    assert receipt_payload["summary"] == "<redacted proof-like value>"
    assert receipt_payload["reason"] == "<redacted proof-like value>"
    assert receipt_payload["errorClass"] == "<redacted proof-like value>"
    assert receipt_payload["evidenceRefs"] == ["<redacted proof-like value>"]
    assert receipt_payload["warnings"] == ["<redacted proof-like value>"]
    for leaked in (
        "level='verified'",
        'level="verified"',
        "flag{bad}",
        "CTF{bad}",
    ):
        assert leaked not in text


def test_p4d_a_normalizes_worker_result_like_receipt() -> None:
    receipt = normalize_task_dag_crew_bridge_receipt(
        {
            "taskId": "task-a",
            "workerId": "worker-a",
            "workerType": "exploit",
            "status": "succeeded",
            "summary": "Found candidate endpoint",
            "traceIds": ["trace-a"],
            "claimIds": ["claim-a"],
            "artifactRefs": ["artifact-a"],
            "metadata": {"source_kind": "worker"},
        }
    )
    payload = receipt.to_dict()
    same = normalize_task_dag_crew_bridge_receipt(payload)

    assert isinstance(receipt, TaskDAGCrewBridgeReceipt)
    assert payload["schemaVersion"] == TASK_DAG_CREW_BRIDGE_RECEIPT_SCHEMA_VERSION
    assert payload["receiptId"] == same.receipt_id
    assert payload["taskId"] == "task-a"
    assert payload["workerId"] == "worker-a"
    assert payload["workerType"] == "exploit"
    assert payload["status"] == "succeeded"
    assert payload["summary"] == "Found candidate endpoint"
    assert payload["evidenceRefs"] == ["trace-a", "claim-a", "artifact-a"]
    assert payload["metadata"]["source_kind"] == "worker"


def test_p4d_a_receipt_accepts_solve_node_receipt_and_maps_completed_to_succeeded() -> None:
    receipt = SolveNodeReceipt(
        id="solve-receipt-a",
        node_id="node-a",
        worker_id="worker-a",
        worker_type="crypto",
        status="completed",
        input_brief_id="brief-a",
        output_summary="Solved compactly",
        trace_ids=["trace-a"],
        claim_ids=["claim-a"],
        artifact_refs=["artifact-a"],
    )

    payload = normalize_task_dag_crew_bridge_receipt(receipt).to_dict()

    assert payload["sourceReceiptId"] == "solve-receipt-a"
    assert payload["solveNodeId"] == "node-a"
    assert payload["taskBriefId"] == "brief-a"
    assert payload["workerType"] == "crypto"
    assert payload["status"] == "succeeded"
    assert payload["summary"] == "Solved compactly"
    assert payload["evidenceRefs"] == ["trace-a", "claim-a", "artifact-a"]


def test_p4d_a_receipt_unknown_status_fails_closed_with_warning() -> None:
    payload = normalize_task_dag_crew_bridge_receipt(
        {
            "taskId": "task-a",
            "workerType": "web",
            "status": "future-status",
            "summary": "worker output",
        }
    ).to_dict()

    assert payload["status"] == "failed"
    assert "invalid_status" in payload["warnings"]


def test_p4d_a_receipt_direct_dataclass_to_dict_strips_raw_sensitive_and_proof_like_fields() -> None:
    receipt = TaskDAGCrewBridgeReceipt(
        schema_version="",
        receipt_id="receipt-a",
        source_receipt_id="source-a",
        task_id="task-a",
        task_brief_id="brief-a",
        solve_node_id="node-a",
        worker_id="worker-a",
        worker_type="web",
        status="succeeded",
        summary="token=summary-token",
        reason="HTTP/1.1 500 ERROR\n<html>secret=body-secret</html>",
        evidence_refs=["trace-a"],
        warnings=["warn-a"],
        metadata={
            "stdout": "raw",
            "verification_decision": "bad",
            "verified_flags": ["flag{bad}"],
            "authorization": "Bearer metadata-auth",
            "safe": "ok",
        },
    )
    payload = receipt.to_dict()
    text = repr(payload)

    assert payload["schemaVersion"] == TASK_DAG_CREW_BRIDGE_RECEIPT_SCHEMA_VERSION
    assert payload["summary"] == "token=<redacted>"
    assert payload["reason"] == "<redacted raw body>"
    assert payload["metadata"] == {"authorization": "<redacted>", "safe": "ok"}
    for leaked in (
        "summary-token",
        "body-secret",
        "verification_decision",
        "verified_flags",
        "flag{bad}",
        "metadata-auth",
    ):
        assert leaked not in text


def test_p4d_a_bridge_outputs_do_not_serialize_full_inputs_or_body_like_payloads() -> None:
    request_text = repr(
        build_task_dag_crew_bridge_request(
            {
                "taskId": "task-a",
                "workerType": "web",
                "goal": "Use one compact step",
                "prompt": "raw prompt",
                "completion": "raw completion",
                "request": {"body": "raw request"},
                "response": {"body": "raw response"},
                "command_line": "curl http://ctf.local",
                "metadata": {"body": "raw body", "safe": "ok"},
            }
        ).to_dict()
    )
    receipt_text = repr(
        normalize_task_dag_crew_bridge_receipt(
            {
                "taskId": "task-a",
                "status": "failed",
                "stdout": "raw stdout",
                "stderr": "raw stderr",
                "response": {"body": "raw response"},
                "summary": "Use compact summary",
            }
        ).to_dict()
    )

    for text in (request_text, receipt_text):
        for forbidden in (
            "raw prompt",
            "raw completion",
            "raw request",
            "raw response",
            "curl http://ctf.local",
            "raw stdout",
            "raw stderr",
            "raw body",
        ):
            assert forbidden not in text
