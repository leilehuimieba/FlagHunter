"""Read-side preview for Task DAG crew bridge request/receipt contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .task_dag_crew_bridge import (
    TaskDAGCrewBridgeReceipt,
    TaskDAGCrewBridgeRequest,
    build_task_dag_crew_bridge_request,
    normalize_task_dag_crew_bridge_receipt,
)
from .task_dag_shared import (
    _counts,
    _is_sensitive_key,
    _redact_text,
)


TASK_DAG_CREW_BRIDGE_PREVIEW_SCHEMA_VERSION = "p4d.task_dag_crew_bridge_preview.v1"
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
class TaskDAGCrewBridgePreviewRecord:
    schema_version: str
    task_id: str
    request_id: str
    receipt_id: str
    task_brief_id: str
    solve_node_id: str
    worker_type: str
    status: str
    goal_snippet: str = ""
    summary_snippet: str = ""
    has_receipt: bool = False
    evidence_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_CREW_BRIDGE_PREVIEW_SCHEMA_VERSION
        self.task_id = _preview(self.task_id, limit=160)
        self.request_id = _preview(self.request_id, limit=160)
        self.receipt_id = _preview(self.receipt_id, limit=160)
        self.task_brief_id = _preview(self.task_brief_id, limit=160)
        self.solve_node_id = _preview(self.solve_node_id, limit=160)
        self.worker_type = _preview(self.worker_type or "default", limit=80) or "default"
        self.status = _preview(self.status or "pending", limit=80) or "pending"
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
            "taskBriefId": self.task_brief_id,
            "solveNodeId": self.solve_node_id,
            "workerType": self.worker_type,
            "status": self.status,
            "goalSnippet": self.goal_snippet,
            "summarySnippet": self.summary_snippet,
            "hasReceipt": self.has_receipt,
            "evidenceRefs": list(self.evidence_refs),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def build_task_dag_crew_bridge_preview(
    *,
    requests: Any = None,
    receipts: Any = None,
    max_records: int = 20,
    worker_type: str = "",
    status: str = "",
    task_id: str = "",
    has_receipt: bool | None = None,
) -> dict[str, Any]:
    request_items = [_request_info(item) for item in _coerce_sequence(requests)]
    receipt_items = [_receipt_info(item) for item in _coerce_sequence(receipts)]
    records = _pair_records(request_items, receipt_items)
    filtered = _filter_records(
        records,
        worker_type=worker_type,
        status=status,
        task_id=task_id,
        has_receipt=has_receipt,
    )
    ordered = sorted(
        filtered,
        key=lambda item: (
            item.task_id,
            item.request_id,
            item.receipt_id,
            item.worker_type,
            item.status,
        ),
    )
    normalized_limit = max(0, int(max_records))
    selected = ordered[:normalized_limit] if normalized_limit else []
    return {
        "schemaVersion": TASK_DAG_CREW_BRIDGE_PREVIEW_SCHEMA_VERSION,
        "records": [record.to_dict() for record in selected],
        "summary": {
            "requestCount": len(request_items),
            "receiptCount": len(receipt_items),
            "matchedCount": len(filtered),
            "exportedCount": len(selected),
            "missingReceiptCount": sum(
                1 for record in filtered if record.status == "missing_receipt"
            ),
            "statusCounts": _counts(record.status for record in filtered),
            "workerTypeCounts": _counts(record.worker_type for record in filtered),
            "truncatedCount": max(0, len(filtered) - len(selected)),
            "filters": {
                "workerType": _preview(worker_type, limit=80),
                "status": _preview(status, limit=80),
                "taskId": _preview(task_id, limit=160),
                "hasReceipt": has_receipt,
            },
        },
    }


def load_task_dag_crew_bridge_preview_records(
    *,
    requests: Any = None,
    receipts: Any = None,
    max_records: int = 20,
    worker_type: str = "",
    status: str = "",
    task_id: str = "",
    has_receipt: bool | None = None,
) -> list[TaskDAGCrewBridgePreviewRecord]:
    preview = build_task_dag_crew_bridge_preview(
        requests=requests,
        receipts=receipts,
        max_records=max_records,
        worker_type=worker_type,
        status=status,
        task_id=task_id,
        has_receipt=has_receipt,
    )
    return [
        TaskDAGCrewBridgePreviewRecord(
            schema_version=item.get("schemaVersion", ""),
            task_id=item.get("taskId", ""),
            request_id=item.get("requestId", ""),
            receipt_id=item.get("receiptId", ""),
            task_brief_id=item.get("taskBriefId", ""),
            solve_node_id=item.get("solveNodeId", ""),
            worker_type=item.get("workerType", ""),
            status=item.get("status", ""),
            goal_snippet=item.get("goalSnippet", ""),
            summary_snippet=item.get("summarySnippet", ""),
            has_receipt=bool(item.get("hasReceipt")),
            evidence_refs=list(item.get("evidenceRefs") or []),
            warnings=list(item.get("warnings") or []),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in list(preview.get("records") or [])
    ]


def _pair_records(
    requests: list[dict[str, Any]],
    receipts: list[dict[str, Any]],
) -> list[TaskDAGCrewBridgePreviewRecord]:
    records: list[TaskDAGCrewBridgePreviewRecord] = []
    used_receipts: set[int] = set()
    for request in requests:
        receipt_index = _matching_receipt_index(request, receipts, used_receipts)
        if receipt_index is None:
            records.append(_record_from_pair(request, None))
            continue
        used_receipts.add(receipt_index)
        records.append(_record_from_pair(request, receipts[receipt_index]))
    for index, receipt in enumerate(receipts):
        if index in used_receipts:
            continue
        records.append(_record_from_pair(None, receipt))
    return records


def _record_from_pair(
    request: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
) -> TaskDAGCrewBridgePreviewRecord:
    if request is not None:
        source = request
    else:
        source = receipt or {}
    status_value = ""
    has_receipt = receipt is not None
    warnings: list[str] = []
    if request is None:
        warnings.append("missing_bridge_request")
    if receipt is None:
        warnings.append("missing_bridge_receipt")
        status_value = "missing_receipt"
    else:
        status_value = str(receipt["receipt"].status or "pending")
    request_obj = request["request"] if request is not None else None
    receipt_obj = receipt["receipt"] if receipt is not None else None
    evidence_refs = _merge_refs(
        request_obj.evidence_refs if request_obj is not None else [],
        receipt_obj.evidence_refs if receipt_obj is not None else [],
    )
    warnings = _safe_refs(
        [
            *warnings,
            *(request_obj.warnings if request_obj is not None else []),
            *(receipt_obj.warnings if receipt_obj is not None else []),
        ],
        limit=10,
    )
    metadata = _safe_metadata(
        {
            **(request_obj.metadata if request_obj is not None else {}),
            **(receipt_obj.metadata if receipt_obj is not None else {}),
        }
    )
    return TaskDAGCrewBridgePreviewRecord(
        schema_version=TASK_DAG_CREW_BRIDGE_PREVIEW_SCHEMA_VERSION,
        task_id=_first_non_empty(
            getattr(request_obj, "task_id", ""),
            getattr(receipt_obj, "task_id", ""),
            source.get("task_id", ""),
        ),
        request_id=getattr(request_obj, "request_id", ""),
        receipt_id=getattr(receipt_obj, "receipt_id", ""),
        task_brief_id=_first_non_empty(
            getattr(request_obj, "task_brief_id", ""),
            getattr(receipt_obj, "task_brief_id", ""),
        ),
        solve_node_id=_first_non_empty(
            getattr(request_obj, "solve_node_id", ""),
            getattr(receipt_obj, "solve_node_id", ""),
        ),
        worker_type=_first_non_empty(
            getattr(request_obj, "worker_type", ""),
            getattr(receipt_obj, "worker_type", ""),
            "default",
        ),
        status=status_value,
        goal_snippet=getattr(request_obj, "goal", ""),
        summary_snippet=getattr(receipt_obj, "summary", ""),
        has_receipt=has_receipt,
        evidence_refs=evidence_refs,
        warnings=warnings,
        metadata=metadata,
    )


def _matching_receipt_index(
    request: dict[str, Any],
    receipts: list[dict[str, Any]],
    used_receipts: set[int],
) -> int | None:
    for index, receipt in enumerate(receipts):
        if index in used_receipts:
            continue
        if receipt.get("request_id") and receipt.get("request_id") == request["request"].request_id:
            return index
    for index, receipt in enumerate(receipts):
        if index in used_receipts:
            continue
        if request["request"].task_id and request["request"].task_id == receipt["receipt"].task_id:
            return index
    for index, receipt in enumerate(receipts):
        if index in used_receipts:
            continue
        if (
            request["request"].task_brief_id
            and request["request"].task_brief_id == receipt["receipt"].task_brief_id
        ):
            return index
        if (
            request["request"].solve_node_id
            and request["request"].solve_node_id == receipt["receipt"].solve_node_id
        ):
            return index
    return None


def _request_info(value: Any) -> dict[str, Any]:
    request = build_task_dag_crew_bridge_request(value)
    return {
        "request": request,
        "request_id": request.request_id,
        "task_id": request.task_id,
    }


def _receipt_info(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    receipt = normalize_task_dag_crew_bridge_receipt(value)
    return {
        "receipt": receipt,
        "request_id": str(raw.get("requestId") or raw.get("request_id") or "").strip(),
        "task_id": receipt.task_id,
    }


def _filter_records(
    records: list[TaskDAGCrewBridgePreviewRecord],
    *,
    worker_type: str,
    status: str,
    task_id: str,
    has_receipt: bool | None,
) -> list[TaskDAGCrewBridgePreviewRecord]:
    worker_filter = str(worker_type or "").strip()
    status_filter = str(status or "").strip()
    task_filter = str(task_id or "").strip()
    result: list[TaskDAGCrewBridgePreviewRecord] = []
    for record in records:
        if worker_filter and record.worker_type != worker_filter:
            continue
        if status_filter and record.status != status_filter:
            continue
        if task_filter and task_filter not in record.task_id:
            continue
        if has_receipt is not None and record.has_receipt is not bool(has_receipt):
            continue
        result.append(record)
    return result


def _coerce_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (TaskDAGCrewBridgeRequest, TaskDAGCrewBridgeReceipt, dict)):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _merge_refs(*values: Any) -> list[str]:
    refs: list[str] = []
    for value in values:
        refs.extend(_safe_refs(value, limit=20))
    return _safe_refs(refs, limit=20)


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
        if isinstance(raw_value, bool) or raw_value is None:
            safe[key] = raw_value
        elif isinstance(raw_value, int):
            safe[key] = raw_value
        elif isinstance(raw_value, float):
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


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
