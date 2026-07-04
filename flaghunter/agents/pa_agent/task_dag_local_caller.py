"""Manual/local TaskDAG caller facade over the no-execute shim."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ctf_state import CTFState
from .solve_node import SolveNodeReceipt
from .task_dag_local_shim import (
    apply_local_dag_task_receipt,
    start_next_ready_task_for_local_dag,
)
from .task_dag_plan import TaskDAGPlan


TASK_DAG_LOCAL_CALLER_SCHEMA_VERSION = "p4.task_dag_local_caller.v1"


@dataclass
class TaskDAGLocalCallerResult:
    schema_version: str = TASK_DAG_LOCAL_CALLER_SCHEMA_VERSION
    action: str = ""
    ok: bool = False
    plan_id: str = ""
    task_id: str = ""
    selected_task_id: str = ""
    selection_reason: str = ""
    previous_status: str = ""
    next_status: str = ""
    solve_node_id: str = ""
    task_brief_id: str = ""
    receipt_id: str = ""
    started: bool = False
    applied: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "action": self.action,
            "ok": bool(self.ok),
            "planId": self.plan_id,
            "taskId": self.task_id,
            "selectedTaskId": self.selected_task_id,
            "selectionReason": self.selection_reason,
            "previousStatus": self.previous_status,
            "nextStatus": self.next_status,
            "solveNodeId": self.solve_node_id,
            "taskBriefId": self.task_brief_id,
            "receiptId": self.receipt_id,
            "started": bool(self.started),
            "applied": bool(self.applied),
            "warnings": list(self.warnings),
        }


def local_dag_start_next(
    state: CTFState,
    *,
    plan: TaskDAGPlan | dict[str, Any] | None = None,
    run_id: str = "",
    context_summary: str = "",
    allowed_tool_names: list[str] | None = None,
    blocked_tool_names: list[str] | None = None,
) -> TaskDAGLocalCallerResult:
    result = start_next_ready_task_for_local_dag(
        state,
        plan,
        run_id=run_id,
        context_summary=context_summary,
        allowed_tool_names=allowed_tool_names,
        blocked_tool_names=blocked_tool_names,
    )
    return TaskDAGLocalCallerResult(
        action="start_next_ready",
        ok=bool(result.started),
        plan_id=result.plan_id,
        task_id=result.selected_task_id,
        selected_task_id=result.selected_task_id,
        selection_reason=result.selection_reason,
        previous_status=result.previous_status,
        next_status=result.next_status,
        solve_node_id=result.solve_node_id,
        task_brief_id=result.task_brief_id,
        receipt_id=result.receipt_id,
        started=bool(result.started),
        applied=False,
        warnings=list(result.warnings),
    )


def local_dag_apply_receipt(
    state: CTFState,
    task_id: str,
    receipt: SolveNodeReceipt | dict[str, Any],
    *,
    plan: TaskDAGPlan | dict[str, Any] | None = None,
) -> TaskDAGLocalCallerResult:
    result = apply_local_dag_task_receipt(
        state,
        task_id,
        receipt,
        plan=plan,
    )
    return TaskDAGLocalCallerResult(
        action="apply_receipt",
        ok=bool(result.applied),
        plan_id=result.plan_id,
        task_id=result.task_id,
        selected_task_id="",
        selection_reason=result.selection_reason,
        previous_status=result.previous_status,
        next_status=result.next_status,
        solve_node_id=result.solve_node_id,
        task_brief_id=result.task_brief_id,
        receipt_id=result.receipt_id,
        started=False,
        applied=bool(result.applied),
        warnings=list(result.warnings),
    )
