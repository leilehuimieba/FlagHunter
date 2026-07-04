from __future__ import annotations

import pytest

from flaghunter.agents.base_agent import AgentMessage
from flaghunter.agents.pa_agent.context_assembler import ContextAssembler
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.p3_solve_readback import build_p3_solve_readback
from flaghunter.agents.pa_agent.task_dag_dry_result_adapter import (
    TaskDAGDryResultAdapterError,
    build_task_dag_outcome_from_dry_result,
)
from flaghunter.agents.pa_agent.task_dag_local_caller import (
    local_dag_apply_receipt,
    local_dag_start_next,
)
from flaghunter.agents.pa_agent.task_dag_plan import (
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
    select_next_ready_task,
    task_dag_plan_to_dict,
)
from flaghunter.agents.pa_agent.task_dag_receipt_factory import (
    build_local_task_dag_receipt,
)
from flaghunter.harness.checkpoint_store import CheckpointStore


class _StubAgent:
    def __init__(self, *, project_root, run_id: str):
        self.target = "http://ctf.local"
        self.rag_engine = None
        self.run_id = run_id
        self.project_root = project_root
        self.conversation_history = [
            AgentMessage(role="user", content="continue from local dry E2E")
        ]


def _chain_plan() -> TaskDAGPlan:
    plan = TaskDAGPlan(id="plan-dry-e2e", metadata={"token": "plan-token"})
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            kind="exploit",
            title="HTTP/1.1 200 OK\n<html>secret=task-a-body</html>",
            goal="Use password=task-a-password",
            status=TaskDAGStatus.READY,
            trace_ids=["trace-a"],
            claim_ids=["claim-a"],
            metadata={"session": "task-a-session"},
        )
    )
    plan.add_node(
        TaskDAGNode(
            id="task-b",
            kind="exploit",
            title="Follow-up exploit",
            goal="Use token=task-b-token",
            status=TaskDAGStatus.READY,
            depends_on=["task-a"],
        )
    )
    return plan


def _single_ready_plan(*, task_id: str = "task-a") -> TaskDAGPlan:
    plan = TaskDAGPlan(id=f"plan-{task_id}")
    plan.add_node(
        TaskDAGNode(
            id=task_id,
            kind="exploit",
            title="Dry exploit",
            goal="Run bounded dry fixture",
            status=TaskDAGStatus.READY,
        )
    )
    return plan


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


def _apply_dry_result(
    state: CTFState,
    *,
    task_id: str,
    status: str,
    compact_output: str = "",
    compact_error: str = "",
    exit_code: int | None = None,
    duration_ms: int | None = None,
):
    start = local_dag_start_next(state)
    assert start.ok is True
    assert start.selected_task_id == task_id
    outcome = build_task_dag_outcome_from_dry_result(
        {
            "task_id": task_id,
            "solve_node_id": start.solve_node_id,
            "task_brief_id": start.task_brief_id,
            "status": status,
            "compact_output": compact_output,
            "compact_error": compact_error,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "trace_ids": [f"trace-{task_id}-receipt"],
            "claim_ids": [f"claim-{task_id}-receipt"],
            "metadata": {"outcome_kind": "dry token=metadata-token"},
        }
    )
    receipt = build_local_task_dag_receipt(outcome)
    result = local_dag_apply_receipt(state, task_id, receipt)
    return start, outcome, receipt, result


def test_p4b4r_completed_local_dry_chain_records_p3_receipt_and_compact_readback() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.set_task_dag_plan(_single_ready_plan())

    start, outcome, receipt, result = _apply_dry_result(
        state,
        task_id="task-a",
        status="success",
        compact_output="completed compactly",
        exit_code=0,
        duration_ms=123,
    )
    node = state.get_task_dag_plan().get_node("task-a")
    p3_readback = build_p3_solve_readback(state)
    serialized = repr(
        {
            "plan": task_dag_plan_to_dict(state.get_task_dag_plan()),
            "p3": p3_readback,
            "outcome": outcome,
            "receipt": receipt.to_dict(),
            "result": result.to_dict(),
        }
    )

    assert start.previous_status == "ready"
    assert result.ok is True
    assert result.next_status == "succeeded"
    assert node.status is TaskDAGStatus.SUCCEEDED
    assert receipt.id in node.receipt_ids
    assert state.get_solve_node(start.solve_node_id) is not None
    assert state.get_task_brief(start.task_brief_id) is not None
    assert state.get_solve_node_receipt(receipt.id) is not None
    assert outcome.metadata["exit_code"] == 0
    assert outcome.duration_ms == 123
    assert receipt.duration_ms == 123
    assert p3_readback["summary"]["hasSolveNodeReceipts"] is True
    for forbidden in (
        "verification" + "_decision",
        "verified" + "_flags",
        "verifierProof",
        'level=' + '"verified"',
        "level=" + "'verified'",
        "upgrade_claim_to" + "_verified",
        "append_verification" + "_record",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("dry_status", "exit_code", "expected_status"),
    [
        ("error", 7, TaskDAGStatus.FAILED),
        ("timeout", 124, TaskDAGStatus.INSUFFICIENT),
    ],
)
def test_p4b4r_failed_and_timeout_dry_chains_update_dag_without_proof(
    dry_status: str,
    exit_code: int,
    expected_status: TaskDAGStatus,
) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.set_task_dag_plan(_single_ready_plan())

    _, outcome, receipt, result = _apply_dry_result(
        state,
        task_id="task-a",
        status=dry_status,
        compact_error="failed compactly password=error-password",
        exit_code=exit_code,
    )
    serialized = repr(
        {
            "plan": task_dag_plan_to_dict(state.get_task_dag_plan()),
            "outcome": outcome,
            "receipt": receipt.to_dict(),
            "result": result.to_dict(),
        }
    )

    assert state.get_task_dag_plan().get_node("task-a").status is expected_status
    assert outcome.metadata["exit_code"] == exit_code
    assert result.next_status == expected_status.value
    for forbidden in (
        "verification" + "_decision",
        "verified" + "_flags",
        "verifierProof",
        "error-password",
        "recovery",
    ):
        assert forbidden not in serialized


def test_p4b4r_dependency_progression_is_manual_and_no_scheduler_loop() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.set_task_dag_plan(_chain_plan())

    initial_selection = select_next_ready_task(state.get_task_dag_plan())
    first_start = local_dag_start_next(state)
    b_while_a_running = local_dag_start_next(state)

    assert initial_selection["selectedTaskId"] == "task-a"
    assert initial_selection["blockedTaskIds"] == ["task-b"]
    assert first_start.selected_task_id == "task-a"
    assert b_while_a_running.ok is False
    assert b_while_a_running.selection_reason == "running_task_present"

    outcome = build_task_dag_outcome_from_dry_result(
        {
            "task_id": "task-a",
            "solve_node_id": first_start.solve_node_id,
            "task_brief_id": first_start.task_brief_id,
            "status": "success",
            "compact_output": "task a done",
        }
    )
    receipt = build_local_task_dag_receipt(outcome)
    local_dag_apply_receipt(state, "task-a", receipt)
    second_start = local_dag_start_next(state)

    assert state.get_task_dag_plan().get_node("task-a").status is TaskDAGStatus.SUCCEEDED
    assert second_start.ok is True
    assert second_start.selected_task_id == "task-b"
    assert state.get_task_dag_plan().get_node("task-b").status is TaskDAGStatus.RUNNING
    assert len(state.task_briefs_by_id) == 2
    assert len(state.solve_node_graph.nodes_by_id) == 2


def test_p4b4r_snapshot_restore_checkpoint_and_prompt_context_stay_compact(tmp_path) -> None:
    run_id = "run-p4b4r-dry-e2e"
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.set_task_dag_plan(_chain_plan())
    start = local_dag_start_next(
        state,
        run_id=run_id,
        context_summary="Authorization: Bearer context-auth",
    )
    outcome = build_task_dag_outcome_from_dry_result(
        {
            "task_id": "task-a",
            "solve_node_id": start.solve_node_id,
            "task_brief_id": start.task_brief_id,
            "run_id": run_id,
            "status": "success",
            "compact_output": "Authorization: Bearer dry-auth token=dry-token",
            "exit_code": 0,
            "duration_ms": 321,
            "metadata": {"outcome_kind": "dry token=metadata-token"},
        }
    )
    receipt = build_local_task_dag_receipt(outcome)
    local_dag_apply_receipt(state, "task-a", receipt)
    restored = CTFState.from_snapshot(state.to_snapshot())
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="dry_e2e_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    prompt_text = ContextAssembler(
        _StubAgent(project_root=tmp_path, run_id=run_id)
    ).assemble()

    assert restored.get_task_dag_plan().get_node("task-a").status is TaskDAGStatus.SUCCEEDED
    assert len(restored.solve_node_receipts_by_id) == 1
    assert len(restored.task_briefs_by_id) == 1
    assert "solve_nodes=1" in prompt_text
    assert "task_briefs=1" in prompt_text
    assert "node_receipts=1" in prompt_text
    assert "task_dag_nodes=2" in prompt_text
    assert "task_dag_statuses=ready:1,succeeded:1" in prompt_text
    for forbidden in (
        "taskDagPlanReadback",
        "task_dag_plan",
        "task-a",
        "task-b",
        "HTTP/1.1 200 OK",
        "<html",
        "task-a-body",
        "task-a-password",
        "task-a-session",
        "task-b-token",
        "context-auth",
        "dry-auth",
        "dry-token",
        "metadata-token",
        "plan-token",
    ):
        assert forbidden not in prompt_text


@pytest.mark.parametrize("raw_key", ["stdout", "http_body", "prompt"])
def test_p4b4r_raw_dry_result_fields_reject_before_receipt_apply(raw_key: str) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.set_task_dag_plan(_single_ready_plan())
    start = local_dag_start_next(state)
    before = _state_snapshot(state)

    with pytest.raises(TaskDAGDryResultAdapterError, match="raw field"):
        build_task_dag_outcome_from_dry_result(
            {
                "task_id": "task-a",
                "solve_node_id": start.solve_node_id,
                "task_brief_id": start.task_brief_id,
                "status": "success",
                raw_key: "Authorization: Bearer raw-auth",
            }
        )

    assert _state_snapshot(state) == before


def test_p4b4r_exit_code_zero_without_status_remains_insufficient_not_succeeded() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.set_task_dag_plan(_single_ready_plan())
    start = local_dag_start_next(state)
    outcome = build_task_dag_outcome_from_dry_result(
        {
            "task_id": "task-a",
            "solve_node_id": start.solve_node_id,
            "task_brief_id": start.task_brief_id,
            "exit_code": 0,
            "compact_output": "finished",
        }
    )
    receipt = build_local_task_dag_receipt(outcome)
    result = local_dag_apply_receipt(state, "task-a", receipt)

    assert outcome.status == "partial"
    assert "exit_code_without_status" in outcome.warnings
    assert outcome.metadata["exit_code"] == 0
    assert result.next_status == "insufficient"
    assert state.get_task_dag_plan().get_node("task-a").status is TaskDAGStatus.INSUFFICIENT
