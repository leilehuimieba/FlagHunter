"""Dry executor-like result adapter for Task DAG outcomes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .task_dag_outcome_source import (
    TaskDAGOutcomeSourceError,
    build_manual_task_dag_outcome,
)
from .task_dag_receipt_factory import TaskDAGReceiptOutcome


_SUCCESS_STATUSES = {"completed", "success", "succeeded", "ok"}
_FAILED_STATUSES = {"failed", "failure", "error"}
_PARTIAL_STATUSES = {"partial", "insufficient", "no_evidence", "timeout", "timed_out", "unknown"}
_DIRECT_STATUSES = {"blocked", "skipped"}
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
    "tool_results",
    "request",
    "response",
    "http_request",
    "http_response",
    "browser_log",
    "terminal_output",
    "full_output",
}
_PROOF_FIELD_KEYS = {
    "verification" + "_decision",
    "verified" + "_flags",
    "verifier" + "Proof",
    "proof" + "_level",
    "verification" + "RecordId",
    "verified" + "Flag",
    "flag" + "_level",
    "flag" + "_verified",
    "verifier" + "_decision",
}


class TaskDAGDryResultAdapterError(ValueError):
    pass


@dataclass
class TaskDAGDryExecutorResult:
    task_id: str
    solve_node_id: str = ""
    task_brief_id: str = ""
    run_id: str = ""
    status: str = "partial"
    compact_output: str = ""
    compact_error: str = ""
    error_class: str = ""
    exit_code: int | None = None
    duration_ms: int | None = None
    trace_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def build_task_dag_outcome_from_dry_result(
    result: TaskDAGDryExecutorResult | dict[str, Any],
) -> TaskDAGReceiptOutcome:
    payload = _result_payload(result)
    _reject_forbidden_fields(payload)

    status_value, status_was_explicit = _status_value(payload)
    status = _canonical_status(status_value)
    warnings = _coerce_str_list(payload.get("warnings"))
    exit_code = _optional_int(payload.get("exit_code"))
    if not status_was_explicit and exit_code == 0:
        warnings.append("exit_code_without_status")

    metadata = _safe_metadata(payload.get("metadata"))
    try:
        outcome = build_manual_task_dag_outcome(
            task_id=payload.get("task_id", ""),
            solve_node_id=payload.get("solve_node_id", ""),
            task_brief_id=payload.get("task_brief_id", ""),
            run_id=payload.get("run_id", ""),
            status=status,
            output_summary=_first_present(payload, ("compact_output", "output_summary")),
            error_class=payload.get("error_class", ""),
            error_summary=_first_present(payload, ("compact_error", "error_summary")),
            trace_ids=payload.get("trace_ids"),
            claim_ids=payload.get("claim_ids"),
            artifact_refs=payload.get("artifact_refs"),
            warnings=warnings,
            metadata=metadata,
        )
    except TaskDAGOutcomeSourceError as exc:
        raise TaskDAGDryResultAdapterError(str(exc)) from exc
    if exit_code is not None:
        outcome.metadata["exit_code"] = exit_code
    duration_ms = _optional_non_negative_int(payload.get("duration_ms"))
    if duration_ms is not None:
        outcome.duration_ms = duration_ms
    return outcome


def _result_payload(result: TaskDAGDryExecutorResult | dict[str, Any]) -> dict[str, Any]:
    if result is None or (isinstance(result, dict) and not result):
        raise TaskDAGDryResultAdapterError("dry result is required")
    if isinstance(result, TaskDAGDryExecutorResult):
        return asdict(result)
    if not isinstance(result, dict):
        raise TaskDAGDryResultAdapterError("dry result must be a dict")
    return dict(result)


def _reject_forbidden_fields(payload: dict[str, Any]) -> None:
    for key in payload:
        if key in _RAW_FIELD_KEYS:
            raise TaskDAGDryResultAdapterError(f"raw field is not accepted: {key}")
        if key in _PROOF_FIELD_KEYS:
            raise TaskDAGDryResultAdapterError(f"proof-like field is not accepted: {key}")


def _status_value(payload: dict[str, Any]) -> tuple[str, bool]:
    for key in ("status", "result_status", "dry_status"):
        if key in payload and str(payload.get(key) or "").strip():
            return str(payload.get(key) or ""), True
    return "partial", False


def _canonical_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _SUCCESS_STATUSES:
        return "completed"
    if normalized in _FAILED_STATUSES:
        return "failed"
    if normalized in _PARTIAL_STATUSES:
        return "partial"
    if normalized in _DIRECT_STATUSES:
        return normalized
    raise TaskDAGDryResultAdapterError(f"invalid status: {value}")


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return ""


def _safe_metadata(value: Any) -> dict[str, Any]:
    metadata = value if isinstance(value, dict) else {}
    return {
        "outcome_kind": metadata.get("outcome_kind", "dry_executor_like"),
        "source_kind": metadata.get("source_kind", "dry_result_adapter"),
    }


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        return []
    return [str(item).strip() for item in items if str(item or "").strip()]


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_non_negative_int(value: Any) -> int | None:
    result = _optional_int(value)
    if result is None or result < 0:
        return None
    return result
