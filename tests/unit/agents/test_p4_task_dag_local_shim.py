from __future__ import annotations

import json

import pytest

from flaghunter.agents.base_agent import AgentMessage
from flaghunter.agents.pa_agent.context_assembler import ContextAssembler
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.solve_node import SolveNodeReceipt
from flaghunter.agents.pa_agent.task_dag_local_shim import (
    TASK_DAG_LOCAL_RECEIPT_SCHEMA_VERSION,
    TASK_DAG_LOCAL_START_SCHEMA_VERSION,
    apply_local_dag_task_receipt,
    start_next_ready_task_for_local_dag,
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
            AgentMessage(role="user", content="continue from DAG local shim")
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
    plan = TaskDAGPlan(id="plan-local")
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


def test_p4b4h_start_no_plan_or_empty_plan_returns_noop_without_state_mutation() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    before = _state_snapshot(state)

    result = start_next_ready_task_for_local_dag(state)
    explicit_empty = start_next_ready_task_for_local_dag(
        state,
        TaskDAGPlan(id="empty-plan"),
    )

    assert result.schema_version == TASK_DAG_LOCAL_START_SCHEMA_VERSION
    assert result.action == "start_next_ready"
    assert result.started is False
    assert result.selection_reason == "empty_plan"
    assert result.selected_task_id == ""
    assert explicit_empty.started is False
    assert explicit_empty.selection_reason == "empty_plan"
    assert _state_snapshot(state) == before


def test_p4b4h_start_restore_warning_plan_returns_noop_without_bridge_mutation() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = _ready_plan()
    plan.restore_warnings.append("bad edge")
    before = _state_snapshot(state)

    result = start_next_ready_task_for_local_dag(state, plan)

    assert result.started is False
    assert result.selection_reason == "restore_warnings_present"
    assert result.selected_task_id == ""
    assert _state_snapshot(state) == before


def test_p4b4h_start_running_task_present_returns_noop_without_new_p3_objects() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = TaskDAGPlan(id="plan-running")
    plan.add_node(TaskDAGNode(id="task-running", status="running"))
    plan.add_node(TaskDAGNode(id="task-ready", status="ready"))
    before = _state_snapshot(state)

    result = start_next_ready_task_for_local_dag(state, plan)

    assert result.started is False
    assert result.selection_reason == "running_task_present"
    assert result.selected_task_id == ""
    assert _state_snapshot(state) == before


def test_p4b4h_start_no_ready_task_returns_noop() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = TaskDAGPlan(id="plan-no-ready")
    plan.add_node(TaskDAGNode(id="task-a", status="proposed"))
    before = _state_snapshot(state)

    result = start_next_ready_task_for_local_dag(state, plan)

    assert result.started is False
    assert result.selection_reason == "no_ready_tasks"
    assert result.selected_task_id == ""
    assert _state_snapshot(state) == before


def test_p4b4h_start_blocked_dependencies_returns_noop() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = TaskDAGPlan(id="plan-blocked")
    plan.add_node(TaskDAGNode(id="dep", status="failed"))
    plan.add_node(TaskDAGNode(id="task-a", status="ready", depends_on=["dep"]))
    before = _state_snapshot(state)

    result = start_next_ready_task_for_local_dag(state, plan)

    assert result.started is False
    assert result.selection_reason == "blocked_by_dependencies"
    assert result.selected_task_id == ""
    assert _state_snapshot(state) == before


def test_p4b4h_start_selects_first_ready_task_deterministically_after_round_trip() -> None:
    plan = TaskDAGPlan(id="plan-deterministic")
    plan.add_node(TaskDAGNode(id="task-first", status="ready", created_at=3.0))
    plan.add_node(TaskDAGNode(id="task-second", status="ready", created_at=1.0))
    restored = task_dag_plan_from_dict(task_dag_plan_to_dict(plan))

    first_result = start_next_ready_task_for_local_dag(
        CTFState(target="http://ctf.local", goal="get flag"),
        plan,
    )
    restored_result = start_next_ready_task_for_local_dag(
        CTFState(target="http://ctf.local", goal="get flag"),
        restored,
    )

    assert first_result.started is True
    assert restored_result.started is True
    assert first_result.selected_task_id == "task-first"
    assert restored_result.selected_task_id == "task-first"


def test_p4b4h_start_ready_task_records_p3_refs_marks_running_and_does_not_create_receipt() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")

    result = start_next_ready_task_for_local_dag(
        state,
        _ready_plan(),
        run_id="run-local",
        context_summary="compact context",
        allowed_tool_names=["browser"],
        blocked_tool_names=["sqlmap"],
    )
    node = state.get_task_dag_plan().get_node("task-a")

    assert result.schema_version == TASK_DAG_LOCAL_START_SCHEMA_VERSION
    assert result.started is True
    assert result.selection_reason == "selected"
    assert result.selected_task_id == "task-a"
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


def test_p4b4h_start_result_serialization_is_compact_and_redacted() -> None:
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

    result = start_next_ready_task_for_local_dag(
        state,
        plan,
        context_summary="Authorization: Bearer context-auth",
    )
    text = repr(result.to_dict())

    assert result.started is True
    for allowed in ("schemaVersion", "selectedTaskId", "solveNodeId", "taskBriefId"):
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


def test_p4b4h_apply_external_completed_receipt_updates_dag_through_bridge() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    start = start_next_ready_task_for_local_dag(state, _ready_plan())

    result = apply_local_dag_task_receipt(
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

    assert result.schema_version == TASK_DAG_LOCAL_RECEIPT_SCHEMA_VERSION
    assert result.action == "apply_receipt"
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
def test_p4b4h_failed_or_partial_receipts_update_state_without_proof_fields(
    receipt_status: str,
    expected_status: TaskDAGStatus,
) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    start = start_next_ready_task_for_local_dag(state, _ready_plan())

    result = apply_local_dag_task_receipt(
        state,
        "task-a",
        SolveNodeReceipt(
            id=f"receipt-{receipt_status}",
            node_id=start.solve_node_id,
            status=receipt_status,
        ),
    )
    text = repr({"result": result.to_dict(), "plan": task_dag_plan_to_dict(state.get_task_dag_plan())})

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


def test_p4b4h_apply_malformed_or_conflicting_receipt_rejects_without_state_mutation() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    start = start_next_ready_task_for_local_dag(state, _ready_plan())
    before = _state_snapshot(state)

    with pytest.raises(TaskDAGP3BridgeError, match="conflicting solve_node_id"):
        apply_local_dag_task_receipt(
            state,
            "task-a",
            SolveNodeReceipt(id="receipt-conflict", node_id="other-node"),
        )
    with pytest.raises(TaskDAGP3BridgeError, match="receipt id is required"):
        apply_local_dag_task_receipt(
            state,
            "task-a",
            {"id": "", "node_id": start.solve_node_id, "status": "completed"},
        )

    assert _state_snapshot(state) == before


def test_p4b4h_readback_session_and_prompt_surfaces_remain_compact(tmp_path) -> None:
    run_id = "run-p4b4h-compact"
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
    start = start_next_ready_task_for_local_dag(
        state,
        plan,
        run_id=run_id,
        context_summary="Authorization: Bearer context-auth",
    )
    apply_local_dag_task_receipt(
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
