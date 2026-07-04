from __future__ import annotations

import json

from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent import p3_solve_readback
from flaghunter.agents.pa_agent.solve_node import (
    SolveNode,
    SolveNodeReceipt,
    TaskBrief,
)


def _state_with_worker_contracts() -> CTFState:
    state = CTFState(target="http://ctf.local", goal="get flag")
    node_a = state.record_solve_node(
        SolveNode(id="node-web", title="web worker token=node-token")
    )
    node_b = state.record_solve_node(
        SolveNode(id="node-recon", title="recon worker")
    )
    brief_a = state.record_task_brief(
        TaskBrief(
            id="brief-web",
            node_id=node_a,
            worker_type="web token=worker-token",
            objective=json.dumps({"password": "brief-pass"}),
            allowed_tool_names=["curl api_key=brief-key"],
        )
    )
    brief_b = state.record_task_brief(
        TaskBrief(
            id="brief-recon",
            node_id=node_b,
            worker_type="recon",
            objective="map target",
        )
    )
    state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-web",
            node_id=node_a,
            input_brief_id=brief_a,
            worker_id="worker-web cookie=worker-cookie",
            worker_type="web token=worker-token",
            status="completed",
            output_summary=json.dumps({"authorization": "receipt-auth"}),
            error_summary="secret=receipt-secret",
        )
    )
    state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-recon",
            node_id=node_b,
            input_brief_id=brief_b,
            worker_id="worker-recon",
            worker_type="recon",
            status="partial",
            output_summary="needs follow up",
        )
    )
    return state


def test_p3f_crew_trace_readback_empty_shape_is_stable() -> None:
    readback = p3_solve_readback.build_p3_crew_trace_readback(None)

    assert readback == {
        "schemaVersion": "p3.crew_trace_readback.v1",
        "workers": [],
        "handoffs": [],
        "nodeRefs": [],
        "receiptRefs": [],
        "summary": {
            "workerCount": 0,
            "handoffCount": 0,
            "nodeCount": 0,
            "receiptCount": 0,
            "workerTypeCounts": {},
            "receiptStatusCounts": {},
            "truncated": {
                "workers": 0,
                "handoffs": 0,
                "nodeRefs": 0,
                "receiptRefs": 0,
            },
        },
    }


def test_p3f_crew_trace_readback_aggregates_workers_receipts_and_redacts() -> None:
    state = _state_with_worker_contracts()
    before_claims = dict(state.claims_by_id)
    before_flags = list(state.verified_flags)

    readback = p3_solve_readback.build_p3_crew_trace_readback(state)

    assert readback["summary"]["workerCount"] == 2
    assert readback["summary"]["nodeCount"] == 2
    assert readback["summary"]["receiptCount"] == 2
    assert readback["summary"]["workerTypeCounts"] == {
        "recon": 1,
        "web token=<redacted>": 1,
    }
    assert readback["summary"]["receiptStatusCounts"] == {
        "completed": 1,
        "partial": 1,
    }
    assert {item["workerId"] for item in readback["workers"]} == {
        "worker-web cookie=<redacted>",
        "worker-recon",
    }
    assert {item["receiptId"] for item in readback["receiptRefs"]} == {
        "receipt-web",
        "receipt-recon",
    }
    assert state.claims_by_id == before_claims
    assert state.verified_flags == before_flags

    text = repr(readback)
    for leaked in (
        "node-token",
        "worker-token",
        "brief-pass",
        "brief-key",
        "worker-cookie",
        "receipt-auth",
        "receipt-secret",
    ):
        assert leaked not in text
    assert "<redacted>" in text


def test_p3f_crew_trace_readback_limits_and_truncation() -> None:
    state = _state_with_worker_contracts()

    readback = p3_solve_readback.build_p3_crew_trace_readback(
        state,
        worker_limit=1,
        node_ref_limit=1,
        receipt_ref_limit=1,
    )

    assert len(readback["workers"]) == 1
    assert len(readback["nodeRefs"]) == 1
    assert len(readback["receiptRefs"]) == 1
    assert readback["summary"]["truncated"] == {
        "workers": 1,
        "handoffs": 0,
        "nodeRefs": 1,
        "receiptRefs": 1,
    }


def test_p3f_solve_readback_nests_crew_trace_summary() -> None:
    state = _state_with_worker_contracts()

    snapshot = p3_solve_readback.build_p3_solve_readback(state)

    assert snapshot["crewTrace"]["schemaVersion"] == "p3.crew_trace_readback.v1"
    assert snapshot["crewTrace"]["summary"]["workerCount"] == 2
    assert snapshot["summary"]["crewWorkerCount"] == 2
    assert snapshot["summary"]["crewReceiptCount"] == 2


def test_p3f_matching_brief_and_receipt_do_not_double_count_worker_type() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    node_id = state.record_solve_node(SolveNode(id="node-one-worker"))
    brief_id = state.record_task_brief(
        TaskBrief(id="brief-one-worker", node_id=node_id, worker_type="web")
    )
    state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-one-worker",
            node_id=node_id,
            input_brief_id=brief_id,
            worker_id="worker-one",
            worker_type="web",
            status="completed",
        )
    )

    snapshot = p3_solve_readback.build_p3_solve_readback(state)

    assert snapshot["summary"]["crewWorkerCount"] == 1
    assert snapshot["summary"]["crewWorkerTypeCounts"] == {"web": 1}
    assert snapshot["crewTrace"]["summary"]["workerTypeCounts"] == {"web": 1}
