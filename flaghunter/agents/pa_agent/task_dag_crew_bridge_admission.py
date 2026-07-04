"""Dry admission package for Task DAG crew bridge handoff items."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .task_dag_crew_bridge_handoff import (
    TaskDAGCrewBridgeHandoffEnvelope,
    TaskDAGCrewBridgeHandoffItem,
    build_task_dag_crew_bridge_handoff_envelope,
)


TASK_DAG_CREW_BRIDGE_ADMISSION_SCHEMA_VERSION = "p4d.task_dag_crew_bridge_admission.v1"
_ADMISSION_STATES = {
    "admit_dry",
    "hold_for_receipt",
    "manual_review_required",
    "reject_failed",
    "complete_noop",
}
_ADMISSION_ORDER = {
    "reject_failed": 0,
    "manual_review_required": 1,
    "admit_dry": 2,
    "hold_for_receipt": 3,
    "complete_noop": 4,
}
_HANDOFF_TO_ADMISSION = {
    "ready_for_review": ("admit_dry", "ready_for_review"),
    "waiting_for_receipt": ("hold_for_receipt", "waiting_for_receipt"),
    "needs_manual_review": ("manual_review_required", "needs_manual_review"),
    "blocked_or_failed": ("reject_failed", "blocked_or_failed"),
    "completed_no_handoff": ("complete_noop", "completed_no_handoff"),
}
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
    "full_command",
    "raw_args",
    "command_line",
    "terminal_output",
}
_PROOF_LIKE_KEYS = {
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
_PROOF_LIKE_VALUE_FRAGMENTS = {
    'level="' + "verified" + '"',
    "level='" + "verified" + "'",
}


@dataclass
class TaskDAGCrewBridgeAdmissionItem:
    schema_version: str
    task_id: str
    request_id: str
    receipt_id: str
    worker_type: str
    status: str
    handoff_decision: str
    admission_state: str
    reason: str = ""
    goal_snippet: str = ""
    summary_snippet: str = ""
    has_receipt: bool = False
    evidence_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_CREW_BRIDGE_ADMISSION_SCHEMA_VERSION
        self.task_id = _preview(self.task_id, limit=160)
        self.request_id = _preview(self.request_id, limit=160)
        self.receipt_id = _preview(self.receipt_id, limit=160)
        self.worker_type = _preview(self.worker_type or "default", limit=80) or "default"
        self.status = _preview(self.status or "pending", limit=80) or "pending"
        self.handoff_decision = _preview(
            self.handoff_decision or "ready_for_review",
            limit=80,
        ) or "ready_for_review"
        self.admission_state = _admission_state(self.admission_state)
        self.reason = _preview(self.reason, limit=160)
        self.goal_snippet = _preview(self.goal_snippet, limit=160)
        self.summary_snippet = _preview(self.summary_snippet, limit=160)
        self.has_receipt = bool(self.has_receipt)
        self.evidence_refs = _safe_refs(self.evidence_refs, limit=20)
        self.warnings = _safe_refs(self.warnings, limit=10)
        self.metadata = _safe_metadata(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "taskId": self.task_id,
            "requestId": self.request_id,
            "receiptId": self.receipt_id,
            "workerType": self.worker_type,
            "status": self.status,
            "handoffDecision": self.handoff_decision,
            "admissionState": self.admission_state,
            "reason": self.reason,
            "goalSnippet": self.goal_snippet,
            "summarySnippet": self.summary_snippet,
            "hasReceipt": self.has_receipt,
            "evidenceRefs": list(self.evidence_refs),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class TaskDAGCrewBridgeAdmissionPackage:
    schema_version: str
    package_id: str
    items: list[TaskDAGCrewBridgeAdmissionItem] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_CREW_BRIDGE_ADMISSION_SCHEMA_VERSION
        self.package_id = _preview(self.package_id, limit=160)
        self.items = [_coerce_admission_item(item) for item in list(self.items or [])]
        self.summary = _safe_mapping(self.summary)
        self.filters = _safe_mapping(self.filters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "packageId": self.package_id,
            "items": [item.to_dict() for item in self.items],
            "summary": dict(self.summary),
            "filters": dict(self.filters),
        }


def build_task_dag_crew_bridge_admission_package(
    *,
    handoff: Any = None,
    preview: Any = None,
    requests: Any = None,
    receipts: Any = None,
    max_items: int = 20,
    worker_type: str = "",
    status: str = "",
    task_id: str = "",
    handoff_decision: str = "",
    admission_state: str = "",
    has_receipt: bool | None = None,
) -> TaskDAGCrewBridgeAdmissionPackage:
    handoff_payload = _handoff_payload(
        handoff,
        preview=preview,
        requests=requests,
        receipts=receipts,
    )
    items = [
        _admission_item_from_handoff_payload(item)
        for item in list(handoff_payload.get("items") or [])
    ]
    filtered = _filter_items(
        items,
        worker_type=worker_type,
        status=status,
        task_id=task_id,
        handoff_decision=handoff_decision,
        admission_state=admission_state,
        has_receipt=has_receipt,
    )
    ordered = sorted(
        filtered,
        key=lambda item: (
            _ADMISSION_ORDER.get(item.admission_state, 99),
            item.task_id,
            item.request_id,
            item.receipt_id,
            item.worker_type,
            item.status,
        ),
    )
    normalized_limit = max(0, int(max_items))
    selected = ordered[:normalized_limit] if normalized_limit else []
    filters = {
        "workerType": _preview(worker_type, limit=80),
        "status": _preview(status, limit=80),
        "taskId": _preview(task_id, limit=160),
        "handoffDecision": _preview(handoff_decision, limit=80),
        "admissionState": _preview(admission_state, limit=80),
        "hasReceipt": has_receipt,
    }
    summary = {
        "handoffItemCount": len(filtered),
        "exportedCount": len(selected),
        "admitDryCount": _state_count(filtered, "admit_dry"),
        "holdCount": _state_count(filtered, "hold_for_receipt"),
        "manualReviewCount": _state_count(filtered, "manual_review_required"),
        "rejectCount": _state_count(filtered, "reject_failed"),
        "completeNoopCount": _state_count(filtered, "complete_noop"),
        "truncatedCount": max(0, len(filtered) - len(selected)),
        "statusCounts": _counts(item.status for item in filtered),
        "workerTypeCounts": _counts(item.worker_type for item in filtered),
        "decisionCounts": _counts(item.admission_state for item in filtered),
        "filters": dict(filters),
    }
    package = TaskDAGCrewBridgeAdmissionPackage(
        schema_version=TASK_DAG_CREW_BRIDGE_ADMISSION_SCHEMA_VERSION,
        package_id="",
        items=selected,
        summary=summary,
        filters=filters,
    )
    package.package_id = _package_id(package.items, summary)
    return package


def load_task_dag_crew_bridge_admission_items(
    *,
    handoff: Any = None,
    preview: Any = None,
    requests: Any = None,
    receipts: Any = None,
    max_items: int = 20,
    worker_type: str = "",
    status: str = "",
    task_id: str = "",
    handoff_decision: str = "",
    admission_state: str = "",
    has_receipt: bool | None = None,
) -> list[TaskDAGCrewBridgeAdmissionItem]:
    return build_task_dag_crew_bridge_admission_package(
        handoff=handoff,
        preview=preview,
        requests=requests,
        receipts=receipts,
        max_items=max_items,
        worker_type=worker_type,
        status=status,
        task_id=task_id,
        handoff_decision=handoff_decision,
        admission_state=admission_state,
        has_receipt=has_receipt,
    ).items


def _handoff_payload(
    handoff: Any,
    *,
    preview: Any,
    requests: Any,
    receipts: Any,
) -> dict[str, Any]:
    if isinstance(handoff, dict):
        return dict(handoff)
    if isinstance(handoff, TaskDAGCrewBridgeHandoffEnvelope):
        return handoff.to_dict()
    if isinstance(handoff, TaskDAGCrewBridgeHandoffItem):
        return {"items": [handoff.to_dict()]}
    if isinstance(handoff, (list, tuple)):
        return {"items": list(handoff)}
    return build_task_dag_crew_bridge_handoff_envelope(
        preview=preview,
        requests=requests,
        receipts=receipts,
    ).to_dict()


def _admission_item_from_handoff_payload(value: Any) -> TaskDAGCrewBridgeAdmissionItem:
    payload = _handoff_item_payload(value)
    handoff_decision = str(payload.get("handoffDecision") or "ready_for_review").strip()
    admission_state, reason, extra_warnings = _admission_for_handoff(handoff_decision)
    warnings = [*(payload.get("warnings") or []), *extra_warnings]
    return TaskDAGCrewBridgeAdmissionItem(
        schema_version=TASK_DAG_CREW_BRIDGE_ADMISSION_SCHEMA_VERSION,
        task_id=str(payload.get("taskId") or ""),
        request_id=str(payload.get("requestId") or ""),
        receipt_id=str(payload.get("receiptId") or ""),
        worker_type=str(payload.get("workerType") or ""),
        status=str(payload.get("status") or ""),
        handoff_decision=handoff_decision,
        admission_state=admission_state,
        reason=reason,
        goal_snippet=str(payload.get("goalSnippet") or ""),
        summary_snippet=str(payload.get("summarySnippet") or ""),
        has_receipt=bool(payload.get("hasReceipt")),
        evidence_refs=list(payload.get("evidenceRefs") or []),
        warnings=warnings,
        metadata=dict(payload.get("metadata") or {}),
    )


def _handoff_item_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, TaskDAGCrewBridgeHandoffItem):
        return value.to_dict()
    return dict(value or {}) if isinstance(value, dict) else {}


def _admission_for_handoff(decision: str) -> tuple[str, str, list[str]]:
    normalized = str(decision or "").strip()
    if normalized in _HANDOFF_TO_ADMISSION:
        state, reason = _HANDOFF_TO_ADMISSION[normalized]
        return state, reason, []
    return "manual_review_required", "unknown_handoff_decision", ["unknown_handoff_decision"]


def _filter_items(
    items: list[TaskDAGCrewBridgeAdmissionItem],
    *,
    worker_type: str,
    status: str,
    task_id: str,
    handoff_decision: str,
    admission_state: str,
    has_receipt: bool | None,
) -> list[TaskDAGCrewBridgeAdmissionItem]:
    worker_filter = str(worker_type or "").strip()
    status_filter = str(status or "").strip()
    task_filter = str(task_id or "").strip()
    handoff_filter = str(handoff_decision or "").strip()
    admission_filter = str(admission_state or "").strip()
    result: list[TaskDAGCrewBridgeAdmissionItem] = []
    for item in items:
        if worker_filter and item.worker_type != worker_filter:
            continue
        if status_filter and item.status != status_filter:
            continue
        if task_filter and task_filter not in item.task_id:
            continue
        if handoff_filter and item.handoff_decision != handoff_filter:
            continue
        if admission_filter and item.admission_state != admission_filter:
            continue
        if has_receipt is not None and item.has_receipt is not bool(has_receipt):
            continue
        result.append(item)
    return result


def _coerce_admission_item(value: Any) -> TaskDAGCrewBridgeAdmissionItem:
    if isinstance(value, TaskDAGCrewBridgeAdmissionItem):
        return TaskDAGCrewBridgeAdmissionItem(
            schema_version=value.schema_version,
            task_id=value.task_id,
            request_id=value.request_id,
            receipt_id=value.receipt_id,
            worker_type=value.worker_type,
            status=value.status,
            handoff_decision=value.handoff_decision,
            admission_state=value.admission_state,
            reason=value.reason,
            goal_snippet=value.goal_snippet,
            summary_snippet=value.summary_snippet,
            has_receipt=value.has_receipt,
            evidence_refs=list(value.evidence_refs),
            warnings=list(value.warnings),
            metadata=dict(value.metadata),
        )
    payload = dict(value or {}) if isinstance(value, dict) else {}
    return TaskDAGCrewBridgeAdmissionItem(
        schema_version=str(payload.get("schemaVersion") or ""),
        task_id=str(payload.get("taskId") or ""),
        request_id=str(payload.get("requestId") or ""),
        receipt_id=str(payload.get("receiptId") or ""),
        worker_type=str(payload.get("workerType") or ""),
        status=str(payload.get("status") or ""),
        handoff_decision=str(payload.get("handoffDecision") or ""),
        admission_state=str(payload.get("admissionState") or ""),
        reason=str(payload.get("reason") or ""),
        goal_snippet=str(payload.get("goalSnippet") or ""),
        summary_snippet=str(payload.get("summarySnippet") or ""),
        has_receipt=bool(payload.get("hasReceipt")),
        evidence_refs=list(payload.get("evidenceRefs") or []),
        warnings=list(payload.get("warnings") or []),
        metadata=dict(payload.get("metadata") or {}),
    )


def _admission_state(value: Any) -> str:
    normalized = str(value or "manual_review_required").strip() or "manual_review_required"
    if normalized not in _ADMISSION_STATES:
        return "manual_review_required"
    return normalized


def _state_count(items: list[TaskDAGCrewBridgeAdmissionItem], state: str) -> int:
    return sum(1 for item in items if item.admission_state == state)


def _package_id(items: list[TaskDAGCrewBridgeAdmissionItem], summary: dict[str, Any]) -> str:
    seed = "|".join(
        [
            str(summary.get("handoffItemCount", 0)),
            str(summary.get("exportedCount", 0)),
            "|".join(
                ":".join(
                    [
                        item.admission_state,
                        item.handoff_decision,
                        item.task_id,
                        item.request_id,
                        item.receipt_id,
                        item.worker_type,
                        item.status,
                    ]
                )
                for item in items
            ),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"task_dag_crew_admission_{digest}"


def _safe_refs(values: Any, *, limit: int) -> list[str]:
    if values is None:
        items: list[Any] = []
    elif isinstance(values, str):
        items = [values]
    elif isinstance(values, (list, tuple, set)):
        items = list(values)
    else:
        items = []
    refs: list[str] = []
    for item in items:
        text = _preview(item, limit=160)
        if text and text not in refs:
            refs.append(text)
        if len(refs) >= max(0, int(limit)):
            break
    return refs


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for raw_key, raw_value in dict(metadata or {}).items():
        key_text = str(raw_key or "")
        key = _preview(key_text, limit=80)
        if (
            not key
            or key_text in _RAW_FIELD_KEYS
            or _is_proof_like_key(key_text)
            or _contains_proof_like_value(raw_value)
        ):
            continue
        if _is_sensitive_key(key):
            safe[key] = "<redacted>"
            continue
        if isinstance(raw_value, (bool, int, float)) or raw_value is None:
            safe[key] = raw_value
        elif isinstance(raw_value, dict):
            safe[key] = _safe_mapping(raw_value)
        else:
            safe[key] = _preview(raw_value, limit=160)
    return safe


def _safe_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for raw_key, raw_value in dict(mapping or {}).items():
        key = _preview(raw_key, limit=80)
        if not key or str(raw_key or "") in _RAW_FIELD_KEYS or _is_proof_like_key(raw_key):
            continue
        if _is_sensitive_key(key):
            safe[key] = "<redacted>"
            continue
        if isinstance(raw_value, dict):
            safe[key] = _safe_mapping(raw_value)
        elif isinstance(raw_value, (bool, int, float)) or raw_value is None:
            safe[key] = raw_value
        else:
            safe[key] = _preview(raw_value, limit=160)
    return safe


def _preview(value: Any, *, limit: int) -> str:
    if _contains_proof_like_value(value):
        return "<redacted proof-like value>"[: max(0, int(limit))]
    text = _redact_text(value)
    if _looks_like_raw_body(text):
        return "<redacted raw body>"[: max(0, int(limit))]
    return text[: max(0, int(limit))]


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


def _looks_like_raw_body(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if len(stripped) > 240 and stripped[:1] in {"{", "["}:
        return True
    return any(
        re.search(pattern, text)
        for pattern in (
            r"(?im)^\s*HTTP/\d(?:\.\d)?\s+\d{3}\b",
            r"(?is)<!doctype\s+html|<html[\s>]",
            r"(?im)^\s*PING\s+",
            r"(?im)^\s*\d+\s+bytes\s+from\s+",
            r"(?im)^\s*uid=\d+\(",
            r"(?im)^\s*gid=\d+\(",
        )
    )


def _is_sensitive_key(value: Any) -> bool:
    return bool(
        re.search(
            r"(?i)(token|api[_-]?key|password|secret|session|sessionid|cookie|authorization)",
            str(value or ""),
        )
    )


def _is_proof_like_key(value: Any) -> bool:
    text = str(value or "")
    if text in _PROOF_LIKE_KEYS:
        return True
    return _contains_proof_like_value(text)


def _contains_proof_like_value(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float)):
        return False
    if isinstance(value, dict):
        return any(
            _is_proof_like_key(key) or _contains_proof_like_value(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(_contains_proof_like_value(item) for item in value)
    text = str(value or "")
    return any(fragment in text for fragment in _PROOF_LIKE_VALUE_FRAGMENTS) or bool(
        re.search(r"(?i)\b(?:flag|ctf)\{[^}\s]{1,160}\}", text)
    )


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "").strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
