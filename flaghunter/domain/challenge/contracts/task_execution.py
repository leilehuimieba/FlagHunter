from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list
from .sanitization import preview_text, sanitize_metadata


SCHEMA_VERSION = "challenge.task_execution.v1"
TASK_EXECUTION_NODE_SCHEMA_VERSION = "challenge.task_execution_node.v1"
TASK_EXECUTION_EDGE_SCHEMA_VERSION = "challenge.task_execution_edge.v1"
TASK_BRIEF_SCHEMA_VERSION = "challenge.task_brief.v1"
TASK_EXECUTION_RECEIPT_SCHEMA_VERSION = "challenge.task_execution_receipt.v1"


@dataclass(frozen=True)
class TaskExecutionNode:
    node_id: str
    run_id: str = ""
    parent_id: str = ""
    task_kind: str = "generic"
    status: str = "planned"
    title_preview: str = ""
    goal_preview: str = ""
    summary_preview: str = ""
    claim_ids: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    receipt_ids: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": TASK_EXECUTION_NODE_SCHEMA_VERSION,
            "nodeId": _clean(self.node_id),
            "runId": _clean(self.run_id),
            "parentId": _clean(self.parent_id),
            "taskKind": _clean(self.task_kind) or "generic",
            "status": _clean(self.status) or "planned",
            "titlePreview": preview_text(self.title_preview),
            "goalPreview": preview_text(self.goal_preview),
            "summaryPreview": preview_text(self.summary_preview),
            "claimIds": _str_refs(self.claim_ids),
            "traceIds": _str_refs(self.trace_ids),
            "receiptIds": _str_refs(self.receipt_ids),
            "artifactRefs": [preview_text(item) for item in _str_refs(self.artifact_refs)],
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskExecutionNode":
        return cls(
            node_id=str(payload.get("nodeId", "")),
            run_id=str(payload.get("runId", "")),
            parent_id=str(payload.get("parentId", "")),
            task_kind=str(payload.get("taskKind", "generic")),
            status=str(payload.get("status", "planned")),
            title_preview=str(payload.get("titlePreview", "")),
            goal_preview=str(payload.get("goalPreview", "")),
            summary_preview=str(payload.get("summaryPreview", "")),
            claim_ids=[str(item) for item in coerce_json_list(payload.get("claimIds"))],
            trace_ids=[str(item) for item in coerce_json_list(payload.get("traceIds"))],
            receipt_ids=[str(item) for item in coerce_json_list(payload.get("receiptIds"))],
            artifact_refs=[
                str(item) for item in coerce_json_list(payload.get("artifactRefs"))
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class TaskExecutionEdge:
    source_id: str
    target_id: str
    relation: str = "depends_on"
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": TASK_EXECUTION_EDGE_SCHEMA_VERSION,
            "sourceId": _clean(self.source_id),
            "targetId": _clean(self.target_id),
            "relation": _clean(self.relation) or "depends_on",
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskExecutionEdge":
        return cls(
            source_id=str(payload.get("sourceId", "")),
            target_id=str(payload.get("targetId", "")),
            relation=str(payload.get("relation", "depends_on")),
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class TaskBrief:
    brief_id: str
    node_id: str = ""
    run_id: str = ""
    worker_type: str = "generic"
    objective_preview: str = ""
    context_summary_preview: str = ""
    constraints: list[str] = field(default_factory=list)
    allowed_tool_names: list[str] = field(default_factory=list)
    blocked_tool_names: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": TASK_BRIEF_SCHEMA_VERSION,
            "briefId": _clean(self.brief_id),
            "nodeId": _clean(self.node_id),
            "runId": _clean(self.run_id),
            "workerType": _clean(self.worker_type) or "generic",
            "objectivePreview": preview_text(self.objective_preview),
            "contextSummaryPreview": preview_text(self.context_summary_preview),
            "constraints": [preview_text(item) for item in _str_refs(self.constraints)],
            "allowedToolNames": _str_refs(self.allowed_tool_names),
            "blockedToolNames": _str_refs(self.blocked_tool_names),
            "claimIds": _str_refs(self.claim_ids),
            "traceIds": _str_refs(self.trace_ids),
            "artifactRefs": [preview_text(item) for item in _str_refs(self.artifact_refs)],
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskBrief":
        return cls(
            brief_id=str(payload.get("briefId", "")),
            node_id=str(payload.get("nodeId", "")),
            run_id=str(payload.get("runId", "")),
            worker_type=str(payload.get("workerType", "generic")),
            objective_preview=str(payload.get("objectivePreview", "")),
            context_summary_preview=str(payload.get("contextSummaryPreview", "")),
            constraints=[str(item) for item in coerce_json_list(payload.get("constraints"))],
            allowed_tool_names=[
                str(item) for item in coerce_json_list(payload.get("allowedToolNames"))
            ],
            blocked_tool_names=[
                str(item) for item in coerce_json_list(payload.get("blockedToolNames"))
            ],
            claim_ids=[str(item) for item in coerce_json_list(payload.get("claimIds"))],
            trace_ids=[str(item) for item in coerce_json_list(payload.get("traceIds"))],
            artifact_refs=[
                str(item) for item in coerce_json_list(payload.get("artifactRefs"))
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class TaskExecutionReceipt:
    receipt_id: str
    node_id: str = ""
    run_id: str = ""
    worker_id: str = ""
    worker_type: str = "generic"
    status: str = "completed"
    input_brief_id: str = ""
    output_summary_preview: str = ""
    claim_ids: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    error_class: str = ""
    error_summary_preview: str = ""
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": TASK_EXECUTION_RECEIPT_SCHEMA_VERSION,
            "receiptId": _clean(self.receipt_id),
            "nodeId": _clean(self.node_id),
            "runId": _clean(self.run_id),
            "workerId": _clean(self.worker_id),
            "workerType": _clean(self.worker_type) or "generic",
            "status": _clean(self.status) or "completed",
            "inputBriefId": _clean(self.input_brief_id),
            "outputSummaryPreview": preview_text(self.output_summary_preview),
            "claimIds": _str_refs(self.claim_ids),
            "traceIds": _str_refs(self.trace_ids),
            "artifactRefs": [preview_text(item) for item in _str_refs(self.artifact_refs)],
            "errorClass": preview_text(self.error_class),
            "errorSummaryPreview": preview_text(self.error_summary_preview),
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskExecutionReceipt":
        return cls(
            receipt_id=str(payload.get("receiptId", "")),
            node_id=str(payload.get("nodeId", "")),
            run_id=str(payload.get("runId", "")),
            worker_id=str(payload.get("workerId", "")),
            worker_type=str(payload.get("workerType", "generic")),
            status=str(payload.get("status", "completed")),
            input_brief_id=str(payload.get("inputBriefId", "")),
            output_summary_preview=str(payload.get("outputSummaryPreview", "")),
            claim_ids=[str(item) for item in coerce_json_list(payload.get("claimIds"))],
            trace_ids=[str(item) for item in coerce_json_list(payload.get("traceIds"))],
            artifact_refs=[
                str(item) for item in coerce_json_list(payload.get("artifactRefs"))
            ],
            error_class=str(payload.get("errorClass", "")),
            error_summary_preview=str(payload.get("errorSummaryPreview", "")),
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class TaskExecutionReadback:
    run_id: str
    nodes: list[TaskExecutionNode] = field(default_factory=list)
    edges: list[TaskExecutionEdge] = field(default_factory=list)
    briefs: list[TaskBrief] = field(default_factory=list)
    receipts: list[TaskExecutionReceipt] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        node_payloads = [_coerce_node(item).to_dict() for item in self.nodes]
        edge_payloads = [_coerce_edge(item).to_dict() for item in self.edges]
        brief_payloads = [_coerce_brief(item).to_dict() for item in self.briefs]
        receipt_payloads = [_coerce_receipt(item).to_dict() for item in self.receipts]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "runId": _clean(self.run_id),
            "nodes": node_payloads,
            "edges": edge_payloads,
            "briefs": brief_payloads,
            "receipts": receipt_payloads,
            "summary": {
                "nodeCount": len(node_payloads),
                "edgeCount": len(edge_payloads),
                "briefCount": len(brief_payloads),
                "receiptCount": len(receipt_payloads),
                "statusCounts": _counts(item.get("status") for item in node_payloads),
                "receiptStatusCounts": _counts(
                    item.get("status") for item in receipt_payloads
                ),
                "relationCounts": _counts(item.get("relation") for item in edge_payloads),
            },
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskExecutionReadback":
        return cls(
            run_id=str(payload.get("runId", "")),
            nodes=[
                TaskExecutionNode.from_dict(item)
                for item in coerce_json_list(payload.get("nodes"))
                if isinstance(item, dict)
            ],
            edges=[
                TaskExecutionEdge.from_dict(item)
                for item in coerce_json_list(payload.get("edges"))
                if isinstance(item, dict)
            ],
            briefs=[
                TaskBrief.from_dict(item)
                for item in coerce_json_list(payload.get("briefs"))
                if isinstance(item, dict)
            ],
            receipts=[
                TaskExecutionReceipt.from_dict(item)
                for item in coerce_json_list(payload.get("receipts"))
                if isinstance(item, dict)
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


def _coerce_node(value: TaskExecutionNode | Mapping[str, Any]) -> TaskExecutionNode:
    if isinstance(value, TaskExecutionNode):
        return value
    return TaskExecutionNode.from_dict(value)


def _coerce_edge(value: TaskExecutionEdge | Mapping[str, Any]) -> TaskExecutionEdge:
    if isinstance(value, TaskExecutionEdge):
        return value
    return TaskExecutionEdge.from_dict(value)


def _coerce_brief(value: TaskBrief | Mapping[str, Any]) -> TaskBrief:
    if isinstance(value, TaskBrief):
        return value
    return TaskBrief.from_dict(value)


def _coerce_receipt(
    value: TaskExecutionReceipt | Mapping[str, Any],
) -> TaskExecutionReceipt:
    if isinstance(value, TaskExecutionReceipt):
        return value
    return TaskExecutionReceipt.from_dict(value)


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
