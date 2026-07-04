from __future__ import annotations

import json

import pytest

from flaghunter.agents.base_agent import AgentMessage
from flaghunter.agents.pa_agent.context_assembler import ContextAssembler
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.solve_node import SolveNodeReceipt
from flaghunter.agents.pa_agent.task_dag_local_caller import (
    TASK_DAG_LOCAL_CALLER_SCHEMA_VERSION,
    local_dag_apply_receipt,
    local_dag_start_next,
)
from flaghunter.agents.pa_agent.task_dag_p3_bridge import TaskDAGP3BridgeError
from flaghunter.agents.pa_agent.task_dag_plan import (
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
    task_dag_plan_from_dict,
    task_dag_plan_to_dict,
)
from flaghunter.harness.checkpoint_store import CheckpointStore


class _StubAgent:
    def __init__(self, *, project_root, run_id: str):
        self.target = "http://ctf.local"
        self.rag_engine = None
        self.run_id = run_id
        self.project_root = project_root
        self.conversation_history = [
            AgentMessage(role="user", content="continue from DAG local caller")
        ]


def _state_snapshot(state: CTFState) -> dict[str, object]:
    return {
        "plan": task_dag_plan_to_dict(state.get_task_dag_plan()),
        "solve_graph": state.solve_node_graph.to_dict(),
        "briefs": {
            key: value.to_dict()
            for key, value in sorted(state.task_briefs_by_id.items())
        },
        "receipts": {
            key: value.to_dict()
            for key, value in sorted(state.solve_node_receipts_by_id.items())
        },
    }


def _ready_plan() -> TaskDAGPlan:
    plan = TaskDAGPlan(id="plan-caller")
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            kind="exploit",
            title="Exploit upload",
            goal="Run upload primitive",
            status=TaskDAGStatus.READY,
            claim_ids=["claim-a"],
            trace_ids=["trace-a"],
        )
    )
    return plan


def test_p4b4j_start_no_plan_or_empty_plan_returns_compact_noop_without_mutation() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    before = _state_snapshot(state)

    result = local_dag_start_next(state)
    explicit_empty = local_dag_start_next(state, plan=TaskDAGPlan(id="empty-plan"))

    assert result.schema_version == TASK_DAG_LOCAL_CALLER_SCHEMA_VERSION
    assert result.action == "start_next_ready"
    assert result.ok is False
    assert result.started is False
    assert result.applied is False
    assert result.selection_reason == "empty_plan"
    assert result.selected_task_id == ""
    assert explicit_empty.ok is False
    assert explicit_empty.selection_reason == "empty_plan"
    assert _state_snapshot(state) == before


def test_p4b4j_start_restore_warning_plan_returns_compact_noop_without_mutation() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = _ready_plan()
    plan.restore_warnings.append("bad edge")
    before = _state_snapshot(state)

    result = local_dag_start_next(state, plan=plan)

    assert result.ok is False
    assert result.started is False
    assert result.selection_reason == "restore_warnings_present"
    assert result.selected_task_id == ""
    assert _state_snapshot(state) == before


def test_p4b4j_start_running_task_present_returns_noop_without_new_p3_objects() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = TaskDAGPlan(id="plan-running")
    plan.add_node(TaskDAGNode(id="task-running", status="running"))
    plan.add_node(TaskDAGNode(id="task-ready", status="ready"))
    before = _state_snapshot(state)

    result = local_dag_start_next(state, plan=plan)

    assert result.ok is False
    assert result.started is False
    assert result.selection_reason == "running_task_present"
    assert result.selected_task_id == ""
    assert _state_snapshot(state) == before


def test_p4b4j_start_ready_task_delegates_through_shim_and_creates_no_receipt() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")

    result = local_dag_start_next(
        state,
        plan=_ready_plan(),
        run_id="run-caller",
        context_summary="compact context",
        allowed_tool_names=["browser"],
        blocked_tool_names=["sqlmap"],
    )
    node = state.get_task_dag_plan().get_node("task-a")

    assert result.ok is True
    assert result.started is True
    assert result.applied is False
    assert result.selection_reason == "selected"
    assert result.selected_task_id == "task-a"
    assert result.task_id == "task-a"
    assert result.previous_status == "ready"
    assert result.next_status == "running"
    assert result.solve_node_id
    assert result.task_brief_id
    assert result.receipt_id == ""
    assert node.status is TaskDAGStatus.RUNNING
    assert node.solve_node_id == result.solve_node_id
    assert node.task_brief_id == result.task_brief_id
    assert state.get_solve_node(result.solve_node_id) is not None
    assert state.get_task_brief(result.task_brief_id) is not None
    assert state.solve_node_receipts_by_id == {}


def test_p4b4j_start_selects_first_ready_task_deterministically_after_round_trip() -> None:
    plan = TaskDAGPlan(id="plan-deterministic")
    plan.add_node(TaskDAGNode(id="task-first", status="ready", created_at=3.0))
    plan.add_node(TaskDAGNode(id="task-second", status="ready", created_at=1.0))
    restored = task_dag_plan_from_dict(task_dag_plan_to_dict(plan))

    first = local_dag_start_next(
        CTFState(target="http://ctf.local", goal="get flag"),
        plan=plan,
    )
    second = local_dag_start_next(
        CTFState(target="http://ctf.local", goal="get flag"),
        plan=restored,
    )

    assert first.ok is True
    assert second.ok is True
    assert first.selected_task_id == "task-first"
    assert second.selected_task_id == "task-first"


def test_p4b4j_start_result_to_dict_is_compact_and_redacted() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = TaskDAGPlan(id="plan-compact", metadata={"token": "plan-token"})
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            title="HTTP/1.1 200 OK\n<html>secret=body-secret</html>",
            goal="Use password=goal-password",
            status="ready",
        )
    )

    result = local_dag_start_next(
        state,
        plan=plan,
        context_summary="Authorization: Bearer context-auth",
    )
    text = repr(result.to_dict())

    assert result.ok is True
    for allowed in ("schemaVersion", "action", "selectedTaskId", "solveNodeId"):
        assert allowed in text
    for forbidden in (
        "nodes",
        "briefs",
        "receipts",
        "HTTP/1.1 200 OK",
        "<html",
        "body-secret",
        "goal-password",
        "plan-token",
        "context-auth",
    ):
        assert forbidden not in text


def test_p4b4j_apply_external_completed_receipt_updates_dag_via_shim() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    start = local_dag_start_next(state, plan=_ready_plan())

    result = local_dag_apply_receipt(
        state,
        "task-a",
        SolveNodeReceipt(
            id="receipt-completed",
            node_id=start.solve_node_id,
            input_brief_id=start.task_brief_id,
            status="completed",
            trace_ids=["trace-receipt"],
            claim_ids=["claim-receipt"],
        ),
    )
    node = state.get_task_dag_plan().get_node("task-a")

    assert result.schema_version == TASK_DAG_LOCAL_CALLER_SCHEMA_VERSION
    assert result.action == "apply_receipt"
    assert result.ok is True
    assert result.started is False
    assert result.applied is True
    assert result.task_id == "task-a"
    assert result.receipt_id == "receipt-completed"
    assert result.previous_status == "running"
    assert result.next_status == "succeeded"
    assert node.status is TaskDAGStatus.SUCCEEDED
    assert node.receipt_ids == ["receipt-completed"]
    assert "trace-receipt" in node.trace_ids
    assert "claim-receipt" in node.claim_ids


@pytest.mark.parametrize(
    ("receipt_status", "expected_status"),
    [
        ("failed", TaskDAGStatus.FAILED),
        ("partial", TaskDAGStatus.INSUFFICIENT),
    ],
)
def test_p4b4j_failed_or_partial_receipts_do_not_emit_recovery_or_proof_fields(
    receipt_status: str,
    expected_status: TaskDAGStatus,
) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    start = local_dag_start_next(state, plan=_ready_plan())

    result = local_dag_apply_receipt(
        state,
        "task-a",
        SolveNodeReceipt(
            id=f"receipt-{receipt_status}",
            node_id=start.solve_node_id,
            status=receipt_status,
        ),
    )
    text = repr(
        {
            "result": result.to_dict(),
            "plan": task_dag_plan_to_dict(state.get_task_dag_plan()),
        }
    )

    assert result.ok is True
    assert result.applied is True
    assert result.next_status == expected_status.value
    assert state.get_task_dag_plan().get_node("task-a").status is expected_status
    for forbidden in (
        "verifiedFlags",
        "verification_decision",
        "recovery",
        "dispatcher",
        "verifierProof",
        'level="verified"',
        "level='verified'",
    ):
        assert forbidden not in text


def test_p4b4j_malformed_or_conflicting_receipt_rejects_without_state_mutation() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    start = local_dag_start_next(state, plan=_ready_plan())
    before = _state_snapshot(state)

    with pytest.raises(TaskDAGP3BridgeError, match="conflicting solve_node_id"):
        local_dag_apply_receipt(
            state,
            "task-a",
            SolveNodeReceipt(id="receipt-conflict", node_id="other-node"),
        )
    with pytest.raises(TaskDAGP3BridgeError, match="receipt id is required"):
        local_dag_apply_receipt(
            state,
            "task-a",
            {"id": "", "node_id": start.solve_node_id, "status": "completed"},
        )

    assert _state_snapshot(state) == before


def test_p4b4j_session_context_and_prompt_surfaces_remain_compact(tmp_path) -> None:
    run_id = "run-p4b4j-compact"
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = TaskDAGPlan(id="plan-prompt", metadata={"token": "plan-token"})
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            kind="exploit",
            title="HTTP/1.1 200 OK\n<html>secret=body-secret</html>",
            goal="Use password=goal-password",
            status="ready",
            metadata={"note": json.dumps({"session": "metadata-session"})},
        )
    )
    start = local_dag_start_next(
        state,
        plan=plan,
        run_id=run_id,
        context_summary="Authorization: Bearer context-auth",
    )
    local_dag_apply_receipt(
        state,
        "task-a",
        SolveNodeReceipt(
            id="receipt-a",
            node_id=start.solve_node_id,
            input_brief_id=start.task_brief_id,
            status="completed",
            output_summary="token=receipt-token",
        ),
    )
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    prompt_text = ContextAssembler(
        _StubAgent(project_root=tmp_path, run_id=run_id)
    ).assemble()

    assert "solve_nodes=1" in prompt_text
    assert "task_briefs=1" in prompt_text
    assert "node_receipts=1" in prompt_text
    assert "task_dag_nodes=1" in prompt_text
    assert "task_dag_statuses=succeeded:1" in prompt_text
    for forbidden in (
        "taskDagPlanReadback",
        "task_dag_plan",
        "task-a",
        "HTTP/1.1 200 OK",
        "<html",
        "body-secret",
        "goal-password",
        "plan-token",
        "context-auth",
        "metadata-session",
        "receipt-token",
    ):
        assert forbidden not in prompt_text
