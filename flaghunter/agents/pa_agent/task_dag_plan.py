"""P4-B single-agent task DAG plan contract and readback helpers."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from typing import Any


TASK_DAG_PLAN_SCHEMA_VERSION = "p4.task_dag_plan.v1"
TASK_DAG_READY_SELECTION_SCHEMA_VERSION = "p4.task_dag_ready_selection.v1"
_DEPENDENCY_SATISFIED_STATUSES = {
    "succeeded",
    "skipped",
}
_TERMINAL_STATUSES = {
    "succeeded",
    "failed",
    "insufficient",
    "skipped",
    "blocked",
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _now_ts() -> float:
    return time.time()


class TaskDAGStatus(str, Enum):
    PROPOSED = "proposed"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    INSUFFICIENT = "insufficient"


@dataclass
class TaskDAGNode:
    id: str = field(default_factory=lambda: _new_id("task"))
    kind: str = "generic"
    title: str = ""
    goal: str = ""
    status: TaskDAGStatus = TaskDAGStatus.PROPOSED
    depends_on: list[str] = field(default_factory=list)
    task_brief_id: str = ""
    solve_node_id: str = ""
    receipt_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    verification_record_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=_now_ts)
    updated_at: float = field(default_factory=_now_ts)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id or "").strip() or _new_id("task")
        self.kind = str(self.kind or "generic").strip() or "generic"
        self.title = str(self.title or "")
        self.goal = str(self.goal or "")
        self.status = _coerce_status(self.status)
        self.depends_on = _coerce_str_list(self.depends_on)
        self.task_brief_id = str(self.task_brief_id or "").strip()
        self.solve_node_id = str(self.solve_node_id or "").strip()
        self.receipt_ids = _coerce_str_list(self.receipt_ids)
        self.claim_ids = _coerce_str_list(self.claim_ids)
        self.trace_ids = _coerce_str_list(self.trace_ids)
        self.verification_record_ids = _coerce_str_list(self.verification_record_ids)
        self.created_at = _coerce_float(self.created_at, default=_now_ts())
        self.updated_at = _coerce_float(self.updated_at, default=self.created_at)
        self.metadata = dict(self.metadata or {}) if isinstance(self.metadata, dict) else {}

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TaskDAGNode":
        payload = dict(data or {})
        payload["status"] = _coerce_status(payload.get("status", TaskDAGStatus.PROPOSED))
        for key in [
            "depends_on",
            "receipt_ids",
            "claim_ids",
            "trace_ids",
            "verification_record_ids",
        ]:
            payload[key] = _coerce_str_list(payload.get(key, []))
        payload["metadata"] = (
            dict(payload.get("metadata") or {})
            if isinstance(payload.get("metadata"), dict)
            else {}
        )
        allowed_fields = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in allowed_fields})


@dataclass
class TaskDAGEdge:
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
        self.metadata = dict(self.metadata or {}) if isinstance(self.metadata, dict) else {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TaskDAGEdge":
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
        return cls(**{key: value for key, value in payload.items() if key in allowed_fields})


class TaskDAGGraphError(ValueError):
    pass


class TaskDAGTransitionError(ValueError):
    pass


@dataclass
class TaskDAGPlan:
    id: str = field(default_factory=lambda: _new_id("task_dag_plan"))
    schema_version: str = TASK_DAG_PLAN_SCHEMA_VERSION
    nodes_by_id: dict[str, TaskDAGNode] = field(default_factory=dict)
    edges: list[TaskDAGEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    restore_warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.id = str(self.id or "").strip() or _new_id("task_dag_plan")
        self.schema_version = TASK_DAG_PLAN_SCHEMA_VERSION
        self.metadata = dict(self.metadata or {}) if isinstance(self.metadata, dict) else {}
        self.restore_warnings = _coerce_str_list(self.restore_warnings)
        raw_nodes = list(dict(self.nodes_by_id or {}).values())
        raw_edges = list(self.edges or [])
        self.nodes_by_id = {}
        self.edges = []
        for node in raw_nodes:
            normalized = task_dag_node_from_dict(task_dag_node_to_dict(node))
            normalized.depends_on = []
            self.nodes_by_id[normalized.id] = normalized
        for edge_data in raw_edges:
            self._restore_edge(edge_data)
        self._refresh_node_dependencies()

    def add_node(self, node: TaskDAGNode | dict[str, Any]) -> TaskDAGNode:
        normalized = task_dag_node_from_dict(task_dag_node_to_dict(node))
        dependencies = list(normalized.depends_on)
        normalized.depends_on = []
        previous_nodes = dict(self.nodes_by_id)
        previous_edges = list(self.edges)
        try:
            self.nodes_by_id[normalized.id] = normalized
            for dependency_id in dependencies:
                self.add_edge(dependency_id, normalized.id)
            self._refresh_node_dependencies()
            return self.nodes_by_id[normalized.id]
        except Exception:
            self.nodes_by_id = previous_nodes
            self.edges = previous_edges
            self._refresh_node_dependencies()
            raise

    def get_node(self, node_id: str) -> TaskDAGNode | None:
        return self.nodes_by_id.get(str(node_id or "").strip())

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        *,
        relation: str = "depends_on",
        metadata: dict[str, Any] | None = None,
    ) -> TaskDAGEdge:
        edge = TaskDAGEdge(
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
        self._refresh_node_dependencies()
        return edge

    def to_dict(self) -> dict[str, Any]:
        self._refresh_node_dependencies()
        nodes = [node.to_dict() for node in self.nodes_by_id.values()]
        edges = [edge.to_dict() for edge in self.edges]
        return {
            "schemaVersion": TASK_DAG_PLAN_SCHEMA_VERSION,
            "id": self.id,
            "nodes": nodes,
            "edges": edges,
            "metadata": dict(self.metadata),
            "summary": _summary(
                nodes=[task_dag_node_from_dict(node) for node in nodes],
                edges=[task_dag_edge_from_dict(edge) for edge in edges],
                exported_node_count=len(nodes),
                exported_edge_count=len(edges),
                restore_warning_count=len(self.restore_warnings),
            ),
            "restoreWarnings": [
                _preview(item, limit=160) for item in self.restore_warnings
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TaskDAGPlan":
        payload = dict(data or {})
        plan = cls(
            id=str(payload.get("id") or "").strip() or _new_id("task_dag_plan"),
            metadata=(
                dict(payload.get("metadata") or {})
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
        )
        node_dependencies: dict[str, list[str]] = {}
        for node_data in list(payload.get("nodes") or []):
            try:
                node = task_dag_node_from_dict(node_data)
                node_dependencies[node.id] = list(node.depends_on)
                node.depends_on = []
                plan.add_node(node)
            except Exception as exc:
                plan.restore_warnings.append(_preview(str(exc), limit=160))
        for node_id, dependencies in node_dependencies.items():
            for dependency_id in dependencies:
                plan._restore_edge(
                    {
                        "source_id": dependency_id,
                        "target_id": node_id,
                        "relation": "depends_on",
                    }
                )
        for edge_data in list(payload.get("edges") or []):
            plan._restore_edge(edge_data)
        plan.restore_warnings.extend(
            _coerce_str_list(payload.get("restoreWarnings", []))
        )
        plan._refresh_node_dependencies()
        return plan

    def _restore_edge(self, edge_data: TaskDAGEdge | dict[str, Any]) -> None:
        try:
            edge = task_dag_edge_from_dict(task_dag_edge_to_dict(edge_data))
            existing = self._existing_edge(edge)
            if existing is not None:
                return
            self._validate_edge(edge)
            self.edges.append(edge)
        except (TypeError, ValueError) as exc:
            self.restore_warnings.append(_preview(str(exc), limit=160))

    def _existing_edge(self, edge: TaskDAGEdge) -> TaskDAGEdge | None:
        for existing in self.edges:
            if (
                existing.source_id == edge.source_id
                and existing.target_id == edge.target_id
                and existing.relation == edge.relation
            ):
                return existing
        return None

    def _validate_edge(self, edge: TaskDAGEdge) -> None:
        if edge.source_id == edge.target_id:
            raise TaskDAGGraphError("self edge is not allowed")
        if edge.source_id not in self.nodes_by_id:
            raise TaskDAGGraphError(f"missing source task: {edge.source_id}")
        if edge.target_id not in self.nodes_by_id:
            raise TaskDAGGraphError(f"missing target task: {edge.target_id}")
        if self._has_path(edge.target_id, edge.source_id):
            raise TaskDAGGraphError(
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
                edge.target_id
                for edge in self.edges
                if edge.source_id == node_id
            )
        return False

    def _refresh_node_dependencies(self) -> None:
        dependencies_by_target: dict[str, list[str]] = {
            node_id: [] for node_id in self.nodes_by_id
        }
        for edge in self.edges:
            if edge.relation != "depends_on" or edge.target_id not in dependencies_by_target:
                continue
            if edge.source_id not in dependencies_by_target[edge.target_id]:
                dependencies_by_target[edge.target_id].append(edge.source_id)
        for node_id, node in self.nodes_by_id.items():
            node.depends_on = dependencies_by_target.get(node_id, [])


def task_dag_node_to_dict(node: TaskDAGNode | dict[str, Any]) -> dict[str, Any]:
    if isinstance(node, TaskDAGNode):
        return node.to_dict()
    return TaskDAGNode.from_dict(dict(node or {})).to_dict()


def task_dag_node_from_dict(data: dict[str, Any] | None) -> TaskDAGNode:
    return TaskDAGNode.from_dict(data)


def task_dag_edge_to_dict(edge: TaskDAGEdge | dict[str, Any]) -> dict[str, Any]:
    if isinstance(edge, TaskDAGEdge):
        return edge.to_dict()
    return TaskDAGEdge.from_dict(dict(edge or {})).to_dict()


def task_dag_edge_from_dict(data: dict[str, Any] | None) -> TaskDAGEdge:
    return TaskDAGEdge.from_dict(data)


def task_dag_plan_to_dict(plan: TaskDAGPlan | dict[str, Any]) -> dict[str, Any]:
    if isinstance(plan, TaskDAGPlan):
        return plan.to_dict()
    return TaskDAGPlan.from_dict(dict(plan or {})).to_dict()


def task_dag_plan_from_dict(data: dict[str, Any] | None) -> TaskDAGPlan:
    return TaskDAGPlan.from_dict(data)


def sanitize_task_dag_plan(plan: TaskDAGPlan | dict[str, Any] | None) -> TaskDAGPlan:
    normalized = task_dag_plan_from_dict(task_dag_plan_to_dict(plan or {}))
    sanitized = TaskDAGPlan(
        id=normalized.id,
        metadata=_safe_metadata(normalized.metadata, preview_limit=160),
    )
    for node in normalized.nodes_by_id.values():
        safe_node = TaskDAGNode(
            id=node.id,
            kind=_preview(node.kind, limit=160),
            title=_preview(node.title, limit=160),
            goal=_preview(node.goal, limit=160),
            status=node.status,
            task_brief_id=node.task_brief_id,
            solve_node_id=node.solve_node_id,
            receipt_ids=list(node.receipt_ids),
            claim_ids=list(node.claim_ids),
            trace_ids=list(node.trace_ids),
            verification_record_ids=list(node.verification_record_ids),
            created_at=node.created_at,
            updated_at=node.updated_at,
            metadata=_safe_metadata(node.metadata, preview_limit=160),
        )
        sanitized.add_node(safe_node)
    for edge in normalized.edges:
        try:
            sanitized.add_edge(
                edge.source_id,
                edge.target_id,
                relation=_preview(edge.relation, limit=160),
                metadata=_safe_metadata(edge.metadata, preview_limit=160),
            )
        except ValueError as exc:
            sanitized.restore_warnings.append(_preview(str(exc), limit=160))
    sanitized.restore_warnings.extend(
        _preview(item, limit=160) for item in normalized.restore_warnings
    )
    return sanitized


def empty_task_dag_plan_readback() -> dict[str, Any]:
    return {
        "schemaVersion": TASK_DAG_PLAN_SCHEMA_VERSION,
        "planId": "",
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
            "relationCounts": {},
            "restoreWarningCount": 0,
        },
        "restoreWarnings": [],
    }


def empty_task_dag_ready_selection(
    *,
    plan_id: str = "",
    reason: str = "empty_plan",
    restore_warning_count: int = 0,
) -> dict[str, Any]:
    return {
        "schemaVersion": TASK_DAG_READY_SELECTION_SCHEMA_VERSION,
        "planId": str(plan_id or "").strip(),
        "selectedTaskId": "",
        "selectedStatus": "",
        "reason": str(reason or "empty_plan").strip() or "empty_plan",
        "readyTaskIds": [],
        "blockedTaskIds": [],
        "dependencySummary": {
            "satisfiedDependencyCount": 0,
            "blockingDependencyCount": 0,
        },
        "restoreWarningCount": int(restore_warning_count or 0),
    }


def select_next_ready_task(plan: TaskDAGPlan | dict[str, Any] | None) -> dict[str, Any]:
    if plan is None:
        return empty_task_dag_ready_selection()
    normalized = task_dag_plan_from_dict(task_dag_plan_to_dict(plan))
    if normalized.restore_warnings:
        return empty_task_dag_ready_selection(
            plan_id=normalized.id,
            reason="restore_warnings_present",
            restore_warning_count=len(normalized.restore_warnings),
        )
    nodes = list(normalized.nodes_by_id.values())
    if not nodes:
        return empty_task_dag_ready_selection(plan_id=normalized.id)
    if any(node.status is TaskDAGStatus.RUNNING for node in nodes):
        return empty_task_dag_ready_selection(
            plan_id=normalized.id,
            reason="running_task_present",
        )

    ready_ids: list[str] = []
    blocked_ids: list[str] = []
    satisfied_count = 0
    blocking_count = 0
    for node in nodes:
        if node.status is not TaskDAGStatus.READY:
            continue
        dependency_result = _dependency_result(normalized, node)
        satisfied_count += dependency_result["satisfied"]
        blocking_count += dependency_result["blocking"]
        if dependency_result["blocking"]:
            blocked_ids.append(node.id)
        else:
            ready_ids.append(node.id)

    if ready_ids:
        return {
            "schemaVersion": TASK_DAG_READY_SELECTION_SCHEMA_VERSION,
            "planId": normalized.id,
            "selectedTaskId": ready_ids[0],
            "selectedStatus": TaskDAGStatus.READY.value,
            "reason": "selected",
            "readyTaskIds": ready_ids,
            "blockedTaskIds": blocked_ids,
            "dependencySummary": {
                "satisfiedDependencyCount": satisfied_count,
                "blockingDependencyCount": blocking_count,
            },
            "restoreWarningCount": len(normalized.restore_warnings),
        }
    return {
        "schemaVersion": TASK_DAG_READY_SELECTION_SCHEMA_VERSION,
        "planId": normalized.id,
        "selectedTaskId": "",
        "selectedStatus": "",
        "reason": "blocked_by_dependencies" if blocked_ids else "no_ready_tasks",
        "readyTaskIds": [],
        "blockedTaskIds": blocked_ids,
        "dependencySummary": {
            "satisfiedDependencyCount": satisfied_count,
            "blockingDependencyCount": blocking_count,
        },
        "restoreWarningCount": len(normalized.restore_warnings),
    }


def mark_task_ready(
    plan: TaskDAGPlan | dict[str, Any],
    task_id: str,
    *,
    reason: str = "",
) -> TaskDAGPlan:
    updated, node = _transition_target(plan, task_id)
    if node.status is not TaskDAGStatus.PROPOSED:
        raise TaskDAGTransitionError(
            f"task {node.id} cannot be marked ready from {node.status.value}"
        )
    dependency_result = _dependency_result(updated, node)
    if dependency_result["blocking"]:
        raise TaskDAGTransitionError(f"task {node.id} dependencies are not satisfied")
    replacement = task_dag_node_from_dict(task_dag_node_to_dict(node))
    replacement.status = TaskDAGStatus.READY
    replacement.updated_at = _now_ts()
    if str(reason or "").strip():
        replacement.metadata = dict(replacement.metadata)
        replacement.metadata["readyReason"] = _preview(reason, limit=160)
    updated.add_node(replacement)
    return updated


def mark_task_running(
    plan: TaskDAGPlan | dict[str, Any],
    task_id: str,
    *,
    started_at: float | None = None,
) -> TaskDAGPlan:
    updated, node = _transition_target(plan, task_id)
    if node.status.value in _TERMINAL_STATUSES:
        raise TaskDAGTransitionError(f"task {node.id} is terminal")
    if node.status is not TaskDAGStatus.READY:
        raise TaskDAGTransitionError(
            f"task {node.id} cannot be marked running from {node.status.value}"
        )
    replacement = task_dag_node_from_dict(task_dag_node_to_dict(node))
    replacement.status = TaskDAGStatus.RUNNING
    replacement.updated_at = _now_ts()
    if started_at is not None:
        replacement.metadata = dict(replacement.metadata)
        replacement.metadata["startedAt"] = _coerce_float(started_at, default=_now_ts())
    updated.add_node(replacement)
    return updated


def mark_task_finished(
    plan: TaskDAGPlan | dict[str, Any],
    task_id: str,
    *,
    status: TaskDAGStatus | str,
    receipt_id: str = "",
    solve_node_id: str = "",
    trace_ids: list[str] | tuple[str, ...] | None = None,
    claim_ids: list[str] | tuple[str, ...] | None = None,
    verification_record_ids: list[str] | tuple[str, ...] | None = None,
) -> TaskDAGPlan:
    updated, node = _transition_target(plan, task_id)
    finished_status = _coerce_status(status)
    if finished_status.value not in _TERMINAL_STATUSES:
        raise TaskDAGTransitionError(f"invalid finish status: {status}")
    if node.status is TaskDAGStatus.RUNNING:
        pass
    elif node.status in {TaskDAGStatus.PROPOSED, TaskDAGStatus.READY} and finished_status in {
        TaskDAGStatus.SKIPPED,
        TaskDAGStatus.BLOCKED,
    }:
        pass
    elif node.status.value in _TERMINAL_STATUSES:
        raise TaskDAGTransitionError(f"task {node.id} is terminal")
    else:
        raise TaskDAGTransitionError(
            f"task {node.id} cannot finish as {finished_status.value} from {node.status.value}"
        )

    replacement = task_dag_node_from_dict(task_dag_node_to_dict(node))
    replacement.status = finished_status
    replacement.updated_at = _now_ts()
    if str(receipt_id or "").strip():
        replacement.receipt_ids = _append_unique(
            replacement.receipt_ids,
            [str(receipt_id or "").strip()],
        )
    if str(solve_node_id or "").strip():
        replacement.solve_node_id = str(solve_node_id or "").strip()
    replacement.trace_ids = _append_unique(replacement.trace_ids, trace_ids or [])
    replacement.claim_ids = _append_unique(replacement.claim_ids, claim_ids or [])
    replacement.verification_record_ids = _append_unique(
        replacement.verification_record_ids,
        verification_record_ids or [],
    )
    updated.add_node(replacement)
    return updated


def build_task_dag_plan_readback(
    plan: TaskDAGPlan | dict[str, Any] | None,
    *,
    node_limit: int = 20,
    edge_limit: int = 50,
    preview_limit: int = 160,
) -> dict[str, Any]:
    if plan is None:
        return empty_task_dag_plan_readback()
    normalized = task_dag_plan_from_dict(task_dag_plan_to_dict(plan))
    normalized_node_limit = max(0, int(node_limit))
    normalized_edge_limit = max(0, int(edge_limit))
    normalized_preview = max(1, int(preview_limit))
    nodes = list(normalized.nodes_by_id.values())
    edges = list(normalized.edges)
    selected_nodes = _tail(nodes, normalized_node_limit)
    selected_edges = _tail(edges, normalized_edge_limit)
    return {
        "schemaVersion": TASK_DAG_PLAN_SCHEMA_VERSION,
        "planId": normalized.id,
        "nodes": [
            _node_readback(node, preview_limit=normalized_preview)
            for node in selected_nodes
        ],
        "edges": [
            _edge_readback(edge, preview_limit=normalized_preview)
            for edge in selected_edges
        ],
        "summary": _summary(
            nodes=nodes,
            edges=edges,
            exported_node_count=len(selected_nodes),
            exported_edge_count=len(selected_edges),
            restore_warning_count=len(normalized.restore_warnings),
        ),
        "restoreWarnings": [
            _preview(item, limit=normalized_preview)
            for item in normalized.restore_warnings
        ],
    }


def _node_readback(node: TaskDAGNode, *, preview_limit: int) -> dict[str, Any]:
    return {
        "taskId": node.id,
        "kind": _preview(node.kind, limit=preview_limit),
        "status": node.status.value,
        "titlePreview": _preview(node.title, limit=preview_limit),
        "goalPreview": _preview(node.goal, limit=preview_limit),
        "dependsOn": list(node.depends_on),
        "taskBriefId": node.task_brief_id,
        "solveNodeId": node.solve_node_id,
        "receiptIds": list(node.receipt_ids),
        "claimIds": list(node.claim_ids),
        "traceIds": list(node.trace_ids),
        "verificationRecordIds": list(node.verification_record_ids),
        "metadata": _safe_metadata(node.metadata, preview_limit=preview_limit),
    }


def _edge_readback(edge: TaskDAGEdge, *, preview_limit: int) -> dict[str, Any]:
    return {
        "sourceTaskId": edge.source_id,
        "targetTaskId": edge.target_id,
        "relation": _preview(edge.relation, limit=preview_limit),
        "metadata": _safe_metadata(edge.metadata, preview_limit=preview_limit),
    }


def _summary(
    *,
    nodes: list[TaskDAGNode],
    edges: list[TaskDAGEdge],
    exported_node_count: int,
    exported_edge_count: int,
    restore_warning_count: int,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for node in nodes:
        status_counts[node.status.value] = status_counts.get(node.status.value, 0) + 1
    relation_counts: dict[str, int] = {}
    for edge in edges:
        relation_counts[edge.relation] = relation_counts.get(edge.relation, 0) + 1
    return {
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "exportedNodeCount": int(exported_node_count),
        "exportedEdgeCount": int(exported_edge_count),
        "truncatedNodeCount": max(0, len(nodes) - int(exported_node_count)),
        "truncatedEdgeCount": max(0, len(edges) - int(exported_edge_count)),
        "statusCounts": dict(sorted(status_counts.items())),
        "relationCounts": dict(sorted(relation_counts.items())),
        "restoreWarningCount": int(restore_warning_count),
    }


def _tail(items: list[Any], limit: int) -> list[Any]:
    normalized_limit = max(0, int(limit))
    return list(items[-normalized_limit:]) if normalized_limit else []


def _transition_target(
    plan: TaskDAGPlan | dict[str, Any],
    task_id: str,
) -> tuple[TaskDAGPlan, TaskDAGNode]:
    updated = task_dag_plan_from_dict(task_dag_plan_to_dict(plan))
    normalized_task_id = str(task_id or "").strip()
    node = updated.get_node(normalized_task_id)
    if node is None:
        raise TaskDAGTransitionError(f"unknown task: {normalized_task_id}")
    return updated, node


def _dependency_result(plan: TaskDAGPlan, node: TaskDAGNode) -> dict[str, int]:
    satisfied = 0
    blocking = 0
    for dependency_id in list(node.depends_on):
        dependency = plan.get_node(dependency_id)
        if dependency is not None and dependency.status.value in _DEPENDENCY_SATISFIED_STATUSES:
            satisfied += 1
        else:
            blocking += 1
    return {"satisfied": satisfied, "blocking": blocking}


def _append_unique(existing: list[str], values: Any) -> list[str]:
    result = list(existing or [])
    for item in _coerce_str_list(values):
        if item not in result:
            result.append(item)
    return result


def _coerce_status(value: TaskDAGStatus | str) -> TaskDAGStatus:
    if isinstance(value, TaskDAGStatus):
        return value
    try:
        return TaskDAGStatus(str(value or "").strip().lower())
    except ValueError:
        return TaskDAGStatus.PROPOSED


def _coerce_relation(value: Any) -> str:
    normalized = str(value or "depends_on").strip() or "depends_on"
    return normalized


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


def _coerce_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_metadata(
    metadata: dict[str, Any],
    *,
    preview_limit: int,
) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in dict(metadata or {}).items():
        safe_key = _preview(key, limit=preview_limit)
        if _is_sensitive_key(key):
            safe[safe_key] = "<redacted>"
            continue
        if isinstance(value, (bool, int, float)) or value is None:
            safe[safe_key] = value
        elif isinstance(value, dict):
            safe[safe_key] = _safe_metadata(value, preview_limit=preview_limit)
        elif isinstance(value, (list, tuple)):
            safe[safe_key] = [
                _preview(item, limit=preview_limit)
                for item in value
            ]
        else:
            safe[safe_key] = _preview(value, limit=preview_limit)
    return safe


def _preview(value: Any, *, limit: int) -> str:
    text = _redact_text(value)
    if _looks_like_raw_body(text):
        return "<redacted raw body>"[: max(0, int(limit))]
    return text[: max(0, int(limit))]


def _is_sensitive_key(value: Any) -> bool:
    return bool(
        re.search(
            r"(?i)(token|api[_-]?key|password|secret|session|cookie|authorization)",
            str(value or ""),
        )
    )


def _looks_like_raw_body(text: str) -> bool:
    if not text:
        return False
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
        r"(?i)\b(token|api[_-]?key|password|secret|session|cookie|authorization)\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)([\"'](?:token|api[_-]?key|password|secret|session|cookie|authorization)[\"']\s*:\s*)([\"'][^\"']*[\"']|[^,\n\r}\]]+)",
        r'\1"<redacted>"',
        text,
    )
    return text
