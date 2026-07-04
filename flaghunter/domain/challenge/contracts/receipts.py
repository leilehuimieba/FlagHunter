from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TaskReceipt:
    receipt_id: str
    task_id: str
    outcome: str
    summary: str | None = None
    artifact_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "receiptId": self.receipt_id,
            "taskId": self.task_id,
            "outcome": self.outcome,
            "summary": self.summary,
            "artifactRefs": [str(item) for item in self.artifact_refs],
            "metadata": coerce_json_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskReceipt":
        return cls(
            receipt_id=str(payload.get("receiptId", "")),
            task_id=str(payload.get("taskId", "")),
            outcome=str(payload.get("outcome", "")),
            summary=str(payload["summary"]) if payload.get("summary") is not None else None,
            artifact_refs=[str(item) for item in coerce_json_list(payload.get("artifactRefs"))],
            metadata=coerce_json_dict(payload.get("metadata")),
        )
