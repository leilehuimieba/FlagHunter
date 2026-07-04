"""Unified read-side P2 evidence snapshot contract."""

from __future__ import annotations

from typing import Any

from .audit_views import build_audit_evidence_export
from .ctf_state import CTFState
from .p3_solve_readback import build_p3_solve_readback
from flaghunter.domain.challenge.contracts.evidence_snapshot import (
    SCHEMA_VERSION,
    build_evidence_snapshot_payload,
)


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
    trace_kinds = _trace_kinds(state)

    return build_evidence_snapshot_payload(
        trace_refs=trace_refs,
        claim_evidence_refs=claim_evidence_refs,
        audit_evidence_export=audit_export,
        p3_solve_snapshot=p3_solve_snapshot,
        trace_kinds=trace_kinds,
    )


def _trace_kinds(state: CTFState | None) -> set[str]:
    if state is None:
        return set()
    traces = getattr(state, "execution_traces_by_id", {}) or {}
    return {
        str(getattr(getattr(trace, "kind", ""), "value", getattr(trace, "kind", "")) or "")
        for trace in traces.values()
    }
