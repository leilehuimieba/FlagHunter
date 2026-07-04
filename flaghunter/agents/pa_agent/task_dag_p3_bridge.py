"""Explicit TaskDAGPlan <-> P3 state bridge wrappers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ctf_state import CTFState
from .solve_node import (
    SolveNodeGraph,
    SolveNodeReceipt,
    solve_node_receipt_from_dict,
    solve_node_receipt_to_dict,
    task_brief_from_dict,
    task_brief_to_dict,
)
from .task_dag_p3_mapping import (
    TaskDAGMappingError,
    apply_solve_node_receipt_to_task,
    build_solve_node_for_dag_node,
    build_task_brief_for_dag_node,
    link_solve_node_to_task,
)
from .task_dag_plan import (
    TaskDAGPlan,
    TaskDAGStatus,
    TaskDAGTransitionError,
    mark_task_running,
    task_dag_plan_from_dict,
    task_dag_plan_to_dict,
)


TASK_DAG_P3_BRIDGE_START_SCHEMA_VERSION = "p4.task_dag_p3_bridge_start.v1"
TASK_DAG_P3_BRIDGE_RECEIPT_SCHEMA_VERSION = "p4.task_dag_p3_bridge_receipt.v1"


class TaskDAGP3BridgeError(TaskDAGMappingError):
    pass


@dataclass
class TaskDAGP3BridgeStartResult:
    schema_version: str = TASK_DAG_P3_BRIDGE_START_SCHEMA_VERSION
    plan_id: str = ""
    task_id: str = ""
    solve_node_id: str = ""
    task_brief_id: str = ""
    receipt_id: str = ""
    previous_status: str = ""
    next_status: str = ""
    updated_plan: TaskDAGPlan | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "planId": self.plan_id,
            "taskId": self.task_id,
            "solveNodeId": self.solve_node_id,
            "taskBriefId": self.task_brief_id,
            "receiptId": self.receipt_id,
            "previousStatus": self.previous_status,
            "nextStatus": self.next_status,
            "warnings": list(self.warnings),
        }


@dataclass
class TaskDAGP3BridgeReceiptResult:
    schema_version: str = TASK_DAG_P3_BRIDGE_RECEIPT_SCHEMA_VERSION
    plan_id: str = ""
    task_id: str = ""
    solve_node_id: str = ""
    task_brief_id: str = ""
    receipt_id: str = ""
    previous_status: str = ""
    next_status: str = ""
    updated_plan: TaskDAGPlan | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "planId": self.plan_id,
            "taskId": self.task_id,
            "solveNodeId": self.solve_node_id,
            "taskBriefId": self.task_brief_id,
            "receiptId": self.receipt_id,
            "previousStatus": self.previous_status,
            "nextStatus": self.next_status,
            "warnings": list(self.warnings),
        }


def record_task_dag_p3_start(
    state: CTFState,
    plan: TaskDAGPlan | dict[str, Any] | None,
    task_id: str,
    *,
    run_id: str = "",
    context_summary: str = "",
    allowed_tool_names: list[str] | None = None,
    blocked_tool_names: list[str] | None = None,
) -> TaskDAGP3BridgeStartResult:
    normalized = _bridge_plan(plan)
    normalized_task_id = str(task_id or "").strip()
    node = normalized.get_node(normalized_task_id)
    if node is None:
        raise TaskDAGP3BridgeError(f"unknown task: {normalized_task_id}")
    previous_status = node.status.value
    if node.status is TaskDAGStatus.PROPOSED:
        raise TaskDAGP3BridgeError(f"task {node.id} must be ready before start")
    if node.status in {
        TaskDAGStatus.SUCCEEDED,
        TaskDAGStatus.FAILED,
        TaskDAGStatus.INSUFFICIENT,
        TaskDAGStatus.SKIPPED,
        TaskDAGStatus.BLOCKED,
    }:
        raise TaskDAGP3BridgeError(f"task {node.id} is terminal")
    if node.status is not TaskDAGStatus.RUNNING and node.status is not TaskDAGStatus.READY:
        raise TaskDAGP3BridgeError(f"task {node.id} cannot be started from {previous_status}")
    _validate_existing_refs(state, node.solve_node_id, node.task_brief_id)
    if node.status is TaskDAGStatus.RUNNING and node.solve_node_id and node.task_brief_id:
        return TaskDAGP3BridgeStartResult(
            plan_id=normalized.id,
            task_id=node.id,
            solve_node_id=node.solve_node_id,
            task_brief_id=node.task_brief_id,
            previous_status=previous_status,
            next_status=previous_status,
            updated_plan=normalized,
        )

    solve_node = build_solve_node_for_dag_node(
        normalized,
        node.id,
        run_id=run_id,
    )
    brief = build_task_brief_for_dag_node(
        normalized,
        node.id,
        run_id=run_id,
        context_summary=context_summary,
        allowed_tool_names=allowed_tool_names,
        blocked_tool_names=blocked_tool_names,
    )
    snapshot = _snapshot_state(state)
    try:
        solve_node_id = state.record_solve_node(solve_node)
        brief.node_id = solve_node_id
        task_brief_id = state.record_task_brief(brief)
        updated = link_solve_node_to_task(
            normalized,
            node.id,
            solve_node_id=solve_node_id,
            task_brief_id=task_brief_id,
        )
        if node.status is TaskDAGStatus.READY:
            updated = mark_task_running(updated, node.id)
        state.set_task_dag_plan(updated)
        persisted = state.get_task_dag_plan()
        persisted_node = persisted.get_node(node.id)
        return TaskDAGP3BridgeStartResult(
            plan_id=persisted.id,
            task_id=node.id,
            solve_node_id=solve_node_id,
            task_brief_id=task_brief_id,
            previous_status=previous_status,
            next_status=(persisted_node.status.value if persisted_node else previous_status),
            updated_plan=persisted,
        )
    except Exception as exc:
        _restore_state(state, snapshot)
        raise TaskDAGP3BridgeError(str(exc)) from exc


def record_task_dag_p3_receipt(
    state: CTFState,
    plan: TaskDAGPlan | dict[str, Any] | None,
    task_id: str,
    receipt: SolveNodeReceipt | dict[str, Any],
) -> TaskDAGP3BridgeReceiptResult:
    normalized = _bridge_plan(plan)
    normalized_task_id = str(task_id or "").strip()
    node = normalized.get_node(normalized_task_id)
    if node is None:
        raise TaskDAGP3BridgeError(f"unknown task: {normalized_task_id}")
    normalized_receipt = _bridge_receipt(receipt)
    if not normalized_receipt.id:
        raise TaskDAGP3BridgeError("receipt id is required")
    if normalized_receipt.node_id and node.solve_node_id and normalized_receipt.node_id != node.solve_node_id:
        raise TaskDAGP3BridgeError("conflicting solve_node_id")
    if normalized_receipt.status in {"completed", "failed", "partial"} and node.status is not TaskDAGStatus.RUNNING:
        raise TaskDAGP3BridgeError(
            f"task {node.id} must be running before {normalized_receipt.status} receipt"
        )
    if normalized_receipt.status not in {"completed", "failed", "partial", "blocked", "skipped"}:
        raise TaskDAGP3BridgeError(f"invalid receipt status: {normalized_receipt.status}")
    previous_status = node.status.value
    try:
        updated = apply_solve_node_receipt_to_task(
            normalized,
            node.id,
            normalized_receipt,
        )
    except (TaskDAGMappingError, TaskDAGTransitionError) as exc:
        raise TaskDAGP3BridgeError(str(exc)) from exc
    snapshot = _snapshot_state(state)
    try:
        receipt_id = state.record_solve_node_receipt(normalized_receipt)
        state.set_task_dag_plan(updated)
        persisted = state.get_task_dag_plan()
        persisted_node = persisted.get_node(node.id)
        return TaskDAGP3BridgeReceiptResult(
            plan_id=persisted.id,
            task_id=node.id,
            solve_node_id=persisted_node.solve_node_id if persisted_node else node.solve_node_id,
            task_brief_id=persisted_node.task_brief_id if persisted_node else node.task_brief_id,
            receipt_id=receipt_id,
            previous_status=previous_status,
            next_status=(persisted_node.status.value if persisted_node else previous_status),
            updated_plan=persisted,
        )
    except Exception as exc:
        _restore_state(state, snapshot)
        raise TaskDAGP3BridgeError(str(exc)) from exc


def _bridge_plan(plan: TaskDAGPlan | dict[str, Any] | None) -> TaskDAGPlan:
    if plan is None:
        raise TaskDAGP3BridgeError("task DAG plan is required")
    try:
        normalized = task_dag_plan_from_dict(task_dag_plan_to_dict(plan))
    except Exception as exc:
        raise TaskDAGP3BridgeError("invalid task DAG plan") from exc
    if not normalized.nodes_by_id:
        raise TaskDAGP3BridgeError("task DAG plan is empty")
    if normalized.restore_warnings:
        raise TaskDAGP3BridgeError("task DAG plan has restore warnings")
    return normalized


def _bridge_receipt(receipt: SolveNodeReceipt | dict[str, Any]) -> SolveNodeReceipt:
    if isinstance(receipt, dict) and not str(receipt.get("id") or "").strip():
        raise TaskDAGP3BridgeError("receipt id is required")
    try:
        normalized = (
            receipt
            if isinstance(receipt, SolveNodeReceipt)
            else solve_node_receipt_from_dict(solve_node_receipt_to_dict(receipt))
        )
    except Exception as exc:
        raise TaskDAGP3BridgeError("invalid solve node receipt") from exc
    if not str(normalized.id or "").strip():
        raise TaskDAGP3BridgeError("receipt id is required")
    return normalized


def _validate_existing_refs(
    state: CTFState,
    solve_node_id: str,
    task_brief_id: str,
) -> None:
    normalized_node_id = str(solve_node_id or "").strip()
    normalized_brief_id = str(task_brief_id or "").strip()
    if normalized_node_id:
        existing_brief_id = _brief_id_for_node(state, normalized_node_id)
        if existing_brief_id and normalized_brief_id and existing_brief_id != normalized_brief_id:
            raise TaskDAGP3BridgeError("conflicting task_brief_id")
        if state.get_solve_node(normalized_node_id) is None:
            raise TaskDAGP3BridgeError("unknown solve_node_id")
    if normalized_brief_id:
        brief = state.get_task_brief(normalized_brief_id)
        if brief is None:
            raise TaskDAGP3BridgeError("unknown task_brief_id")
        if normalized_node_id and brief.node_id != normalized_node_id:
            raise TaskDAGP3BridgeError("conflicting solve_node_id")


def _brief_id_for_node(state: CTFState, node_id: str) -> str:
    normalized_node_id = str(node_id or "").strip()
    for brief_id, brief in state.task_briefs_by_id.items():
        if brief.node_id == normalized_node_id:
            return brief_id
    return ""


def _snapshot_state(state: CTFState) -> dict[str, Any]:
    return {
        "task_dag_plan": task_dag_plan_to_dict(state.get_task_dag_plan()),
        "solve_node_graph": state.solve_node_graph.to_dict(),
        "task_briefs_by_id": {
            key: task_brief_to_dict(value)
            for key, value in state.task_briefs_by_id.items()
        },
        "solve_node_receipts_by_id": {
            key: solve_node_receipt_to_dict(value)
            for key, value in state.solve_node_receipts_by_id.items()
        },
    }


def _restore_state(state: CTFState, snapshot: dict[str, Any]) -> None:
    state.task_dag_plan = task_dag_plan_from_dict(snapshot.get("task_dag_plan"))
    state.solve_node_graph = SolveNodeGraph.from_dict(snapshot.get("solve_node_graph"))
    state.task_briefs_by_id = {
        str(key): task_brief_from_dict(value)
        for key, value in dict(snapshot.get("task_briefs_by_id") or {}).items()
    }
    state.solve_node_receipts_by_id = {
        str(key): solve_node_receipt_from_dict(value)
        for key, value in dict(snapshot.get("solve_node_receipts_by_id") or {}).items()
    }
