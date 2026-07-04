from __future__ import annotations

import json

from flaghunter.agents.pa_agent.audit_views import build_audit_evidence_export
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.evidence_snapshot import build_p2_evidence_snapshot
from flaghunter.agents.pa_agent.solve_node import (
    SolveNode,
    SolveNodeReceipt,
    TaskBrief,
)


def _state_with_p3_contracts() -> CTFState:
    state = CTFState(target="http://ctf.local", goal="get flag")
    node_id = state.record_solve_node(
        SolveNode(
            id="node-p3",
            title=json.dumps({"token": "node-token"}),
            goal="try exploit password=node-password",
            summary="node summary secret=node-secret",
            artifact_refs=["http://ctf.local/a?session=node-session"],
            metadata={"note": json.dumps({"api_key": "node-key"})},
        )
    )
    brief_id = state.record_task_brief(
        TaskBrief(
            id="brief-p3",
            node_id=node_id,
            worker_type="web token=worker-token",
            objective=json.dumps({"token": "brief-token"}),
            context_summary="context password=brief-password",
            constraints=["avoid cookie=brief-cookie"],
            allowed_tool_names=["curl api_key=brief-key"],
            artifact_refs=["file://loot/secret=brief-secret.txt"],
            metadata={"session": "brief-session"},
        )
    )
    state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-p3",
            node_id=node_id,
            input_brief_id=brief_id,
            worker_type="web secret=receipt-worker-secret",
            status="completed",
            output_summary=json.dumps({"authorization": "receipt-auth"}),
            error_summary="password=receipt-password",
            artifact_refs=["http://ctf.local/r?token=receipt-token"],
            metadata={"cookie": "receipt-cookie"},
        )
    )
    return state


def test_p3_evidence_snapshot_includes_compact_solve_readback() -> None:
    state = _state_with_p3_contracts()
    before_claims = dict(state.claims_by_id)
    before_flags = list(state.verified_flags)

    snapshot = build_p2_evidence_snapshot(state)

    p3 = snapshot["p3SolveSnapshot"]
    assert p3["schemaVersion"] == "p3.solve_readback.v1"
    assert p3["summary"]["nodeCount"] == 1
    assert p3["summary"]["taskBriefCount"] == 1
    assert p3["summary"]["solveNodeReceiptCount"] == 1
    assert p3["summary"]["hasSolveNodes"] is True
    assert p3["summary"]["hasTaskBriefs"] is True
    assert p3["summary"]["hasSolveNodeReceipts"] is True
    assert p3["solveGraph"]["nodes"][0]["nodeId"] == "node-p3"
    assert p3["taskBriefs"]["briefs"][0]["briefId"] == "brief-p3"
    assert p3["solveNodeReceipts"]["receipts"][0]["receiptId"] == "receipt-p3"
    assert state.claims_by_id == before_claims
    assert state.verified_flags == before_flags

    snapshot_text = repr(snapshot)
    for leaked in (
        "node-token",
        "node-password",
        "node-secret",
        "node-session",
        "node-key",
        "worker-token",
        "brief-token",
        "brief-password",
        "brief-cookie",
        "brief-key",
        "brief-secret",
        "brief-session",
        "receipt-worker-secret",
        "receipt-auth",
        "receipt-password",
        "receipt-token",
        "receipt-cookie",
    ):
        assert leaked not in snapshot_text
    assert snapshot["summary"]["hasVerifiedClaim"] is False


def test_p3_evidence_snapshot_none_state_has_empty_p3_shape() -> None:
    snapshot = build_p2_evidence_snapshot(None)

    assert snapshot["p3SolveSnapshot"]["schemaVersion"] == "p3.solve_readback.v1"
    assert snapshot["p3SolveSnapshot"]["summary"]["nodeCount"] == 0
    assert snapshot["p3SolveSnapshot"]["summary"]["edgeCount"] == 0
    assert snapshot["p3SolveSnapshot"]["summary"]["taskBriefCount"] == 0
    assert snapshot["p3SolveSnapshot"]["summary"]["solveNodeReceiptCount"] == 0
    assert snapshot["p3SolveSnapshot"]["summary"]["hasSolveNodes"] is False
    assert snapshot["p3SolveSnapshot"]["summary"]["hasTaskBriefs"] is False
    assert snapshot["p3SolveSnapshot"]["summary"]["hasSolveNodeReceipts"] is False


def test_p3_audit_export_includes_compact_solve_readback_without_proof_upgrade() -> None:
    state = _state_with_p3_contracts()
    before_claims = dict(state.claims_by_id)
    before_flags = list(state.verified_flags)

    export = build_audit_evidence_export(state)

    p3 = export["p3SolveSnapshot"]
    assert p3["summary"]["nodeCount"] == 1
    assert p3["summary"]["taskBriefCount"] == 1
    assert p3["summary"]["solveNodeReceiptCount"] == 1
    assert p3["solveNodeReceipts"]["summary"]["statusCounts"] == {"completed": 1}
    assert state.claims_by_id == before_claims
    assert state.verified_flags == before_flags
    assert export["summary"]["verifiedClaimCount"] == 0

    export_text = repr(export)
    for leaked in (
        "node-token",
        "brief-token",
        "brief-password",
        "receipt-auth",
        "receipt-password",
        "receipt-token",
    ):
        assert leaked not in export_text
