"""Prompt-safe compact evidence context for P4 reasoning."""

from __future__ import annotations

import re
from typing import Any

from .audit_views import build_audit_evidence_export
from .ctf_state import CTFState
from .p3_solve_readback import build_p3_solve_readback


SCHEMA_VERSION = "p4.evidence_reasoning_context.v1"


def build_evidence_reasoning_context(
    state: CTFState | None,
    *,
    limit: int = 5,
    preview_limit: int = 160,
) -> dict[str, Any]:
    """Build a bounded, read-only evidence context for reasoning prompts."""
    normalized_limit = max(0, int(limit))
    normalized_preview = max(1, int(preview_limit))
    audit = build_audit_evidence_export(
        state,
        claim_limit=normalized_limit,
        trace_limit=normalized_limit,
        verification_record_limit=normalized_limit,
        preview_limit=normalized_preview,
    )
    p3 = build_p3_solve_readback(
        state,
        node_limit=normalized_limit,
        edge_limit=normalized_limit,
        task_brief_limit=normalized_limit,
        node_receipt_limit=normalized_limit,
        preview_limit=normalized_preview,
    )
    audit_summary = dict(audit.get("summary") or {})
    p3_summary = dict(p3.get("summary") or {})
    trace_kinds = {
        str(item.get("kind") or "").strip()
        for item in list(audit.get("executionTraces") or [])
    }

    claim_refs = [
        _claim_ref(item)
        for item in list(audit.get("claims") or [])[:normalized_limit]
    ]
    verification_refs = [
        _verification_ref(item)
        for item in list(audit.get("verificationRecords") or [])[:normalized_limit]
    ]
    trace_signals = [
        _trace_signal(item)
        for item in list(audit.get("executionTraces") or [])[:normalized_limit]
    ]
    crew_summary = dict((p3.get("crewTrace") or {}).get("summary") or {})

    summary = {
        "claimCount": int(audit_summary.get("claimCount", 0) or 0),
        "verifiedClaimCount": int(audit_summary.get("verifiedClaimCount", 0) or 0),
        "candidateClaimCount": int(audit_summary.get("candidateClaimCount", 0) or 0),
        "verificationRecordCount": int(
            audit_summary.get("verificationRecordCount", 0) or 0
        ),
        "traceSignalCount": int(audit_summary.get("executionTraceCount", 0) or 0),
        "hasVerifiedClaim": int(audit_summary.get("verifiedClaimCount", 0) or 0) > 0,
        "hasControlReceipt": "control_receipt" in trace_kinds,
        "hasToolReceipt": "tool_receipt" in trace_kinds,
        "hasVerificationReceipt": "verification_receipt" in trace_kinds,
        "p3NodeCount": int(p3_summary.get("nodeCount", 0) or 0),
        "p3ReceiptCount": int(p3_summary.get("solveNodeReceiptCount", 0) or 0),
        "crewWorkerCount": int(p3_summary.get("crewWorkerCount", 0) or 0),
    }
    summary["text"] = _summary_text(summary, p3_summary)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "summary": summary,
        "claimRefs": claim_refs,
        "verificationRefs": verification_refs,
        "traceSignals": trace_signals,
        "p3Summary": _p3_summary_ref(p3_summary),
        "crewSummary": _crew_summary_ref(crew_summary),
    }


def _claim_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "claimId": str(item.get("claimId") or ""),
        "kind": str(item.get("kind") or ""),
        "level": str(item.get("level") or ""),
        "status": str(item.get("status") or ""),
        "contentPreview": _prompt_safe_preview(item.get("contentPreview")),
        "primaryTraceId": str(item.get("primaryTraceId") or ""),
        "sourceTraceId": str(item.get("sourceTraceId") or ""),
        "sourceReceiptId": str(item.get("sourceReceiptId") or ""),
        "latestVerificationDecision": str(
            item.get("latestVerificationDecision") or ""
        ),
    }


def _verification_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "recordId": str(item.get("recordId") or ""),
        "claimId": str(item.get("claimId") or ""),
        "decision": str(item.get("decision") or ""),
        "method": str(item.get("method") or ""),
        "passed": bool(item.get("passed")),
        "sufficientForUpgrade": bool(item.get("sufficientForUpgrade")),
        "traceId": str(item.get("traceId") or ""),
        "evidenceTraceIds": [
            str(trace_id)
            for trace_id in list(item.get("evidenceTraceIds") or [])
            if str(trace_id).strip()
        ],
        "rationalePreview": _prompt_safe_preview(item.get("rationalePreview")),
        "evidenceSummaryPreview": _prompt_safe_preview(
            item.get("evidenceSummaryPreview")
        ),
    }


def _trace_signal(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "traceId": str(item.get("traceId") or ""),
        "receiptId": str(item.get("receiptId") or ""),
        "kind": str(item.get("kind") or ""),
        "producer": str(item.get("producer") or ""),
        "success": bool(item.get("success")),
        "outputPreview": _prompt_safe_preview(item.get("outputPreview")),
    }


def _p3_summary_ref(summary: dict[str, Any]) -> dict[str, Any]:
    if not summary:
        return {}
    if not any(
        [
            int(summary.get("nodeCount", 0) or 0),
            int(summary.get("taskBriefCount", 0) or 0),
            int(summary.get("solveNodeReceiptCount", 0) or 0),
            int(summary.get("crewWorkerCount", 0) or 0),
            dict(summary.get("receiptStatusCounts") or {}),
            dict(summary.get("nodeStatusCounts") or {}),
            dict(summary.get("crewWorkerTypeCounts") or {}),
        ]
    ):
        return {}
    return {
        "nodeCount": int(summary.get("nodeCount", 0) or 0),
        "taskBriefCount": int(summary.get("taskBriefCount", 0) or 0),
        "solveNodeReceiptCount": int(summary.get("solveNodeReceiptCount", 0) or 0),
        "receiptStatusCounts": dict(summary.get("receiptStatusCounts") or {}),
        "nodeStatusCounts": dict(summary.get("nodeStatusCounts") or {}),
        "crewWorkerCount": int(summary.get("crewWorkerCount", 0) or 0),
        "crewReceiptCount": int(summary.get("crewReceiptCount", 0) or 0),
        "crewWorkerTypeCounts": dict(summary.get("crewWorkerTypeCounts") or {}),
    }


def _crew_summary_ref(summary: dict[str, Any]) -> dict[str, Any]:
    if not summary:
        return {}
    if not any(
        [
            int(summary.get("workerCount", 0) or 0),
            int(summary.get("receiptCount", 0) or 0),
            dict(summary.get("workerTypeCounts") or {}),
            dict(summary.get("receiptStatusCounts") or {}),
        ]
    ):
        return {}
    return {
        "workerCount": int(summary.get("workerCount", 0) or 0),
        "receiptCount": int(summary.get("receiptCount", 0) or 0),
        "workerTypeCounts": dict(summary.get("workerTypeCounts") or {}),
        "receiptStatusCounts": dict(summary.get("receiptStatusCounts") or {}),
    }


def _summary_text(summary: dict[str, Any], p3_summary: dict[str, Any]) -> str:
    parts: list[str] = []
    claim_count = int(summary.get("claimCount", 0) or 0)
    record_count = int(summary.get("verificationRecordCount", 0) or 0)
    trace_count = int(summary.get("traceSignalCount", 0) or 0)
    p3_receipt_count = int(summary.get("p3ReceiptCount", 0) or 0)
    crew_worker_count = int(summary.get("crewWorkerCount", 0) or 0)
    if claim_count:
        parts.append(f"evidence_claims={claim_count}")
        parts.append(f"evidence_verified={int(summary.get('verifiedClaimCount', 0) or 0)}")
        parts.append(f"evidence_candidates={int(summary.get('candidateClaimCount', 0) or 0)}")
    if record_count:
        parts.append(f"verification_records={record_count}")
    if trace_count:
        parts.append(f"evidence_traces={trace_count}")
    if p3_receipt_count:
        parts.append(f"p3_receipts={p3_receipt_count}")
        receipt_statuses = dict(p3_summary.get("receiptStatusCounts") or {})
        if receipt_statuses:
            parts.append(
                "p3_receipt_statuses="
                + ",".join(
                    f"{key}:{receipt_statuses[key]}"
                    for key in sorted(receipt_statuses)
                    if str(key).strip()
                )
            )
    if crew_worker_count:
        parts.append(f"crew_workers={crew_worker_count}")
    return " ".join(parts)


def _prompt_safe_preview(value: Any, *, limit: int = 160) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = _redact_sensitive_text(text)
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


def _redact_sensitive_text(value: Any) -> str:
    text = str(value or "")
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
