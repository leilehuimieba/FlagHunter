from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list
from .sanitization import preview_text


SCHEMA_VERSION = "challenge.progress.v1"
TASK_PROGRESS_SCHEMA_VERSION = "challenge.task_progress.v1"
WORKER_TRACE_SCHEMA_VERSION = "challenge.worker_trace.v1"


@dataclass(frozen=True)
class TaskProgressRef:
    task_id: str
    status: str
    title_preview: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    receipt_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": TASK_PROGRESS_SCHEMA_VERSION,
            "taskId": str(self.task_id or "").strip(),
            "status": str(self.status or "").strip(),
            "titlePreview": preview_text(self.title_preview),
            "evidenceRefs": _str_refs(self.evidence_refs),
            "receiptRefs": _str_refs(self.receipt_refs),
            "metadata": coerce_json_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskProgressRef":
        return cls(
            task_id=str(payload.get("taskId", "")),
            status=str(payload.get("status", "")),
            title_preview=str(payload.get("titlePreview", "")),
            evidence_refs=[str(item) for item in coerce_json_list(payload.get("evidenceRefs"))],
            receipt_refs=[str(item) for item in coerce_json_list(payload.get("receiptRefs"))],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class WorkerTraceRef:
    worker_id: str
    task_id: str
    worker_type: str = ""
    status: str = ""
    summary_preview: str = ""
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": WORKER_TRACE_SCHEMA_VERSION,
            "workerId": str(self.worker_id or "").strip(),
            "taskId": str(self.task_id or "").strip(),
            "workerType": str(self.worker_type or "").strip(),
            "status": str(self.status or "").strip(),
            "summaryPreview": preview_text(self.summary_preview),
            "metadata": coerce_json_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkerTraceRef":
        return cls(
            worker_id=str(payload.get("workerId", "")),
            task_id=str(payload.get("taskId", "")),
            worker_type=str(payload.get("workerType", "")),
            status=str(payload.get("status", "")),
            summary_preview=str(payload.get("summaryPreview", "")),
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class ChallengeProgressReadback:
    run_id: str
    task_refs: list[TaskProgressRef] = field(default_factory=list)
    worker_refs: list[WorkerTraceRef] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        task_payloads = [_coerce_task_ref(item).to_dict() for item in self.task_refs]
        worker_payloads = [_coerce_worker_ref(item).to_dict() for item in self.worker_refs]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "runId": str(self.run_id or "").strip(),
            "taskRefs": task_payloads,
            "workerRefs": worker_payloads,
            "summary": {
                "taskCount": len(task_payloads),
                "workerCount": len(worker_payloads),
                "statusCounts": _counts(item.get("status") for item in task_payloads),
                "workerStatusCounts": _counts(
                    item.get("status") for item in worker_payloads
                ),
            },
            "metadata": coerce_json_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ChallengeProgressReadback":
        return cls(
            run_id=str(payload.get("runId", "")),
            task_refs=[
                TaskProgressRef.from_dict(item)
                for item in coerce_json_list(payload.get("taskRefs"))
                if isinstance(item, dict)
            ],
            worker_refs=[
                WorkerTraceRef.from_dict(item)
                for item in coerce_json_list(payload.get("workerRefs"))
                if isinstance(item, dict)
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


def _coerce_task_ref(value: TaskProgressRef | Mapping[str, Any]) -> TaskProgressRef:
    if isinstance(value, TaskProgressRef):
        return value
    return TaskProgressRef.from_dict(value)


def _coerce_worker_ref(value: WorkerTraceRef | Mapping[str, Any]) -> WorkerTraceRef:
    if isinstance(value, WorkerTraceRef):
        return value
    return WorkerTraceRef.from_dict(value)


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "").strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _str_refs(values: Any) -> list[str]:
    return [
        str(item).strip()
        for item in coerce_json_list(values)
        if str(item or "").strip()
    ]
