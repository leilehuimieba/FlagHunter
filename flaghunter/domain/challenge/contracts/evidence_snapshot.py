from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list


SCHEMA_VERSION = "p2.evidence_snapshot.v1"


@dataclass(frozen=True)
class EvidenceSnapshot:
    trace_refs: list[JsonValue] = field(default_factory=list)
    claim_evidence_refs: list[JsonValue] = field(default_factory=list)
    audit_evidence_export: dict[str, JsonValue] = field(default_factory=dict)
    p3_solve_snapshot: dict[str, JsonValue] = field(default_factory=dict)
    trace_kinds: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, JsonValue]:
        return build_evidence_snapshot_payload(
            trace_refs=self.trace_refs,
            claim_evidence_refs=self.claim_evidence_refs,
            audit_evidence_export=self.audit_evidence_export,
            p3_solve_snapshot=self.p3_solve_snapshot,
            trace_kinds=self.trace_kinds,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceSnapshot":
        return cls(
            trace_refs=coerce_json_list(payload.get("traceRefs")),
            claim_evidence_refs=coerce_json_list(payload.get("claimEvidenceRefs")),
            audit_evidence_export=coerce_json_dict(payload.get("auditEvidenceExport")),
            p3_solve_snapshot=coerce_json_dict(payload.get("p3SolveSnapshot")),
            trace_kinds=_trace_kinds_from_summary(payload.get("summary")),
        )


def build_evidence_snapshot_payload(
    *,
    trace_refs: list[Any] | None = None,
    claim_evidence_refs: list[Any] | None = None,
    audit_evidence_export: Mapping[str, Any] | None = None,
    p3_solve_snapshot: Mapping[str, Any] | None = None,
    trace_kinds: Iterable[str] | None = None,
) -> dict[str, JsonValue]:
    normalized_trace_refs = coerce_json_list(trace_refs)
    normalized_claim_evidence_refs = coerce_json_list(claim_evidence_refs)
    normalized_audit_export = coerce_json_dict(audit_evidence_export)
    normalized_p3_snapshot = coerce_json_dict(p3_solve_snapshot)
    audit_summary = coerce_json_dict(normalized_audit_export.get("summary"))
    claim_count = int(audit_summary.get("claimCount", 0) or 0)
    trace_count = int(audit_summary.get("executionTraceCount", 0) or 0)
    record_count = int(audit_summary.get("verificationRecordCount", 0) or 0)
    normalized_trace_kinds = {str(item or "") for item in list(trace_kinds or [])}

    return {
        "schemaVersion": SCHEMA_VERSION,
        "traceRefs": normalized_trace_refs,
        "claimEvidenceRefs": normalized_claim_evidence_refs,
        "auditEvidenceExport": normalized_audit_export,
        "p3SolveSnapshot": normalized_p3_snapshot,
        "summary": {
            "claimCount": claim_count,
            "traceCount": trace_count,
            "verificationRecordCount": record_count,
            "hasVerifiedClaim": int(audit_summary.get("verifiedClaimCount", 0) or 0)
            > 0,
            "hasControlReceipt": "control_receipt" in normalized_trace_kinds,
            "hasToolReceipt": "tool_receipt" in normalized_trace_kinds,
            "hasVerificationReceipt": "verification_receipt" in normalized_trace_kinds,
            "truncated": {
                "traceRefs": max(0, claim_count - len(normalized_trace_refs)),
                "claimEvidenceRefs": max(
                    0,
                    claim_count - len(normalized_claim_evidence_refs),
                ),
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


def _trace_kinds_from_summary(summary: Any) -> set[str]:
    normalized = coerce_json_dict(summary)
    kinds: set[str] = set()
    if normalized.get("hasControlReceipt"):
        kinds.add("control_receipt")
    if normalized.get("hasToolReceipt"):
        kinds.add("tool_receipt")
    if normalized.get("hasVerificationReceipt"):
        kinds.add("verification_receipt")
    return kinds
