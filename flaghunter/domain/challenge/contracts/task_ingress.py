from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list
from .sanitization import preview_text, sanitize_metadata


SCHEMA_VERSION = "challenge.task_ingress.v1"
TASK_INGRESS_REQUEST_SCHEMA_VERSION = "challenge.task_ingress_request.v1"
TASK_INGRESS_RECEIPT_SCHEMA_VERSION = "challenge.task_ingress_receipt.v1"
TASK_INGRESS_READBACK_SCHEMA_VERSION = "challenge.task_ingress_readback.v1"


@dataclass(frozen=True)
class TaskIngressRequest:
    task_id: str
    task_type: str
    instructions: str
    run_id: str = ""
    source_ref: str = ""
    artifact_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": TASK_INGRESS_REQUEST_SCHEMA_VERSION,
            "taskId": _clean(self.task_id),
            "taskType": _clean(self.task_type),
            "instructionsPreview": preview_text(self.instructions),
            "runId": _clean(self.run_id),
            "sourceRef": preview_text(self.source_ref),
            "artifactRefs": [preview_text(item) for item in _str_refs(self.artifact_refs)],
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskIngressRequest":
        instructions = payload.get("instructionsPreview", payload.get("instructions", ""))
        return cls(
            task_id=str(payload.get("taskId", "")),
            task_type=str(payload.get("taskType", "")),
            instructions=str(instructions or ""),
            run_id=str(payload.get("runId", "")),
            source_ref=str(payload.get("sourceRef", "")),
            artifact_refs=[
                str(item) for item in coerce_json_list(payload.get("artifactRefs"))
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class TaskIngressReceipt:
    receipt_id: str
    task_id: str
    status: str
    summary_preview: str = ""
    artifact_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": TASK_INGRESS_RECEIPT_SCHEMA_VERSION,
            "receiptId": _clean(self.receipt_id),
            "taskId": _clean(self.task_id),
            "status": _clean(self.status),
            "summaryPreview": preview_text(self.summary_preview),
            "artifactRefs": [preview_text(item) for item in _str_refs(self.artifact_refs)],
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskIngressReceipt":
        return cls(
            receipt_id=str(payload.get("receiptId", "")),
            task_id=str(payload.get("taskId", "")),
            status=str(payload.get("status", "")),
            summary_preview=str(payload.get("summaryPreview", "")),
            artifact_refs=[
                str(item) for item in coerce_json_list(payload.get("artifactRefs"))
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class TaskIngressReadback:
    run_id: str
    ingress_items: list[TaskIngressRequest | Mapping[str, Any]] = field(
        default_factory=list
    )
    receipts: list[TaskIngressReceipt | Mapping[str, Any]] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        item_payloads = [_coerce_request(item).to_dict() for item in self.ingress_items]
        receipt_payloads = [_coerce_receipt(item).to_dict() for item in self.receipts]
        return {
            "schemaVersion": TASK_INGRESS_READBACK_SCHEMA_VERSION,
            "runId": _clean(self.run_id),
            "ingressItems": item_payloads,
            "receipts": receipt_payloads,
            "summary": {
                "requestCount": len(item_payloads),
                "receiptCount": len(receipt_payloads),
                "taskTypeCounts": _counts(
                    item.get("taskType") for item in item_payloads
                ),
                "statusCounts": _counts(item.get("status") for item in receipt_payloads),
            },
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskIngressReadback":
        return cls(
            run_id=str(payload.get("runId", "")),
            ingress_items=[
                TaskIngressRequest.from_dict(item)
                for item in coerce_json_list(payload.get("ingressItems"))
                if isinstance(item, dict)
            ],
            receipts=[
                TaskIngressReceipt.from_dict(item)
                for item in coerce_json_list(payload.get("receipts"))
                if isinstance(item, dict)
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


def _coerce_request(value: TaskIngressRequest | Mapping[str, Any]) -> TaskIngressRequest:
    if isinstance(value, TaskIngressRequest):
        return value
    return TaskIngressRequest.from_dict(value)


def _coerce_receipt(value: TaskIngressReceipt | Mapping[str, Any]) -> TaskIngressReceipt:
    if isinstance(value, TaskIngressReceipt):
        return value
    return TaskIngressReceipt.from_dict(value)


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = _clean(value)
        if key:
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _str_refs(values: Any) -> list[str]:
    return [_clean(item) for item in coerce_json_list(values) if _clean(item)]


def _clean(value: Any) -> str:
    return str(value or "").strip()
