"""P3 SolveNode schema skeleton and compact readback helpers."""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from typing import Any

from flaghunter.domain import UuidIdentityService

SCHEMA_VERSION = "p3.solve_node_snapshot.v1"
GRAPH_SCHEMA_VERSION = "p3.solve_node_graph.v1"
EDGE_RELATIONS = frozenset({"depends_on", "blocks", "derived_from", "reports_to"})
TASK_BRIEF_SCHEMA_VERSION = "p3.task_brief_readback.v1"
NODE_RECEIPT_SCHEMA_VERSION = "p3.solve_node_receipt_readback.v1"
NODE_RECEIPT_STATUSES = frozenset(
    {"completed", "failed", "blocked", "skipped", "partial"}
)


def _new_id(prefix: str) -> str:
    # C-05 / ADR 0002: full 32-hex uuid4 via the identity port.
    return UuidIdentityService().new_id(prefix)


def _now_ts() -> float:
    return time.time()


class SolveNodeKind(str, Enum):
    ROOT = "root"
    RECON = "recon"
    HYPOTHESIS = "hypothesis"
    EXPLOIT = "exploit"
    VERIFY = "verify"
    REPORT = "report"
    GENERIC = "generic"


class SolveNodeStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SolveNode:
    id: str = field(default_factory=lambda: _new_id("node"))
    run_id: str = ""
    parent_id: str = ""
    kind: SolveNodeKind = SolveNodeKind.GENERIC
    status: SolveNodeStatus = SolveNodeStatus.PLANNED
    title: str = ""
    goal: str = ""
    summary: str = ""
    created_at: float = field(default_factory=_now_ts)
    updated_at: float = field(default_factory=_now_ts)
    started_at: float | None = None
    finished_at: float | None = None
    claim_ids: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    receipt_ids: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id or "").strip() or _new_id("node")
        self.run_id = str(self.run_id or "").strip()
        self.parent_id = str(self.parent_id or "").strip()
        self.kind = _coerce_kind(self.kind)
        self.status = _coerce_status(self.status)
        self.title = str(self.title or "").strip()
        self.goal = str(self.goal or "").strip()
        self.summary = str(self.summary or "")
        self.claim_ids = _coerce_str_list(self.claim_ids)
        self.trace_ids = _coerce_str_list(self.trace_ids)
        self.receipt_ids = _coerce_str_list(self.receipt_ids)
        self.artifact_refs = _coerce_str_list(self.artifact_refs)
        self.metadata = (
            dict(self.metadata or {}) if isinstance(self.metadata, dict) else {}
        )
        self.created_at = _coerce_float(self.created_at, default=_now_ts())
        self.updated_at = _coerce_float(self.updated_at, default=self.created_at)
        self.started_at = _coerce_optional_float(self.started_at)
        self.finished_at = _coerce_optional_float(self.finished_at)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["status"] = self.status.value
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SolveNode":
        payload = dict(data or {})
        payload["kind"] = _coerce_kind(payload.get("kind", SolveNodeKind.GENERIC))
        payload["status"] = _coerce_status(
            payload.get("status", SolveNodeStatus.PLANNED)
        )
        for key in ["claim_ids", "trace_ids", "receipt_ids", "artifact_refs"]:
            payload[key] = _coerce_str_list(payload.get(key, []))
        payload["metadata"] = (
            dict(payload.get("metadata") or {})
            if isinstance(payload.get("metadata"), dict)
            else {}
        )
        allowed_fields = {item.name for item in fields(cls)}
        payload = {
            key: value for key, value in payload.items() if key in allowed_fields
        }
        return cls(**payload)


@dataclass
class SolveNodeEdge:
    source_id: str
    target_id: str
    relation: str = "depends_on"
    created_at: float = field(default_factory=_now_ts)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source_id = str(self.source_id or "").strip()
        self.target_id = str(self.target_id or "").strip()
        self.relation = _coerce_relation(self.relation)
        self.created_at = _coerce_float(self.created_at, default=_now_ts())
        self.metadata = (
            dict(self.metadata or {}) if isinstance(self.metadata, dict) else {}
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SolveNodeEdge":
        payload = dict(data or {})
        payload.setdefault("source_id", "")
        payload.setdefault("target_id", "")
        payload["relation"] = _coerce_relation(payload.get("relation", "depends_on"))
        payload["metadata"] = (
            dict(payload.get("metadata") or {})
            if isinstance(payload.get("metadata"), dict)
            else {}
        )
        allowed_fields = {item.name for item in fields(cls)}
        payload = {
            key: value for key, value in payload.items() if key in allowed_fields
        }
        return cls(**payload)


class SolveNodeGraphError(ValueError):
    pass


@dataclass
class SolveNodeGraph:
    nodes_by_id: dict[str, SolveNode] = field(default_factory=dict)
    edges: list[SolveNodeEdge] = field(default_factory=list)
    restore_warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        original_edges = list(self.edges or [])
        normalized_nodes: dict[str, SolveNode] = {}
        for node in dict(self.nodes_by_id or {}).values():
            normalized = solve_node_from_dict(solve_node_to_dict(node))
            normalized_nodes[normalized.id] = normalized
        self.nodes_by_id = normalized_nodes
        self.edges = []
        self.restore_warnings = _coerce_str_list(self.restore_warnings)
        for edge_data in original_edges:
            self._restore_edge(edge_data)

    def add_node(self, node: SolveNode | dict[str, Any]) -> SolveNode:
        normalized = solve_node_from_dict(solve_node_to_dict(node))
        self.nodes_by_id[normalized.id] = normalized
        return normalized

    def get_node(self, node_id: str) -> SolveNode | None:
        return self.nodes_by_id.get(str(node_id or "").strip())

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        *,
        relation: str = "depends_on",
        metadata: dict[str, Any] | None = None,
    ) -> SolveNodeEdge:
        edge = SolveNodeEdge(
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            metadata=metadata or {},
        )
        existing = self._existing_edge(edge)
        if existing is not None:
            return existing
        self._validate_edge(edge)
        self.edges.append(edge)
        return edge

    def to_dict(self) -> dict[str, Any]:
        nodes = [node.to_dict() for node in self.nodes_by_id.values()]
        edges = [edge.to_dict() for edge in self.edges]
        return {
            "schemaVersion": GRAPH_SCHEMA_VERSION,
            "nodes": nodes,
            "edges": edges,
            "summary": _graph_summary(
                nodes=[solve_node_from_dict(node) for node in nodes],
                edges=[solve_node_edge_from_dict(edge) for edge in edges],
                exported_node_count=len(nodes),
                exported_edge_count=len(edges),
                restore_warning_count=len(self.restore_warnings),
            ),
            "restoreWarnings": [
                _preview(item, limit=160) for item in self.restore_warnings
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SolveNodeGraph":
        payload = dict(data or {})
        graph = cls()
        for node_data in list(payload.get("nodes") or []):
            graph.add_node(solve_node_from_dict(node_data))
        for edge_data in list(payload.get("edges") or []):
            graph._restore_edge(edge_data)
        graph.restore_warnings.extend(
            _coerce_str_list(payload.get("restoreWarnings", []))
        )
        return graph

    def _restore_edge(self, edge_data: SolveNodeEdge | dict[str, Any]) -> None:
        try:
            edge = solve_node_edge_from_dict(solve_node_edge_to_dict(edge_data))
            self._append_restored_edge(edge)
        except (TypeError, ValueError) as exc:
            self.restore_warnings.append(_preview(str(exc), limit=160))

    def _append_restored_edge(self, edge: SolveNodeEdge) -> SolveNodeEdge:
        existing = self._existing_edge(edge)
        if existing is not None:
            return existing
        self._validate_edge(edge)
        self.edges.append(edge)
        return edge

    def _existing_edge(self, edge: SolveNodeEdge) -> SolveNodeEdge | None:
        for existing in self.edges:
            if (
                existing.source_id == edge.source_id
                and existing.target_id == edge.target_id
                and existing.relation == edge.relation
            ):
                return existing
        return None

    def _validate_edge(self, edge: SolveNodeEdge) -> None:
        if edge.source_id == edge.target_id:
            raise SolveNodeGraphError("self edge is not allowed")
        if edge.source_id not in self.nodes_by_id:
            raise SolveNodeGraphError(f"missing source node: {edge.source_id}")
        if edge.target_id not in self.nodes_by_id:
            raise SolveNodeGraphError(f"missing target node: {edge.target_id}")
        if self._has_path(edge.target_id, edge.source_id):
            raise SolveNodeGraphError(
                f"cycle detected: {edge.source_id} -> {edge.target_id}"
            )

    def _has_path(self, start_id: str, target_id: str) -> bool:
        stack = [start_id]
        seen: set[str] = set()
        while stack:
            node_id = stack.pop()
            if node_id == target_id:
                return True
            if node_id in seen:
                continue
            seen.add(node_id)
            stack.extend(
                edge.target_id for edge in self.edges if edge.source_id == node_id
            )
        return False


@dataclass
class TaskBrief:
    id: str = field(default_factory=lambda: _new_id("brief"))
    node_id: str = ""
    run_id: str = ""
    worker_type: str = "generic"
    objective: str = ""
    context_summary: str = ""
    constraints: list[str] = field(default_factory=list)
    allowed_tool_names: list[str] = field(default_factory=list)
    blocked_tool_names: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=_now_ts)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id or "").strip() or _new_id("brief")
        self.node_id = str(self.node_id or "").strip()
        self.run_id = str(self.run_id or "").strip()
        self.worker_type = str(self.worker_type or "generic").strip() or "generic"
        self.objective = str(self.objective or "")
        self.context_summary = str(self.context_summary or "")
        self.constraints = _coerce_str_list(self.constraints)
        self.allowed_tool_names = _coerce_str_list(self.allowed_tool_names)
        self.blocked_tool_names = _coerce_str_list(self.blocked_tool_names)
        self.claim_ids = _coerce_str_list(self.claim_ids)
        self.trace_ids = _coerce_str_list(self.trace_ids)
        self.artifact_refs = _coerce_str_list(self.artifact_refs)
        self.created_at = _coerce_float(self.created_at, default=_now_ts())
        self.metadata = (
            dict(self.metadata or {}) if isinstance(self.metadata, dict) else {}
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TaskBrief":
        payload = dict(data or {})
        for key in [
            "constraints",
            "allowed_tool_names",
            "blocked_tool_names",
            "claim_ids",
            "trace_ids",
            "artifact_refs",
        ]:
            payload[key] = _coerce_str_list(payload.get(key, []))
        payload["metadata"] = (
            dict(payload.get("metadata") or {})
            if isinstance(payload.get("metadata"), dict)
            else {}
        )
        allowed_fields = {item.name for item in fields(cls)}
        payload = {
            key: value for key, value in payload.items() if key in allowed_fields
        }
        return cls(**payload)


@dataclass
class SolveNodeReceipt:
    id: str = field(default_factory=lambda: _new_id("node_receipt"))
    node_id: str = ""
    run_id: str = ""
    worker_id: str = ""
    worker_type: str = "generic"
    status: str = "completed"
    started_at: float | None = None
    finished_at: float | None = None
    duration_ms: int | None = None
    input_brief_id: str = ""
    output_summary: str = ""
    claim_ids: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    error_class: str = ""
    error_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id or "").strip() or _new_id("node_receipt")
        self.node_id = str(self.node_id or "").strip()
        self.run_id = str(self.run_id or "").strip()
        self.worker_id = str(self.worker_id or "").strip()
        self.worker_type = str(self.worker_type or "generic").strip() or "generic"
        self.status = _coerce_receipt_status(self.status)
        self.started_at = _coerce_optional_float(self.started_at)
        self.finished_at = _coerce_optional_float(self.finished_at)
        self.duration_ms = _coerce_optional_int(self.duration_ms)
        self.input_brief_id = str(self.input_brief_id or "").strip()
        self.output_summary = str(self.output_summary or "")
        self.claim_ids = _coerce_str_list(self.claim_ids)
        self.trace_ids = _coerce_str_list(self.trace_ids)
        self.artifact_refs = _coerce_str_list(self.artifact_refs)
        self.error_class = str(self.error_class or "").strip()
        self.error_summary = str(self.error_summary or "")
        self.metadata = (
            dict(self.metadata or {}) if isinstance(self.metadata, dict) else {}
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SolveNodeReceipt":
        payload = dict(data or {})
        payload["status"] = _coerce_receipt_status(payload.get("status", "completed"))
        for key in ["claim_ids", "trace_ids", "artifact_refs"]:
            payload[key] = _coerce_str_list(payload.get(key, []))
        payload["metadata"] = (
            dict(payload.get("metadata") or {})
            if isinstance(payload.get("metadata"), dict)
            else {}
        )
        allowed_fields = {item.name for item in fields(cls)}
        payload = {
            key: value for key, value in payload.items() if key in allowed_fields
        }
        return cls(**payload)


def solve_node_to_dict(node: SolveNode | dict[str, Any]) -> dict[str, Any]:
    if isinstance(node, SolveNode):
        return node.to_dict()
    return SolveNode.from_dict(dict(node or {})).to_dict()


def solve_node_from_dict(data: dict[str, Any] | None) -> SolveNode:
    return SolveNode.from_dict(data)


def solve_node_edge_to_dict(edge: SolveNodeEdge | dict[str, Any]) -> dict[str, Any]:
    if isinstance(edge, SolveNodeEdge):
        return edge.to_dict()
    return SolveNodeEdge.from_dict(dict(edge or {})).to_dict()


def solve_node_edge_from_dict(data: dict[str, Any] | None) -> SolveNodeEdge:
    return SolveNodeEdge.from_dict(data)


def task_brief_to_dict(brief: TaskBrief | dict[str, Any]) -> dict[str, Any]:
    if isinstance(brief, TaskBrief):
        return brief.to_dict()
    return TaskBrief.from_dict(dict(brief or {})).to_dict()


def task_brief_from_dict(data: dict[str, Any] | None) -> TaskBrief:
    return TaskBrief.from_dict(data)


def solve_node_receipt_to_dict(
    receipt: SolveNodeReceipt | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(receipt, SolveNodeReceipt):
        return receipt.to_dict()
    return SolveNodeReceipt.from_dict(dict(receipt or {})).to_dict()


def solve_node_receipt_from_dict(
    data: dict[str, Any] | None,
) -> SolveNodeReceipt:
    return SolveNodeReceipt.from_dict(data)


def empty_solve_node_snapshot() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "nodes": [],
        "summary": {
            "nodeCount": 0,
            "exportedNodeCount": 0,
            "truncatedNodeCount": 0,
            "statusCounts": {},
            "kindCounts": {},
        },
    }


def empty_solve_graph_snapshot() -> dict[str, Any]:
    return {
        "schemaVersion": GRAPH_SCHEMA_VERSION,
        "nodes": [],
        "edges": [],
        "summary": {
            "nodeCount": 0,
            "edgeCount": 0,
            "exportedNodeCount": 0,
            "exportedEdgeCount": 0,
            "truncatedNodeCount": 0,
            "truncatedEdgeCount": 0,
            "statusCounts": {},
            "kindCounts": {},
            "relationCounts": {},
            "restoreWarningCount": 0,
        },
        "restoreWarnings": [],
    }


def build_solve_node_readback(
    nodes: (
        list[SolveNode | dict[str, Any]] | tuple[SolveNode | dict[str, Any], ...] | None
    ),
    *,
    limit: int = 20,
    preview_limit: int = 160,
) -> dict[str, Any]:
    normalized_nodes = [
        solve_node_from_dict(solve_node_to_dict(item)) for item in list(nodes or [])
    ]
    normalized_limit = max(0, int(limit))
    selected = normalized_nodes[-normalized_limit:] if normalized_limit else []
    preview = max(1, int(preview_limit))
    projected = [_node_projection(node, preview_limit=preview) for node in selected]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "nodes": projected,
        "summary": {
            "nodeCount": len(normalized_nodes),
            "exportedNodeCount": len(projected),
            "truncatedNodeCount": max(0, len(normalized_nodes) - len(projected)),
            "statusCounts": _counts(node.status.value for node in normalized_nodes),
            "kindCounts": _counts(node.kind.value for node in normalized_nodes),
        },
    }


def build_solve_graph_readback(
    graph: SolveNodeGraph | dict[str, Any] | None,
    *,
    node_limit: int = 20,
    edge_limit: int = 50,
    preview_limit: int = 160,
) -> dict[str, Any]:
    normalized = (
        graph if isinstance(graph, SolveNodeGraph) else SolveNodeGraph.from_dict(graph)
    )
    nodes = list(normalized.nodes_by_id.values())
    edges = list(normalized.edges)
    normalized_node_limit = max(0, int(node_limit))
    normalized_edge_limit = max(0, int(edge_limit))
    selected_nodes = nodes[-normalized_node_limit:] if normalized_node_limit else []
    selected_edges = edges[-normalized_edge_limit:] if normalized_edge_limit else []
    preview = max(1, int(preview_limit))
    projected_nodes = [
        _node_projection(node, preview_limit=preview) for node in selected_nodes
    ]
    projected_edges = [
        _edge_projection(edge, preview_limit=preview) for edge in selected_edges
    ]
    return {
        "schemaVersion": GRAPH_SCHEMA_VERSION,
        "nodes": projected_nodes,
        "edges": projected_edges,
        "summary": _graph_summary(
            nodes=nodes,
            edges=edges,
            exported_node_count=len(projected_nodes),
            exported_edge_count=len(projected_edges),
            restore_warning_count=len(normalized.restore_warnings),
        ),
        "restoreWarnings": [
            _preview(item, limit=preview) for item in normalized.restore_warnings
        ],
    }


def build_task_brief_readback(
    briefs: (
        list[TaskBrief | dict[str, Any]] | tuple[TaskBrief | dict[str, Any], ...] | None
    ),
    *,
    limit: int = 20,
    preview_limit: int = 160,
) -> dict[str, Any]:
    normalized_briefs = [
        task_brief_from_dict(task_brief_to_dict(item)) for item in list(briefs or [])
    ]
    normalized_limit = max(0, int(limit))
    selected = normalized_briefs[-normalized_limit:] if normalized_limit else []
    preview = max(1, int(preview_limit))
    projected = [
        _task_brief_projection(brief, preview_limit=preview) for brief in selected
    ]
    return {
        "schemaVersion": TASK_BRIEF_SCHEMA_VERSION,
        "briefs": projected,
        "summary": {
            "briefCount": len(normalized_briefs),
            "exportedBriefCount": len(projected),
            "truncatedBriefCount": max(0, len(normalized_briefs) - len(projected)),
            "workerTypeCounts": _counts(
                _preview(brief.worker_type, limit=preview)
                for brief in normalized_briefs
            ),
        },
    }


def build_solve_node_receipt_readback(
    receipts: (
        list[SolveNodeReceipt | dict[str, Any]]
        | tuple[SolveNodeReceipt | dict[str, Any], ...]
        | None
    ),
    *,
    limit: int = 20,
    preview_limit: int = 160,
) -> dict[str, Any]:
    normalized_receipts = [
        solve_node_receipt_from_dict(solve_node_receipt_to_dict(item))
        for item in list(receipts or [])
    ]
    normalized_limit = max(0, int(limit))
    selected = normalized_receipts[-normalized_limit:] if normalized_limit else []
    preview = max(1, int(preview_limit))
    projected = [
        _solve_node_receipt_projection(receipt, preview_limit=preview)
        for receipt in selected
    ]
    return {
        "schemaVersion": NODE_RECEIPT_SCHEMA_VERSION,
        "receipts": projected,
        "summary": {
            "receiptCount": len(normalized_receipts),
            "exportedReceiptCount": len(projected),
            "truncatedReceiptCount": max(0, len(normalized_receipts) - len(projected)),
            "statusCounts": _counts(receipt.status for receipt in normalized_receipts),
            "workerTypeCounts": _counts(
                _preview(receipt.worker_type, limit=preview)
                for receipt in normalized_receipts
            ),
        },
    }


def _node_projection(node: SolveNode, *, preview_limit: int) -> dict[str, Any]:
    return {
        "nodeId": node.id,
        "runId": node.run_id,
        "parentId": node.parent_id,
        "kind": node.kind.value,
        "status": node.status.value,
        "titlePreview": _preview(node.title, limit=preview_limit),
        "goalPreview": _preview(node.goal, limit=preview_limit),
        "summaryPreview": _preview(node.summary, limit=preview_limit),
        "claimIds": list(node.claim_ids),
        "traceIds": list(node.trace_ids),
        "receiptIds": list(node.receipt_ids),
        "artifactRefs": [
            _preview(item, limit=preview_limit) for item in list(node.artifact_refs)
        ],
        "metadata": _safe_metadata(node.metadata, preview_limit=preview_limit),
        "createdAt": node.created_at,
        "updatedAt": node.updated_at,
        "startedAt": node.started_at,
        "finishedAt": node.finished_at,
    }


def _task_brief_projection(brief: TaskBrief, *, preview_limit: int) -> dict[str, Any]:
    return {
        "briefId": _preview(brief.id, limit=preview_limit),
        "nodeId": _preview(brief.node_id, limit=preview_limit),
        "runId": _preview(brief.run_id, limit=preview_limit),
        "workerType": _preview(brief.worker_type, limit=preview_limit),
        "objectivePreview": _preview(brief.objective, limit=preview_limit),
        "contextSummaryPreview": _preview(
            brief.context_summary,
            limit=preview_limit,
        ),
        "constraints": [
            _preview(item, limit=preview_limit) for item in brief.constraints
        ],
        "allowedToolNames": [
            _preview(item, limit=preview_limit) for item in brief.allowed_tool_names
        ],
        "blockedToolNames": [
            _preview(item, limit=preview_limit) for item in brief.blocked_tool_names
        ],
        "claimIds": list(brief.claim_ids),
        "traceIds": list(brief.trace_ids),
        "artifactRefs": [
            _preview(item, limit=preview_limit) for item in brief.artifact_refs
        ],
        "metadata": _safe_metadata(brief.metadata, preview_limit=preview_limit),
        "createdAt": brief.created_at,
    }


def _solve_node_receipt_projection(
    receipt: SolveNodeReceipt,
    *,
    preview_limit: int,
) -> dict[str, Any]:
    return {
        "receiptId": _preview(receipt.id, limit=preview_limit),
        "nodeId": _preview(receipt.node_id, limit=preview_limit),
        "runId": _preview(receipt.run_id, limit=preview_limit),
        "workerId": _preview(receipt.worker_id, limit=preview_limit),
        "workerType": _preview(receipt.worker_type, limit=preview_limit),
        "status": _preview(receipt.status, limit=preview_limit),
        "startedAt": receipt.started_at,
        "finishedAt": receipt.finished_at,
        "durationMs": receipt.duration_ms,
        "inputBriefId": _preview(receipt.input_brief_id, limit=preview_limit),
        "outputSummaryPreview": _preview(
            receipt.output_summary,
            limit=preview_limit,
        ),
        "claimIds": list(receipt.claim_ids),
        "traceIds": list(receipt.trace_ids),
        "artifactRefs": [
            _preview(item, limit=preview_limit) for item in receipt.artifact_refs
        ],
        "errorClass": _preview(receipt.error_class, limit=preview_limit),
        "errorSummaryPreview": _preview(receipt.error_summary, limit=preview_limit),
        "metadata": _safe_metadata(receipt.metadata, preview_limit=preview_limit),
    }


def _edge_projection(edge: SolveNodeEdge, *, preview_limit: int) -> dict[str, Any]:
    return {
        "sourceId": _preview(edge.source_id, limit=preview_limit),
        "targetId": _preview(edge.target_id, limit=preview_limit),
        "relation": _preview(edge.relation, limit=preview_limit),
        "metadata": _safe_metadata(edge.metadata, preview_limit=preview_limit),
        "createdAt": edge.created_at,
    }


def _coerce_kind(value: SolveNodeKind | str) -> SolveNodeKind:
    if isinstance(value, SolveNodeKind):
        return value
    try:
        return SolveNodeKind(str(value or "").strip())
    except ValueError:
        return SolveNodeKind.GENERIC


def _coerce_status(value: SolveNodeStatus | str) -> SolveNodeStatus:
    if isinstance(value, SolveNodeStatus):
        return value
    try:
        return SolveNodeStatus(str(value or "").strip())
    except ValueError:
        return SolveNodeStatus.PLANNED


def _coerce_relation(value: Any) -> str:
    relation = str(value or "").strip()
    if relation in EDGE_RELATIONS:
        return relation
    return "depends_on"


def _coerce_receipt_status(value: Any) -> str:
    status = str(value or "").strip()
    if status in NODE_RECEIPT_STATUSES:
        return status
    return "partial"


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        return []
    return [str(item).strip() for item in items if str(item or "").strip()]


def _coerce_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "").strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def _graph_summary(
    *,
    nodes: list[SolveNode],
    edges: list[SolveNodeEdge],
    exported_node_count: int,
    exported_edge_count: int,
    restore_warning_count: int,
) -> dict[str, Any]:
    return {
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "exportedNodeCount": exported_node_count,
        "exportedEdgeCount": exported_edge_count,
        "truncatedNodeCount": max(0, len(nodes) - exported_node_count),
        "truncatedEdgeCount": max(0, len(edges) - exported_edge_count),
        "statusCounts": _counts(node.status.value for node in nodes),
        "kindCounts": _counts(node.kind.value for node in nodes),
        "relationCounts": _counts(edge.relation for edge in edges),
        "restoreWarningCount": restore_warning_count,
    }


def _safe_metadata(metadata: dict[str, Any], *, preview_limit: int) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in sorted(metadata):
        safe_key = _preview(key, limit=preview_limit)
        value = metadata[key]
        if _is_sensitive_key(key):
            safe[safe_key] = "<redacted>"
            continue
        if isinstance(value, (bool, int, float)) or value is None:
            safe[safe_key] = value
            continue
        if isinstance(value, str):
            safe[safe_key] = _preview(value, limit=preview_limit)
            continue
        safe[safe_key] = "<redacted>"
    return safe


def _preview(value: Any, *, limit: int) -> str:
    return _redact_text(value)[: max(0, int(limit))]


def _is_sensitive_key(value: Any) -> bool:
    return bool(
        re.search(
            r"(?i)(token|api[_-]?key|password|secret|session|cookie|authorization)",
            str(value or ""),
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
        r"(?i)\b(token|api[_-]?key|password|secret|session|cookie|authorization)\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)([\"'])(token|api[_-]?key|password|secret|session|cookie|authorization)\1\s*:\s*([\"'])(.*?)\3",
        r"\1\2\1: \3<redacted>\3",
        text,
    )
    return text
