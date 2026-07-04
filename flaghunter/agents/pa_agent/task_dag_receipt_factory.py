"""Standalone Task DAG receipt factory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import re
from typing import Any

from .solve_node import SolveNodeReceipt


RECEIPT_FACTORY_VERSION = "p4.task_dag_receipt_factory.v1"
_VALID_STATUSES = {"completed", "failed", "partial", "blocked", "skipped"}
_STATUS_ALIASES = {
    "success": "completed",
    "error": "failed",
    "insufficient": "partial",
    "no_evidence": "partial",
}
_METADATA_ALLOWLIST = {"outcome_kind"}


class TaskDAGReceiptFactoryError(ValueError):
    pass


@dataclass
class TaskDAGReceiptOutcome:
    task_id: str
    solve_node_id: str = ""
    task_brief_id: str = ""
    run_id: str = ""
    worker_id: str = "local_task_dag"
    worker_type: str = "manual_local_task_dag"
    status: str = "partial"
    output_summary: str = ""
    error_class: str = ""
    error_summary: str = ""
    started_at: float | None = None
    finished_at: float | None = None
    duration_ms: int | None = None
    trace_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.task_id = str(self.task_id or "").strip()
        self.solve_node_id = str(self.solve_node_id or "").strip()
        self.task_brief_id = str(self.task_brief_id or "").strip()
        self.run_id = str(self.run_id or "").strip()
        self.worker_id = str(self.worker_id or "local_task_dag").strip() or "local_task_dag"
        self.worker_type = (
            str(self.worker_type or "manual_local_task_dag").strip()
            or "manual_local_task_dag"
        )
        self.status = str(self.status or "").strip().lower()
        self.output_summary = str(self.output_summary or "")
        self.error_class = str(self.error_class or "").strip()
        self.error_summary = str(self.error_summary or "")
        self.started_at = _optional_float(self.started_at)
        self.finished_at = _optional_float(self.finished_at)
        self.duration_ms = _optional_int(self.duration_ms)
        self.trace_ids = _coerce_str_list(self.trace_ids)
        self.claim_ids = _coerce_str_list(self.claim_ids)
        self.artifact_refs = _coerce_str_list(self.artifact_refs)
        self.warnings = _coerce_str_list(self.warnings)
        self.metadata = dict(self.metadata or {}) if isinstance(self.metadata, dict) else {}


def task_dag_receipt_outcome_to_dict(
    outcome: TaskDAGReceiptOutcome | dict[str, Any],
) -> dict[str, Any]:
    normalized = task_dag_receipt_outcome_from_dict(outcome)
    return asdict(normalized)


def task_dag_receipt_outcome_from_dict(
    data: TaskDAGReceiptOutcome | dict[str, Any] | None,
) -> TaskDAGReceiptOutcome:
    if isinstance(data, TaskDAGReceiptOutcome):
        return TaskDAGReceiptOutcome(**asdict(data))
    payload = dict(data or {})
    allowed = {item.name for item in fields(TaskDAGReceiptOutcome)}
    return TaskDAGReceiptOutcome(
        **{key: value for key, value in payload.items() if key in allowed}
    )


def build_local_task_dag_receipt(
    outcome: TaskDAGReceiptOutcome | dict[str, Any],
) -> SolveNodeReceipt:
    if outcome is None or (isinstance(outcome, dict) and not outcome):
        raise TaskDAGReceiptFactoryError("receipt outcome is required")
    try:
        normalized = task_dag_receipt_outcome_from_dict(outcome)
    except TypeError as exc:
        raise TaskDAGReceiptFactoryError("invalid receipt outcome") from exc
    if not normalized.task_id:
        raise TaskDAGReceiptFactoryError("task_id is required")
    status = _canonical_status(normalized.status)
    warnings = [_preview(item, limit=160) for item in normalized.warnings[:10]]
    return SolveNodeReceipt(
        node_id=_preview(normalized.solve_node_id, limit=160),
        run_id=_preview(normalized.run_id, limit=160),
        worker_id=_preview(normalized.worker_id, limit=160) or "local_task_dag",
        worker_type=_preview(normalized.worker_type, limit=160)
        or "manual_local_task_dag",
        status=status,
        started_at=normalized.started_at,
        finished_at=normalized.finished_at,
        duration_ms=normalized.duration_ms,
        input_brief_id=_preview(normalized.task_brief_id, limit=160),
        output_summary=_preview(normalized.output_summary, limit=160),
        claim_ids=_safe_refs(normalized.claim_ids),
        trace_ids=_safe_refs(normalized.trace_ids),
        artifact_refs=_safe_refs(normalized.artifact_refs),
        error_class=_preview(normalized.error_class, limit=80),
        error_summary=_preview(normalized.error_summary, limit=160),
        metadata=_receipt_metadata(normalized, warnings),
    )


def _receipt_metadata(
    outcome: TaskDAGReceiptOutcome,
    warnings: list[str],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "adapter_version": RECEIPT_FACTORY_VERSION,
        "source_channel": "task_dag_receipt_factory",
        "task_dag_task_id": _preview(outcome.task_id, limit=160),
        "warning_count": len(warnings),
    }
    for key in sorted(_METADATA_ALLOWLIST):
        if key not in outcome.metadata:
            continue
        metadata[_preview(key, limit=80)] = _preview(outcome.metadata[key], limit=160)
    return metadata


def _canonical_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    normalized = _STATUS_ALIASES.get(normalized, normalized)
    if normalized not in _VALID_STATUSES:
        raise TaskDAGReceiptFactoryError(f"invalid status: {value}")
    return normalized


def _safe_refs(values: Any) -> list[str]:
    return [_preview(item, limit=160) for item in _dedupe(_coerce_str_list(values))]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        if item and item not in result:
            result.append(item)
    return result


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


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _preview(value: Any, *, limit: int) -> str:
    text = _redact_text(value)
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


def _redact_text(value: Any) -> str:
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
        r"(?i)\bauthorization\s*=\s*bearer\s+[^\s,;&]+",
        "authorization=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(token|api[_-]?key|password|secret|session|sessionid|cookie|authorization)\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)([\"'])(token|api[_-]?key|password|secret|session|sessionid|cookie|authorization)[\"']\s*:\s*([\"'])(.*?)\3",
        r'\1\2\1: \3<redacted>\3',
        text,
    )
    return text
