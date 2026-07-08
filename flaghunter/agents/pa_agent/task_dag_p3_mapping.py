"""Pure TaskDAGPlan <-> P3 SolveNode/TaskBrief/Receipt mapping helpers."""

from __future__ import annotations

from typing import Any

from .solve_node import (
    SolveNode,
    SolveNodeKind,
    SolveNodeReceipt,
    SolveNodeStatus,
    TaskBrief,
    solve_node_receipt_from_dict,
    solve_node_receipt_to_dict,
)
from .task_dag_plan import (
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
    TaskDAGTransitionError,
    _coerce_str_list,
    _preview,
    mark_task_finished,
    task_dag_node_from_dict,
    task_dag_node_to_dict,
    task_dag_plan_from_dict,
    task_dag_plan_to_dict,
)
from .task_dag_shared import (
    _dedupe,
)


class TaskDAGMappingError(TaskDAGTransitionError):
    pass


def build_task_brief_for_dag_node(
    plan: TaskDAGPlan | dict[str, Any],
    task_id: str,
    *,
    run_id: str = "",
    worker_type: str = "single_agent_task_dag",
    context_summary: str = "",
    allowed_tool_names: list[str] | None = None,
    blocked_tool_names: list[str] | None = None,
) -> TaskBrief:
    normalized, node = _task_from_plan(plan, task_id)
    metadata = _mapping_metadata(normalized, node)
    objective = _preview(node.goal or node.title or node.kind, limit=160)
    context_parts = [
        _preview(context_summary, limit=160),
        _preview(node.title, limit=160),
        f"task_kind={_preview(node.kind, limit=80)}",
    ]
    constraints = _safe_list(_metadata_list(node, "constraints"))
    allowed = _safe_list(allowed_tool_names) + _safe_list(
        _metadata_list(node, "allowed_tool_names")
    )
    blocked = _safe_list(blocked_tool_names) + _safe_list(
        _metadata_list(node, "blocked_tool_names")
    )
    return TaskBrief(
        run_id=_preview(run_id, limit=160),
        worker_type=_preview(worker_type, limit=80) or "single_agent_task_dag",
        objective=objective,
        context_summary=" ".join(part for part in context_parts if part).strip(),
        constraints=_dedupe(constraints),
        allowed_tool_names=_dedupe(allowed),
        blocked_tool_names=_dedupe(blocked),
        claim_ids=list(node.claim_ids),
        trace_ids=list(node.trace_ids),
        metadata=metadata,
    )


def build_solve_node_for_dag_node(
    plan: TaskDAGPlan | dict[str, Any],
    task_id: str,
    *,
    run_id: str = "",
    parent_id: str = "",
) -> SolveNode:
    normalized, node = _task_from_plan(plan, task_id)
    metadata = _mapping_metadata(normalized, node)
    if node.status is TaskDAGStatus.INSUFFICIENT:
        metadata["dag_status"] = TaskDAGStatus.INSUFFICIENT.value
    return SolveNode(
        run_id=_preview(run_id, limit=160),
        parent_id=_preview(parent_id, limit=160),
        kind=_solve_node_kind(node.kind),
        status=_solve_node_status(node.status),
        title=_preview(node.title, limit=160),
        goal=_preview(node.goal, limit=160),
        summary=_preview(_metadata_value(node, "summary"), limit=160),
        claim_ids=list(node.claim_ids),
        trace_ids=list(node.trace_ids),
        receipt_ids=list(node.receipt_ids),
        metadata=metadata,
    )


def link_solve_node_to_task(
    plan: TaskDAGPlan | dict[str, Any],
    task_id: str,
    *,
    solve_node_id: str = "",
    task_brief_id: str = "",
) -> TaskDAGPlan:
    normalized, node = _task_from_plan(plan, task_id)
    normalized_solve_node_id = str(solve_node_id or "").strip()
    normalized_task_brief_id = str(task_brief_id or "").strip()
    if not normalized_solve_node_id and not normalized_task_brief_id:
        raise TaskDAGMappingError("at least one P3 ref is required")
    if (
        normalized_solve_node_id
        and node.solve_node_id
        and node.solve_node_id != normalized_solve_node_id
    ):
        raise TaskDAGMappingError("conflicting solve_node_id")
    if (
        normalized_task_brief_id
        and node.task_brief_id
        and node.task_brief_id != normalized_task_brief_id
    ):
        raise TaskDAGMappingError("conflicting task_brief_id")
    replacement = task_dag_node_from_dict(task_dag_node_to_dict(node))
    if normalized_solve_node_id:
        replacement.solve_node_id = normalized_solve_node_id
    if normalized_task_brief_id:
        replacement.task_brief_id = normalized_task_brief_id
    normalized.add_node(replacement)
    return normalized


def apply_solve_node_receipt_to_task(
    plan: TaskDAGPlan | dict[str, Any],
    task_id: str,
    receipt: SolveNodeReceipt | dict[str, Any],
) -> TaskDAGPlan:
    normalized, node = _task_from_plan(plan, task_id)
    normalized_receipt = _coerce_receipt(receipt)
    if normalized_receipt.node_id and node.solve_node_id and node.solve_node_id != normalized_receipt.node_id:
        raise TaskDAGMappingError("conflicting solve_node_id")
    status = _dag_status_from_receipt(normalized_receipt)
    try:
        return mark_task_finished(
            normalized,
            node.id,
            status=status,
            receipt_id=normalized_receipt.id,
            solve_node_id=normalized_receipt.node_id,
            trace_ids=list(normalized_receipt.trace_ids),
            claim_ids=list(normalized_receipt.claim_ids),
        )
    except TaskDAGTransitionError as exc:
        raise TaskDAGMappingError(str(exc)) from exc


def _task_from_plan(
    plan: TaskDAGPlan | dict[str, Any],
    task_id: str,
) -> tuple[TaskDAGPlan, TaskDAGNode]:
    normalized = task_dag_plan_from_dict(task_dag_plan_to_dict(plan))
    normalized_task_id = str(task_id or "").strip()
    node = normalized.get_node(normalized_task_id)
    if node is None:
        raise TaskDAGMappingError(f"unknown task: {normalized_task_id}")
    return normalized, node


def _mapping_metadata(plan: TaskDAGPlan, node: TaskDAGNode) -> dict[str, str]:
    return {
        "task_dag_plan_id": _preview(plan.id, limit=160),
        "task_dag_task_id": _preview(node.id, limit=160),
        "task_kind": _preview(node.kind, limit=160),
        "source_channel": "task_dag_plan",
    }


def _solve_node_kind(value: str) -> SolveNodeKind:
    normalized = str(value or "").strip().lower()
    try:
        return SolveNodeKind(normalized)
    except ValueError:
        return SolveNodeKind.GENERIC


def _solve_node_status(status: TaskDAGStatus) -> SolveNodeStatus:
    mapping = {
        TaskDAGStatus.PROPOSED: SolveNodeStatus.PLANNED,
        TaskDAGStatus.READY: SolveNodeStatus.PLANNED,
        TaskDAGStatus.RUNNING: SolveNodeStatus.RUNNING,
        TaskDAGStatus.SUCCEEDED: SolveNodeStatus.COMPLETED,
        TaskDAGStatus.FAILED: SolveNodeStatus.FAILED,
        TaskDAGStatus.INSUFFICIENT: SolveNodeStatus.FAILED,
        TaskDAGStatus.SKIPPED: SolveNodeStatus.SKIPPED,
        TaskDAGStatus.BLOCKED: SolveNodeStatus.BLOCKED,
    }
    return mapping[status]


def _dag_status_from_receipt(receipt: SolveNodeReceipt) -> str:
    mapping = {
        "completed": TaskDAGStatus.SUCCEEDED.value,
        "failed": TaskDAGStatus.FAILED.value,
        "partial": TaskDAGStatus.INSUFFICIENT.value,
        "blocked": TaskDAGStatus.BLOCKED.value,
        "skipped": TaskDAGStatus.SKIPPED.value,
    }
    return mapping.get(receipt.status, TaskDAGStatus.INSUFFICIENT.value)


def _coerce_receipt(receipt: SolveNodeReceipt | dict[str, Any]) -> SolveNodeReceipt:
    try:
        return (
            receipt
            if isinstance(receipt, SolveNodeReceipt)
            else solve_node_receipt_from_dict(solve_node_receipt_to_dict(receipt))
        )
    except Exception as exc:
        raise TaskDAGMappingError("invalid solve node receipt") from exc


def _metadata_list(node: TaskDAGNode, key: str) -> list[str]:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    return _coerce_str_list(metadata.get(key))


def _metadata_value(node: TaskDAGNode, key: str) -> str:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    return str(metadata.get(key) or "")


def _safe_list(values: Any) -> list[str]:
    return [_preview(item, limit=160) for item in _coerce_str_list(values)]

