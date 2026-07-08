"""Manual Task DAG outcome source for bounded test-harness input."""

from __future__ import annotations

import re
from typing import Any

from .task_dag_receipt_factory import TaskDAGReceiptOutcome
from .task_dag_shared import (
    _coerce_str_list,
    _dedupe,
    _redact_text,
)


_VALID_STATUSES = {"completed", "failed", "partial", "blocked", "skipped"}
_STATUS_ALIASES = {
    "success": "completed",
    "error": "failed",
    "insufficient": "partial",
    "no_evidence": "partial",
}
_ALLOWED_METADATA_KEYS = {"outcome_kind", "source_kind"}
_RAW_FIELD_KEYS = {
    "stdout",
    "stderr",
    "body",
    "http_body",
    "raw_body",
    "raw_output",
    "prompt",
    "completion",
    "tool_result",
    "request",
    "response",
}
_PROOF_FIELD_KEYS = {
    "verification" + "_decision",
    "verified" + "_flags",
    "verifier" + "Proof",
    "proof" + "_level",
    "verification" + "RecordId",
    "verified" + "Flag",
}


class TaskDAGOutcomeSourceError(ValueError):
    pass


def build_manual_task_dag_outcome(
    *,
    task_id: str,
    solve_node_id: str = "",
    task_brief_id: str = "",
    run_id: str = "",
    status: str = "partial",
    output_summary: str = "",
    error_class: str = "",
    error_summary: str = "",
    trace_ids: list[str] | None = None,
    claim_ids: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    warnings: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> TaskDAGReceiptOutcome:
    normalized_task_id = _preview(task_id, limit=160)
    if not normalized_task_id:
        raise TaskDAGOutcomeSourceError("task_id is required")

    return TaskDAGReceiptOutcome(
        task_id=normalized_task_id,
        solve_node_id=_preview(solve_node_id, limit=160),
        task_brief_id=_preview(task_brief_id, limit=160),
        run_id=_preview(run_id, limit=160),
        status=_canonical_status(status),
        output_summary=_preview(output_summary, limit=160),
        error_class=_preview(error_class, limit=80),
        error_summary=_preview(error_summary, limit=160),
        trace_ids=_safe_refs(trace_ids),
        claim_ids=_safe_refs(claim_ids),
        artifact_refs=_safe_refs(artifact_refs),
        warnings=[_preview(item, limit=160) for item in _coerce_str_list(warnings)[:10]],
        metadata=_safe_metadata(metadata),
    )


def manual_task_dag_outcome_from_dict(
    data: dict[str, Any] | None,
) -> TaskDAGReceiptOutcome:
    if not data:
        raise TaskDAGOutcomeSourceError("outcome data is required")
    if not isinstance(data, dict):
        raise TaskDAGOutcomeSourceError("outcome data must be a dict")
    _reject_forbidden_fields(data)
    return build_manual_task_dag_outcome(
        task_id=data.get("task_id", ""),
        solve_node_id=data.get("solve_node_id", ""),
        task_brief_id=data.get("task_brief_id", ""),
        run_id=data.get("run_id", ""),
        status=data.get("status", "partial"),
        output_summary=data.get("output_summary", ""),
        error_class=data.get("error_class", ""),
        error_summary=data.get("error_summary", ""),
        trace_ids=data.get("trace_ids"),
        claim_ids=data.get("claim_ids"),
        artifact_refs=data.get("artifact_refs"),
        warnings=data.get("warnings"),
        metadata=data.get("metadata"),
    )


def _reject_forbidden_fields(data: dict[str, Any]) -> None:
    for key in data:
        if key in _RAW_FIELD_KEYS:
            raise TaskDAGOutcomeSourceError(f"raw field is not accepted: {key}")
        if key in _PROOF_FIELD_KEYS:
            raise TaskDAGOutcomeSourceError(f"proof-like field is not accepted: {key}")


def _canonical_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    normalized = _STATUS_ALIASES.get(normalized, normalized)
    if normalized not in _VALID_STATUSES:
        raise TaskDAGOutcomeSourceError(f"invalid status: {value}")
    return normalized


def _safe_refs(values: Any) -> list[str]:
    return [_preview(item, limit=160) for item in _dedupe(_coerce_str_list(values))]


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {"source_channel": "manual_task_dag_outcome_source"}
    if not isinstance(metadata, dict):
        return safe
    for key in sorted(_ALLOWED_METADATA_KEYS):
        if key not in metadata:
            continue
        safe[_preview(key, limit=80)] = _preview(metadata[key], limit=160)
    return safe


def _preview(value: Any, *, limit: int) -> str:
    text = _redact_text(value).strip()
    if _looks_like_raw_body(text):
        return "<redacted raw body>"[: max(0, int(limit))]
    return text[: max(0, int(limit))]


def _looks_like_raw_body(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if len(stripped) > 240 and stripped[:1] in {"{", "["}:
        return True
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

