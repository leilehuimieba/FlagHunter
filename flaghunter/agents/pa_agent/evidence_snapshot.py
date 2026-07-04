"""Unified read-side P2 evidence snapshot contract."""

from __future__ import annotations

from typing import Any

from .audit_views import build_audit_evidence_export
from .ctf_state import CTFState
from .p3_solve_readback import build_p3_solve_readback


SCHEMA_VERSION = "p2.evidence_snapshot.v1"


def build_p2_evidence_snapshot(
    state: CTFState | None,
    *,
    trace_ref_limit: int = 5,
    claim_evidence_limit: int = 5,
    audit_claim_limit: int = 5,
    audit_trace_limit: int = 10,
    audit_verification_record_limit: int = 10,
    p3_node_limit: int = 20,
    p3_edge_limit: int = 50,
    p3_task_brief_limit: int = 20,
    p3_node_receipt_limit: int = 20,
    preview_limit: int = 160,
) -> dict[str, Any]:
    """Build a stable P2 read-side evidence snapshot.

    This function is intentionally read-only. It delegates nested projections to
    the existing P2 read models so redaction, truncation, and metadata allowlists
    stay centralized.
    """
    normalized_trace_ref_limit = max(0, int(trace_ref_limit))
    normalized_claim_evidence_limit = max(0, int(claim_evidence_limit))
    normalized_audit_claim_limit = max(0, int(audit_claim_limit))
    normalized_audit_trace_limit = max(0, int(audit_trace_limit))
    normalized_audit_record_limit = max(0, int(audit_verification_record_limit))
    normalized_preview_limit = max(1, int(preview_limit))
    normalized_p3_node_limit = max(0, int(p3_node_limit))
    normalized_p3_edge_limit = max(0, int(p3_edge_limit))
    normalized_p3_task_brief_limit = max(0, int(p3_task_brief_limit))
    normalized_p3_node_receipt_limit = max(0, int(p3_node_receipt_limit))

    trace_refs = (
        state.claim_trace_refs(limit=normalized_trace_ref_limit)
        if state is not None
        else []
    )
    claim_evidence_refs = (
        state.claim_evidence_refs(
            limit=normalized_claim_evidence_limit,
            preview_limit=normalized_preview_limit,
        )
        if state is not None
        else []
    )
    audit_export = build_audit_evidence_export(
        state,
        claim_limit=normalized_audit_claim_limit,
        trace_limit=normalized_audit_trace_limit,
        verification_record_limit=normalized_audit_record_limit,
        p3_node_limit=normalized_p3_node_limit,
        p3_edge_limit=normalized_p3_edge_limit,
        p3_task_brief_limit=normalized_p3_task_brief_limit,
        p3_node_receipt_limit=normalized_p3_node_receipt_limit,
        preview_limit=normalized_preview_limit,
    )
    p3_solve_snapshot = build_p3_solve_readback(
        state,
        node_limit=normalized_p3_node_limit,
        edge_limit=normalized_p3_edge_limit,
        task_brief_limit=normalized_p3_task_brief_limit,
        node_receipt_limit=normalized_p3_node_receipt_limit,
        preview_limit=normalized_preview_limit,
    )
    audit_summary = dict(audit_export.get("summary") or {})
    claim_count = int(audit_summary.get("claimCount", 0) or 0)
    trace_count = int(audit_summary.get("executionTraceCount", 0) or 0)
    record_count = int(audit_summary.get("verificationRecordCount", 0) or 0)
    trace_kinds = _trace_kinds(state)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "traceRefs": trace_refs,
        "claimEvidenceRefs": claim_evidence_refs,
        "auditEvidenceExport": audit_export,
        "p3SolveSnapshot": p3_solve_snapshot,
        "summary": {
            "claimCount": claim_count,
            "traceCount": trace_count,
            "verificationRecordCount": record_count,
            "hasVerifiedClaim": int(audit_summary.get("verifiedClaimCount", 0) or 0) > 0,
            "hasControlReceipt": "control_receipt" in trace_kinds,
            "hasToolReceipt": "tool_receipt" in trace_kinds,
            "hasVerificationReceipt": "verification_receipt" in trace_kinds,
            "truncated": {
                "traceRefs": max(0, claim_count - len(trace_refs)),
                "claimEvidenceRefs": max(0, claim_count - len(claim_evidence_refs)),
                "auditClaims": int(audit_summary.get("truncatedClaimCount", 0) or 0),
                "auditTraces": int(
                    audit_summary.get("truncatedExecutionTraceCount", 0) or 0
                ),
                "auditVerificationRecords": int(
                    audit_summary.get("truncatedVerificationRecordCount", 0) or 0
                ),
            },
        },
    }


def _trace_kinds(state: CTFState | None) -> set[str]:
    if state is None:
        return set()
    traces = getattr(state, "execution_traces_by_id", {}) or {}
    return {
        str(getattr(getattr(trace, "kind", ""), "value", getattr(trace, "kind", "")) or "")
        for trace in traces.values()
    }
