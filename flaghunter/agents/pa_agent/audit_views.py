"""Compact read-only audit exports for P2 execution evidence."""

from __future__ import annotations

import re
from typing import Any

from .ctf_state import CTFState
from .p3_solve_readback import build_p3_solve_readback


SCHEMA_VERSION = "p2.audit_evidence.v1"
_ALLOWED_TRACE_METADATA_KEYS = {
    "tool_name",
    "status",
    "error_class",
    "duration_ms",
    "cache_hit",
    "source_channel",
    "stop_reason",
    "finish_status",
    "selected_claim_id",
    "selected_verification_record_id",
    "selected_trace_id",
    "answer_kind",
}


def build_audit_evidence_export(
    state: CTFState | None,
    *,
    claim_limit: int = 20,
    trace_limit: int = 50,
    verification_record_limit: int = 50,
    p3_node_limit: int = 20,
    p3_edge_limit: int = 50,
    p3_task_brief_limit: int = 20,
    p3_node_receipt_limit: int = 20,
    preview_limit: int = 200,
) -> dict[str, Any]:
    """Build a compact, serializable audit view from the current CTF state.

    This is intentionally read-only. It projects claims, verification records,
    and execution traces into a bounded report-friendly shape without exporting
    raw tool output, full response bodies, cookies, tokens, or unrestricted
    metadata.
    """
    normalized_claim_limit = max(0, int(claim_limit))
    normalized_trace_limit = max(0, int(trace_limit))
    normalized_record_limit = max(0, int(verification_record_limit))
    normalized_preview_limit = max(1, int(preview_limit))
    p3_solve_snapshot = build_p3_solve_readback(
        state,
        node_limit=p3_node_limit,
        edge_limit=p3_edge_limit,
        task_brief_limit=p3_task_brief_limit,
        node_receipt_limit=p3_node_receipt_limit,
        preview_limit=normalized_preview_limit,
    )
    claims = list(getattr(state, "claims_by_id", {}).values()) if state is not None else []
    records = (
        list(getattr(state, "verification_records_by_id", {}).values())
        if state is not None
        else []
    )
    traces = (
        list(getattr(state, "execution_traces_by_id", {}).values())
        if state is not None
        else []
    )

    sorted_claims = _recent_first(claims)[:normalized_claim_limit]
    sorted_records = sorted(
        records,
        key=lambda record: (
            float(getattr(record, "created_at", 0.0) or 0.0),
            str(getattr(record, "id", "") or ""),
        ),
        reverse=True,
    )[:normalized_record_limit]
    sorted_traces = sorted(
        traces,
        key=lambda trace: (
            float(getattr(trace, "created_at", 0.0) or 0.0),
            str(getattr(trace, "id", "") or ""),
        ),
        reverse=True,
    )[:normalized_trace_limit]

    return {
        "schemaVersion": SCHEMA_VERSION,
        "target": _preview(
            getattr(state, "target", "") if state is not None else "",
            limit=normalized_preview_limit,
        ),
        "goal": _preview(
            getattr(state, "goal", "") if state is not None else "",
            limit=normalized_preview_limit,
        ),
        "stopReason": _preview(
            getattr(state, "stop_reason", "") if state is not None else "",
            limit=normalized_preview_limit,
        ),
        "summary": {
            "claimCount": len(claims),
            "exportedClaimCount": len(sorted_claims),
            "truncatedClaimCount": max(0, len(claims) - len(sorted_claims)),
            "verificationRecordCount": len(records),
            "exportedVerificationRecordCount": len(sorted_records),
            "truncatedVerificationRecordCount": max(0, len(records) - len(sorted_records)),
            "executionTraceCount": len(traces),
            "exportedExecutionTraceCount": len(sorted_traces),
            "truncatedExecutionTraceCount": max(0, len(traces) - len(sorted_traces)),
            "candidateClaimCount": sum(1 for claim in claims if _claim_level(claim) == "conjecture"),
            "verifiedClaimCount": sum(1 for claim in claims if _claim_level(claim) == "verified"),
            "retractedClaimCount": sum(
                1
                for claim in claims
                if _claim_level(claim) == "retracted" or _claim_status(claim) == "retracted"
            ),
        },
        "claims": [
            _claim_export(state, claim, preview_limit=normalized_preview_limit)
            for claim in sorted_claims
        ],
        "verificationRecords": [
            _verification_record_export(record, preview_limit=normalized_preview_limit)
            for record in sorted_records
        ],
        "executionTraces": [
            _execution_trace_export(trace, preview_limit=normalized_preview_limit)
            for trace in sorted_traces
        ],
        "p3SolveSnapshot": p3_solve_snapshot,
    }


def _recent_first(items: list[Any]) -> list[Any]:
    return sorted(
        items,
        key=lambda item: (
            float(
                getattr(item, "updated_at", None)
                or getattr(item, "created_at", 0.0)
                or 0.0
            ),
            str(getattr(item, "id", "") or ""),
        ),
        reverse=True,
    )


def _claim_export(state: CTFState | None, claim: Any, *, preview_limit: int) -> dict[str, Any]:
    records = []
    record_store = getattr(state, "verification_records_by_id", {}) if state is not None else {}
    for record_id in list(getattr(claim, "verification_record_ids", []) or []):
        record = record_store.get(record_id)
        if record is not None:
            records.append(record)
    latest_record = max(
        records,
        key=lambda record: float(getattr(record, "created_at", 0.0) or 0.0),
        default=None,
    )
    metadata = dict(getattr(claim, "metadata", {}) or {})
    evidence_trace_ids = list(
        dict.fromkeys(
            str(item).strip()
            for item in list(getattr(claim, "evidence_trace_ids", []) or [])
            if str(item).strip()
        )
    )
    verification_record_ids = [
        str(item).strip()
        for item in list(getattr(claim, "verification_record_ids", []) or [])
        if str(item).strip()
    ]
    return {
        "claimId": str(getattr(claim, "id", "") or ""),
        "kind": _enum_value(getattr(claim, "kind", "")),
        "level": _claim_level(claim),
        "status": _claim_status(claim),
        "contentPreview": _preview(getattr(claim, "content", ""), limit=preview_limit),
        "primaryTraceId": str(getattr(claim, "primary_trace_id", "") or ""),
        "evidenceTraceIds": evidence_trace_ids,
        "verificationRecordIds": verification_record_ids,
        "latestVerificationDecision": (
            _enum_value(getattr(latest_record, "decision", "")) if latest_record is not None else ""
        ),
        "sourceTool": str(metadata.get("source_tool") or "").strip(),
        "sourceTraceId": str(metadata.get("source_trace_id") or "").strip(),
        "sourceReceiptId": str(metadata.get("source_receipt_id") or "").strip(),
    }


def _verification_record_export(record: Any, *, preview_limit: int) -> dict[str, Any]:
    return {
        "recordId": str(getattr(record, "id", "") or ""),
        "claimId": str(getattr(record, "claim_id", "") or ""),
        "decision": _enum_value(getattr(record, "decision", "")),
        "method": _enum_value(getattr(record, "method", "")),
        "passed": bool(getattr(record, "passed", False)),
        "sufficientForUpgrade": bool(getattr(record, "sufficient_for_upgrade", False)),
        "traceId": str(getattr(record, "trace_id", "") or ""),
        "evidenceTraceIds": [
            str(item).strip()
            for item in list(getattr(record, "evidence_trace_ids", []) or [])
            if str(item).strip()
        ],
        "evidenceSummaryPreview": _body_safe_preview(
            getattr(record, "evidence_summary", ""),
            limit=preview_limit,
        ),
        "rationalePreview": _preview(getattr(record, "rationale", ""), limit=preview_limit),
    }


def _execution_trace_export(trace: Any, *, preview_limit: int) -> dict[str, Any]:
    return {
        "traceId": str(getattr(trace, "id", "") or ""),
        "receiptId": str(getattr(trace, "receipt_id", "") or ""),
        "kind": _enum_value(getattr(trace, "kind", "")),
        "producer": str(getattr(trace, "producer", "") or ""),
        "success": bool(getattr(trace, "success", False)),
        "outputPreview": _body_safe_preview(
            getattr(trace, "output_summary", ""),
            limit=preview_limit,
        ),
        "artifactRefs": [
            _preview(item, limit=preview_limit)
            for item in list(getattr(trace, "artifact_refs", []) or [])
            if str(item).strip()
        ],
        "metadata": _allowlisted_metadata(dict(getattr(trace, "metadata", {}) or {})),
    }


def _allowlisted_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _metadata_value(metadata[key])
        for key in sorted(_ALLOWED_TRACE_METADATA_KEYS)
        if key in metadata
    }


def _metadata_value(value: Any) -> Any:
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return _redact(str(value or ""))[:200]


def _claim_level(claim: Any) -> str:
    return _enum_value(getattr(claim, "level", ""))


def _claim_status(claim: Any) -> str:
    return _enum_value(getattr(claim, "status", ""))


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip()


def _preview(value: Any, *, limit: int) -> str:
    return _redact(str(value or ""))[: max(0, int(limit))]


def _body_safe_preview(value: Any, *, limit: int) -> str:
    text = _redact(str(value or ""))
    if _looks_like_raw_body(text):
        return "<redacted raw body>"[: max(0, int(limit))]
    return text[: max(0, int(limit))]


def _looks_like_raw_body(text: str) -> bool:
    if not text:
        return False
    return any(
        re.search(pattern, text)
        for pattern in (
            r"(?im)^\s*PING\s+",
            r"(?im)^\s*\d+\s+bytes\s+from\s+",
            r"(?im)^\s*uid=\d+\(",
            r"(?im)^\s*gid=\d+\(",
            r"(?im)^\s*HTTP/\d(?:\.\d)?\s+\d{3}\b",
            r"(?is)<!doctype\s+html|<html[\s>]",
        )
    )


def _redact(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"(?im)^\s*set-cookie\s*:.*$", "<redacted>", text)
    text = re.sub(r"(?im)^\s*cookie\s*:.*$", "<redacted>", text)
    text = re.sub(r"(?im)^\s*authorization\s*:.*$", "<redacted>", text)
    text = re.sub(
        r"(?i)\bauthorization\s*:\s*bearer\s+[^\s,;&]+",
        "authorization=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(token|api[_-]?key|password|secret|session|cookie|authorization)\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)([\"'](?:token|api[_-]?key|password|secret|session|cookie|authorization)[\"']\s*:\s*)([\"'][^\"']*[\"']|[^,\n\r}\]]+)",
        r'\1"<redacted>"',
        text,
    )
    return text
