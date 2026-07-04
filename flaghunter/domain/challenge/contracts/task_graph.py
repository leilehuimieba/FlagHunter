from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TaskGraphNode:
    node_id: str
    title: str
    depends_on: list[str] = field(default_factory=list)
    strategy_ref: str | None = None
    task_ref: str | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "nodeId": self.node_id,
            "title": self.title,
            "dependsOn": [str(item) for item in self.depends_on],
            "strategyRef": self.strategy_ref,
            "taskRef": self.task_ref,
            "metadata": coerce_json_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskGraphNode":
        return cls(
            node_id=str(payload.get("nodeId", "")),
            title=str(payload.get("title", "")),
            depends_on=[str(item) for item in coerce_json_list(payload.get("dependsOn"))],
            strategy_ref=(
                str(payload["strategyRef"]) if payload.get("strategyRef") is not None else None
            ),
            task_ref=str(payload["taskRef"]) if payload.get("taskRef") is not None else None,
            metadata=coerce_json_dict(payload.get("metadata")),
        )
