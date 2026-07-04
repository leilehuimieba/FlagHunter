from __future__ import annotations

import json

from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.solve_node import (
    SolveNode,
    SolveNodeReceipt,
    TaskBrief,
    build_solve_graph_readback,
    build_solve_node_receipt_readback,
    build_task_brief_readback,
)


def test_p3d_empty_and_legacy_snapshot_restore_has_empty_p3_store() -> None:
    state = CTFState.from_snapshot({"target": "http://ctf.local", "goal": "get flag"})

    assert state.solve_node_graph.to_dict()["summary"]["nodeCount"] == 0
    assert state.solve_node_graph.to_dict()["summary"]["edgeCount"] == 0
    assert state.task_briefs_by_id == {}
    assert state.solve_node_receipts_by_id == {}


def test_p3d_record_p3_contracts_round_trip_through_snapshot() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")

    node_id = state.record_solve_node(
        SolveNode(id="node-a", title="Attempt web exploit")
    )
    brief_id = state.record_task_brief(
        TaskBrief(id="brief-a", node_id=node_id, objective="Run web strategy")
    )
    receipt_id = state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-a",
            node_id=node_id,
            input_brief_id=brief_id,
            status="completed",
            output_summary="Strategy finished",
        )
    )

    restored = CTFState.from_snapshot(state.to_snapshot())

    assert restored.get_solve_node(node_id).title == "Attempt web exploit"
    assert restored.get_task_brief(brief_id).objective == "Run web strategy"
    assert restored.get_solve_node_receipt(receipt_id).output_summary == "Strategy finished"
    assert restored.solve_node_graph.to_dict()["summary"]["nodeCount"] == 1
    assert restored.solve_node_graph.to_dict()["summary"]["edgeCount"] == 0


def test_p3d_malformed_legacy_p3_snapshot_does_not_crash() -> None:
    restored = CTFState.from_snapshot(
        {
            "target": "http://ctf.local",
            "goal": "get flag",
            "solve_node_graph": {
                "nodes": [{"id": "node-a"}, {"future": "ignored"}],
                "edges": [{}],
            },
            "task_briefs_by_id": {
                "brief-a": {"id": "brief-a", "metadata": "not-a-dict"},
                "bad": "not-a-dict",
            },
            "solve_node_receipts_by_id": {
                "receipt-a": {"id": "receipt-a", "status": "future"},
                "bad": "not-a-dict",
            },
        }
    )

    assert restored.solve_node_graph.to_dict()["summary"]["nodeCount"] == 2
    assert restored.solve_node_graph.to_dict()["summary"]["restoreWarningCount"] == 1
    assert restored.get_task_brief("brief-a").metadata == {}
    assert restored.get_solve_node_receipt("receipt-a").status == "partial"


def test_p3d_p3_state_store_redacts_sensitive_values_in_snapshot_and_readback() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    node_id = state.record_solve_node(
        SolveNode(
            id="node-redact",
            title=json.dumps({"token": "node-token"}),
            summary="Use password=node-password",
            artifact_refs=["http://ctf.local/?session=node-session"],
            metadata={"note": json.dumps({"secret": "node-secret"})},
        )
    )
    brief_id = state.record_task_brief(
        TaskBrief(
            id="brief-redact",
            node_id=node_id,
            objective=json.dumps({"token": "brief-token"}),
            allowed_tool_names=["curl api_key=brief-key"],
            artifact_refs=["file://loot/password=brief-pass.txt"],
            metadata={"cookie": "brief-cookie"},
        )
    )
    state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-redact",
            node_id=node_id,
            input_brief_id=brief_id,
            output_summary=json.dumps({"authorization": "receipt-auth"}),
            error_summary="secret=receipt-secret",
            artifact_refs=["http://ctf.local/?token=receipt-token"],
            metadata={"password": "receipt-pass"},
        )
    )

    snapshot_text = repr(state.to_snapshot())
    readback_text = repr(
        {
            "graph": build_solve_graph_readback(state.solve_node_graph),
            "briefs": build_task_brief_readback(list(state.task_briefs_by_id.values())),
            "receipts": build_solve_node_receipt_readback(
                list(state.solve_node_receipts_by_id.values())
            ),
        }
    )

    for leaked in (
        "node-token",
        "node-password",
        "node-session",
        "node-secret",
        "brief-token",
        "brief-key",
        "brief-pass",
        "brief-cookie",
        "receipt-auth",
        "receipt-secret",
        "receipt-token",
        "receipt-pass",
    ):
        assert leaked not in snapshot_text
        assert leaked not in readback_text
    assert "<redacted>" in snapshot_text
    assert "<redacted>" in readback_text


def test_p3d_snapshot_redacts_direct_p3_store_mutation() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.solve_node_graph.add_node(
        SolveNode(
            id="node-direct",
            title=json.dumps({"token": "direct-node-token"}),
            metadata={"note": json.dumps({"password": "direct-node-password"})},
        )
    )
    state.task_briefs_by_id["brief-direct"] = TaskBrief(
        id="brief-direct",
        objective=json.dumps({"secret": "direct-brief-secret"}),
        metadata={"cookie": "direct-brief-cookie"},
    )
    state.solve_node_receipts_by_id["receipt-direct"] = SolveNodeReceipt(
        id="receipt-direct",
        status="completed",
        output_summary=json.dumps({"authorization": "direct-receipt-auth"}),
        error_summary="session=direct-receipt-session",
    )

    snapshot_text = repr(state.to_snapshot())

    for leaked in (
        "direct-node-token",
        "direct-node-password",
        "direct-brief-secret",
        "direct-brief-cookie",
        "direct-receipt-auth",
        "direct-receipt-session",
    ):
        assert leaked not in snapshot_text
    assert "<redacted>" in snapshot_text


def test_p3d_completed_receipt_does_not_change_claims_or_verified_flags() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")

    state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-completed",
            node_id="node-a",
            status="completed",
            claim_ids=["claim-candidate"],
            trace_ids=["trace-tool"],
        )
    )

    assert state.claims_by_id == {}
    assert state.verified_flags == []
    assert state.get_solve_node_receipt("receipt-completed").status == "completed"
