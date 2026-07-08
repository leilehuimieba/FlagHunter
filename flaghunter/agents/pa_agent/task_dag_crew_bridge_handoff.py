"""Dry handoff envelope for Task DAG crew bridge preview records."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .task_dag_crew_bridge_readback import (
    TaskDAGCrewBridgePreviewRecord,
    build_task_dag_crew_bridge_preview,
)
from .task_dag_shared import (
    _counts,
    _is_sensitive_key,
    _redact_text,
)


TASK_DAG_CREW_BRIDGE_HANDOFF_SCHEMA_VERSION = "p4d.task_dag_crew_bridge_handoff.v1"
_DECISIONS = {
    "ready_for_review",
    "waiting_for_receipt",
    "needs_manual_review",
    "blocked_or_failed",
    "completed_no_handoff",
}
_DECISION_ORDER = {
    "blocked_or_failed": 0,
    "needs_manual_review": 1,
    "ready_for_review": 2,
    "waiting_for_receipt": 3,
    "completed_no_handoff": 4,
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
class TaskDAGCrewBridgeHandoffItem:
    schema_version: str
    task_id: str
    request_id: str
    receipt_id: str
    worker_type: str
    status: str
    handoff_decision: str
    goal_snippet: str = ""
    summary_snippet: str = ""
    has_receipt: bool = False
    evidence_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_CREW_BRIDGE_HANDOFF_SCHEMA_VERSION
        self.task_id = _preview(self.task_id, limit=160)
        self.request_id = _preview(self.request_id, limit=160)
        self.receipt_id = _preview(self.receipt_id, limit=160)
        self.worker_type = _preview(self.worker_type or "default", limit=80) or "default"
        self.status = _preview(self.status or "pending", limit=80) or "pending"
        self.handoff_decision = _decision(self.handoff_decision)
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
            "goalSnippet": self.goal_snippet,
            "summarySnippet": self.summary_snippet,
            "hasReceipt": self.has_receipt,
            "evidenceRefs": list(self.evidence_refs),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class TaskDAGCrewBridgeHandoffEnvelope:
    schema_version: str
    envelope_id: str
    items: list[TaskDAGCrewBridgeHandoffItem] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_CREW_BRIDGE_HANDOFF_SCHEMA_VERSION
        self.envelope_id = _preview(self.envelope_id, limit=160)
        self.items = [_coerce_item(item) for item in list(self.items or [])]
        self.summary = _safe_mapping(self.summary)
        self.filters = _safe_mapping(self.filters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "envelopeId": self.envelope_id,
            "items": [item.to_dict() for item in self.items],
            "summary": dict(self.summary),
            "filters": dict(self.filters),
        }


def build_task_dag_crew_bridge_handoff_envelope(
    *,
    preview: Any = None,
    requests: Any = None,
    receipts: Any = None,
    max_items: int = 20,
    worker_type: str = "",
    status: str = "",
    task_id: str = "",
    handoff_decision: str = "",
    has_receipt: bool | None = None,
) -> TaskDAGCrewBridgeHandoffEnvelope:
    preview_payload = _preview_payload(preview, requests=requests, receipts=receipts)
    records = [_record_from_payload(item) for item in list(preview_payload.get("records") or [])]
    items = [_item_from_record(record) for record in records]
    filtered = _filter_items(
        items,
        worker_type=worker_type,
        status=status,
        task_id=task_id,
        handoff_decision=handoff_decision,
        has_receipt=has_receipt,
    )
    ordered = sorted(
        filtered,
        key=lambda item: (
            _DECISION_ORDER.get(item.handoff_decision, 99),
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
        "hasReceipt": has_receipt,
    }
    summary = {
        "recordCount": len(filtered),
        "exportedCount": len(selected),
        "readyCount": _decision_count(filtered, "ready_for_review"),
        "waitingCount": _decision_count(filtered, "waiting_for_receipt"),
        "manualReviewCount": _decision_count(filtered, "needs_manual_review"),
        "blockedOrFailedCount": _decision_count(filtered, "blocked_or_failed"),
        "completedCount": _decision_count(filtered, "completed_no_handoff"),
        "truncatedCount": max(0, len(filtered) - len(selected)),
        "statusCounts": _counts(item.status for item in filtered),
        "workerTypeCounts": _counts(item.worker_type for item in filtered),
        "filters": dict(filters),
    }
    envelope = TaskDAGCrewBridgeHandoffEnvelope(
        schema_version=TASK_DAG_CREW_BRIDGE_HANDOFF_SCHEMA_VERSION,
        envelope_id="",
        items=selected,
        summary=summary,
        filters=filters,
    )
    envelope.envelope_id = _envelope_id(envelope.items, summary)
    return envelope


def load_task_dag_crew_bridge_handoff_items(
    *,
    preview: Any = None,
    requests: Any = None,
    receipts: Any = None,
    max_items: int = 20,
    worker_type: str = "",
    status: str = "",
    task_id: str = "",
    handoff_decision: str = "",
    has_receipt: bool | None = None,
) -> list[TaskDAGCrewBridgeHandoffItem]:
    return build_task_dag_crew_bridge_handoff_envelope(
        preview=preview,
        requests=requests,
        receipts=receipts,
        max_items=max_items,
        worker_type=worker_type,
        status=status,
        task_id=task_id,
        handoff_decision=handoff_decision,
        has_receipt=has_receipt,
    ).items


def _preview_payload(preview: Any, *, requests: Any, receipts: Any) -> dict[str, Any]:
    if isinstance(preview, dict):
        return dict(preview)
    if isinstance(preview, (list, tuple)):
        return {"records": list(preview)}
    if isinstance(preview, TaskDAGCrewBridgePreviewRecord):
        return {"records": [preview.to_dict()]}
    return build_task_dag_crew_bridge_preview(requests=requests, receipts=receipts)


def _record_from_payload(value: Any) -> TaskDAGCrewBridgePreviewRecord:
    if isinstance(value, TaskDAGCrewBridgePreviewRecord):
        return value
    payload = dict(value or {}) if isinstance(value, dict) else {}
    return TaskDAGCrewBridgePreviewRecord(
        schema_version=str(payload.get("schemaVersion") or ""),
        task_id=str(payload.get("taskId") or ""),
        request_id=str(payload.get("requestId") or ""),
        receipt_id=str(payload.get("receiptId") or ""),
        task_brief_id=str(payload.get("taskBriefId") or ""),
        solve_node_id=str(payload.get("solveNodeId") or ""),
        worker_type=str(payload.get("workerType") or ""),
        status=str(payload.get("status") or ""),
        goal_snippet=str(payload.get("goalSnippet") or ""),
        summary_snippet=str(payload.get("summarySnippet") or ""),
        has_receipt=bool(payload.get("hasReceipt")),
        evidence_refs=list(payload.get("evidenceRefs") or []),
        warnings=list(payload.get("warnings") or []),
        metadata=dict(payload.get("metadata") or {}),
    )


def _item_from_record(record: TaskDAGCrewBridgePreviewRecord) -> TaskDAGCrewBridgeHandoffItem:
    return TaskDAGCrewBridgeHandoffItem(
        schema_version=TASK_DAG_CREW_BRIDGE_HANDOFF_SCHEMA_VERSION,
        task_id=record.task_id,
        request_id=record.request_id,
        receipt_id=record.receipt_id,
        worker_type=record.worker_type,
        status=record.status,
        handoff_decision=_decision_for_record(record),
        goal_snippet=record.goal_snippet,
        summary_snippet=record.summary_snippet,
        has_receipt=record.has_receipt,
        evidence_refs=list(record.evidence_refs),
        warnings=list(record.warnings),
        metadata=dict(record.metadata),
    )


def _decision_for_record(record: TaskDAGCrewBridgePreviewRecord) -> str:
    status = str(record.status or "").strip()
    warnings = set(record.warnings or [])
    if "missing_bridge_request" in warnings:
        return "needs_manual_review"
    if not record.has_receipt or status == "missing_receipt":
        return "waiting_for_receipt"
    if status in {"failed", "blocked", "error"}:
        return "blocked_or_failed"
    if status in {"succeeded", "completed"}:
        if record.summary_snippet or record.evidence_refs:
            return "ready_for_review"
        return "completed_no_handoff"
    return "ready_for_review"


def _filter_items(
    items: list[TaskDAGCrewBridgeHandoffItem],
    *,
    worker_type: str,
    status: str,
    task_id: str,
    handoff_decision: str,
    has_receipt: bool | None,
) -> list[TaskDAGCrewBridgeHandoffItem]:
    worker_filter = str(worker_type or "").strip()
    status_filter = str(status or "").strip()
    task_filter = str(task_id or "").strip()
    decision_filter = str(handoff_decision or "").strip()
    result: list[TaskDAGCrewBridgeHandoffItem] = []
    for item in items:
        if worker_filter and item.worker_type != worker_filter:
            continue
        if status_filter and item.status != status_filter:
            continue
        if task_filter and task_filter not in item.task_id:
            continue
        if decision_filter and item.handoff_decision != decision_filter:
            continue
        if has_receipt is not None and item.has_receipt is not bool(has_receipt):
            continue
        result.append(item)
    return result


def _coerce_item(value: Any) -> TaskDAGCrewBridgeHandoffItem:
    if isinstance(value, TaskDAGCrewBridgeHandoffItem):
        return TaskDAGCrewBridgeHandoffItem(
            schema_version=value.schema_version,
            task_id=value.task_id,
            request_id=value.request_id,
            receipt_id=value.receipt_id,
            worker_type=value.worker_type,
            status=value.status,
            handoff_decision=value.handoff_decision,
            goal_snippet=value.goal_snippet,
            summary_snippet=value.summary_snippet,
            has_receipt=value.has_receipt,
            evidence_refs=list(value.evidence_refs),
            warnings=list(value.warnings),
            metadata=dict(value.metadata),
        )
    payload = dict(value or {}) if isinstance(value, dict) else {}
    return TaskDAGCrewBridgeHandoffItem(
        schema_version=str(payload.get("schemaVersion") or ""),
        task_id=str(payload.get("taskId") or ""),
        request_id=str(payload.get("requestId") or ""),
        receipt_id=str(payload.get("receiptId") or ""),
        worker_type=str(payload.get("workerType") or ""),
        status=str(payload.get("status") or ""),
        handoff_decision=str(payload.get("handoffDecision") or ""),
        goal_snippet=str(payload.get("goalSnippet") or ""),
        summary_snippet=str(payload.get("summarySnippet") or ""),
        has_receipt=bool(payload.get("hasReceipt")),
        evidence_refs=list(payload.get("evidenceRefs") or []),
        warnings=list(payload.get("warnings") or []),
        metadata=dict(payload.get("metadata") or {}),
    )


def _decision(value: Any) -> str:
    normalized = str(value or "ready_for_review").strip() or "ready_for_review"
    if normalized not in _DECISIONS:
        return "needs_manual_review"
    return normalized


def _decision_count(items: list[TaskDAGCrewBridgeHandoffItem], decision: str) -> int:
    return sum(1 for item in items if item.handoff_decision == decision)


def _envelope_id(items: list[TaskDAGCrewBridgeHandoffItem], summary: dict[str, Any]) -> str:
    seed = "|".join(
        [
            str(summary.get("recordCount", 0)),
            str(summary.get("exportedCount", 0)),
            "|".join(
                ":".join(
                    [
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
    return f"task_dag_crew_handoff_{digest}"


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

