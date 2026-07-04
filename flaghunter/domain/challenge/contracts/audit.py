from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list
from .sanitization import redact_sensitive_text


SCHEMA_VERSION = "p2.audit_evidence.v1"


@dataclass(frozen=True)
class AuditEvidenceExport:
    target: str = ""
    goal: str = ""
    stop_reason: str = ""
    claims: list[JsonValue] = field(default_factory=list)
    verification_records: list[JsonValue] = field(default_factory=list)
    execution_traces: list[JsonValue] = field(default_factory=list)
    p3_solve_snapshot: dict[str, JsonValue] = field(default_factory=dict)
    claim_count: int = 0
    verification_record_count: int = 0
    execution_trace_count: int = 0
    candidate_claim_count: int = 0
    accepted_claim_count: int = 0
    retracted_claim_count: int = 0
    preview_limit: int = 200

    def to_dict(self) -> dict[str, JsonValue]:
        return build_audit_evidence_payload(
            target=self.target,
            goal=self.goal,
            stop_reason=self.stop_reason,
            claims=self.claims,
            verification_records=self.verification_records,
            execution_traces=self.execution_traces,
            p3_solve_snapshot=self.p3_solve_snapshot,
            claim_count=self.claim_count,
            verification_record_count=self.verification_record_count,
            execution_trace_count=self.execution_trace_count,
            candidate_claim_count=self.candidate_claim_count,
            accepted_claim_count=self.accepted_claim_count,
            retracted_claim_count=self.retracted_claim_count,
            preview_limit=self.preview_limit,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AuditEvidenceExport":
        summary = coerce_json_dict(payload.get("summary"))
        return cls(
            target=str(payload.get("target", "")),
            goal=str(payload.get("goal", "")),
            stop_reason=str(payload.get("stopReason", "")),
            claims=coerce_json_list(payload.get("claims")),
            verification_records=coerce_json_list(payload.get("verificationRecords")),
            execution_traces=coerce_json_list(payload.get("executionTraces")),
            p3_solve_snapshot=coerce_json_dict(payload.get("p3SolveSnapshot")),
            claim_count=int(summary.get("claimCount", 0) or 0),
            verification_record_count=int(
                summary.get("verificationRecordCount", 0) or 0
            ),
            execution_trace_count=int(summary.get("executionTraceCount", 0) or 0),
            candidate_claim_count=int(summary.get("candidateClaimCount", 0) or 0),
            accepted_claim_count=int(summary.get("verifiedClaimCount", 0) or 0),
            retracted_claim_count=int(summary.get("retractedClaimCount", 0) or 0),
        )


def build_audit_evidence_payload(
    *,
    target: Any = "",
    goal: Any = "",
    stop_reason: Any = "",
    claims: list[Any] | None = None,
    verification_records: list[Any] | None = None,
    execution_traces: list[Any] | None = None,
    p3_solve_snapshot: Mapping[str, Any] | None = None,
    claim_count: int = 0,
    verification_record_count: int = 0,
    execution_trace_count: int = 0,
    candidate_claim_count: int = 0,
    accepted_claim_count: int = 0,
    retracted_claim_count: int = 0,
    preview_limit: int = 200,
) -> dict[str, JsonValue]:
    normalized_claims = coerce_json_list(claims)
    normalized_records = coerce_json_list(verification_records)
    normalized_traces = coerce_json_list(execution_traces)
    normalized_limit = max(1, int(preview_limit))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "target": _preview(target, limit=normalized_limit),
        "goal": _preview(goal, limit=normalized_limit),
        "stopReason": _preview(stop_reason, limit=normalized_limit),
        "summary": {
            "claimCount": int(claim_count),
            "exportedClaimCount": len(normalized_claims),
            "truncatedClaimCount": max(0, int(claim_count) - len(normalized_claims)),
            "verificationRecordCount": int(verification_record_count),
            "exportedVerificationRecordCount": len(normalized_records),
            "truncatedVerificationRecordCount": max(
                0,
                int(verification_record_count) - len(normalized_records),
            ),
            "executionTraceCount": int(execution_trace_count),
            "exportedExecutionTraceCount": len(normalized_traces),
            "truncatedExecutionTraceCount": max(
                0,
                int(execution_trace_count) - len(normalized_traces),
            ),
            "candidateClaimCount": int(candidate_claim_count),
            "verifiedClaimCount": int(accepted_claim_count),
            "retractedClaimCount": int(retracted_claim_count),
        },
        "claims": normalized_claims,
        "verificationRecords": normalized_records,
        "executionTraces": normalized_traces,
        "p3SolveSnapshot": coerce_json_dict(p3_solve_snapshot),
    }


def _preview(value: Any, *, limit: int) -> str:
    return redact_sensitive_text(str(value or ""))[: max(0, int(limit))]
