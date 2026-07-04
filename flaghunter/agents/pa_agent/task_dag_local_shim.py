"""Local TaskDAGPlan caller shim for selector and P3 bridge composition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ctf_state import CTFState
from .solve_node import SolveNodeReceipt
from .task_dag_p3_bridge import (
    record_task_dag_p3_receipt,
    record_task_dag_p3_start,
)
from .task_dag_plan import (
    TaskDAGPlan,
    select_next_ready_task,
)


TASK_DAG_LOCAL_START_SCHEMA_VERSION = "p4.task_dag_local_start.v1"
TASK_DAG_LOCAL_RECEIPT_SCHEMA_VERSION = "p4.task_dag_local_receipt.v1"


@dataclass
class TaskDAGLocalStartResult:
    schema_version: str = TASK_DAG_LOCAL_START_SCHEMA_VERSION
    action: str = "start_next_ready"
    plan_id: str = ""
    selected_task_id: str = ""
    selection_reason: str = "empty_plan"
    previous_status: str = ""
    next_status: str = ""
    solve_node_id: str = ""
    task_brief_id: str = ""
    receipt_id: str = ""
    started: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "action": self.action,
            "planId": self.plan_id,
            "selectedTaskId": self.selected_task_id,
            "selectionReason": self.selection_reason,
            "previousStatus": self.previous_status,
            "nextStatus": self.next_status,
            "solveNodeId": self.solve_node_id,
            "taskBriefId": self.task_brief_id,
            "receiptId": self.receipt_id,
            "started": bool(self.started),
            "warnings": list(self.warnings),
        }


@dataclass
class TaskDAGLocalReceiptResult:
    schema_version: str = TASK_DAG_LOCAL_RECEIPT_SCHEMA_VERSION
    action: str = "apply_receipt"
    plan_id: str = ""
    task_id: str = ""
    selection_reason: str = ""
    previous_status: str = ""
    next_status: str = ""
    solve_node_id: str = ""
    task_brief_id: str = ""
    receipt_id: str = ""
    applied: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "action": self.action,
            "planId": self.plan_id,
            "taskId": self.task_id,
            "selectionReason": self.selection_reason,
            "previousStatus": self.previous_status,
            "nextStatus": self.next_status,
            "solveNodeId": self.solve_node_id,
            "taskBriefId": self.task_brief_id,
            "receiptId": self.receipt_id,
            "applied": bool(self.applied),
            "warnings": list(self.warnings),
        }


def start_next_ready_task_for_local_dag(
    state: CTFState,
    plan: TaskDAGPlan | dict[str, Any] | None = None,
    *,
    run_id: str = "",
    context_summary: str = "",
    allowed_tool_names: list[str] | None = None,
    blocked_tool_names: list[str] | None = None,
) -> TaskDAGLocalStartResult:
    active_plan = state.get_task_dag_plan() if plan is None else plan
    selection = select_next_ready_task(active_plan)
    selected_task_id = str(selection.get("selectedTaskId") or "").strip()
    reason = str(selection.get("reason") or "empty_plan").strip() or "empty_plan"
    if not selected_task_id:
        return TaskDAGLocalStartResult(
            plan_id=str(selection.get("planId") or "").strip(),
            selection_reason=reason,
            warnings=_selection_warnings(selection),
        )

    bridge_result = record_task_dag_p3_start(
        state,
        active_plan,
        selected_task_id,
        run_id=run_id,
        context_summary=context_summary,
        allowed_tool_names=allowed_tool_names,
        blocked_tool_names=blocked_tool_names,
    )
    return TaskDAGLocalStartResult(
        plan_id=bridge_result.plan_id,
        selected_task_id=selected_task_id,
        selection_reason=reason,
        previous_status=bridge_result.previous_status,
        next_status=bridge_result.next_status,
        solve_node_id=bridge_result.solve_node_id,
        task_brief_id=bridge_result.task_brief_id,
        receipt_id=bridge_result.receipt_id,
        started=True,
        warnings=list(bridge_result.warnings),
    )


def apply_local_dag_task_receipt(
    state: CTFState,
    task_id: str,
    receipt: SolveNodeReceipt | dict[str, Any],
    *,
    plan: TaskDAGPlan | dict[str, Any] | None = None,
) -> TaskDAGLocalReceiptResult:
    active_plan = state.get_task_dag_plan() if plan is None else plan
    bridge_result = record_task_dag_p3_receipt(
        state,
        active_plan,
        task_id,
        receipt,
    )
    return TaskDAGLocalReceiptResult(
        plan_id=bridge_result.plan_id,
        task_id=bridge_result.task_id,
        previous_status=bridge_result.previous_status,
        next_status=bridge_result.next_status,
        solve_node_id=bridge_result.solve_node_id,
        task_brief_id=bridge_result.task_brief_id,
        receipt_id=bridge_result.receipt_id,
        applied=True,
        warnings=list(bridge_result.warnings),
    )


def _selection_warnings(selection: dict[str, Any]) -> list[str]:
    count = int(selection.get("restoreWarningCount") or 0)
    if count <= 0:
        return []
    return [f"restoreWarningCount={count}"]
