from __future__ import annotations

from types import SimpleNamespace

import pytest

from flaghunter.agents.base_agent import AgentMessage
from flaghunter.agents.pa_agent.context_assembler import ContextAssembler
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.task_dag_plan import (
    TASK_DAG_READY_SELECTION_SCHEMA_VERSION,
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
    TaskDAGTransitionError,
    build_task_dag_plan_readback,
    mark_task_finished,
    mark_task_ready,
    mark_task_running,
    select_next_ready_task,
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
            AgentMessage(role="user", content="continue with task DAG state")
        ]


def _base_selection(reason: str, *, plan_id: str = "") -> dict:
    return {
        "schemaVersion": TASK_DAG_READY_SELECTION_SCHEMA_VERSION,
        "planId": plan_id,
        "selectedTaskId": "",
        "selectedStatus": "",
        "reason": reason,
        "readyTaskIds": [],
        "blockedTaskIds": [],
        "dependencySummary": {
            "satisfiedDependencyCount": 0,
            "blockingDependencyCount": 0,
        },
        "restoreWarningCount": 0,
    }


def test_p4b4_ready_selector_empty_and_restore_warning_noop() -> None:
    assert select_next_ready_task(None) == _base_selection("empty_plan")

    empty_plan = TaskDAGPlan(id="plan-empty")
    assert select_next_ready_task(empty_plan) == _base_selection(
        "empty_plan",
        plan_id="plan-empty",
    )

    warning_plan = TaskDAGPlan(id="plan-warning")
    warning_plan.restore_warnings.append("restored edge was invalid")
    warning_plan.add_node(TaskDAGNode(id="task-ready", status=TaskDAGStatus.READY))

    selection = select_next_ready_task(warning_plan)

    assert selection["reason"] == "restore_warnings_present"
    assert selection["selectedTaskId"] == ""
    assert selection["readyTaskIds"] == []
    assert selection["restoreWarningCount"] == 1


def test_p4b4_ready_selector_running_guard_blocks_selection() -> None:
    plan = TaskDAGPlan(id="plan-running")
    plan.add_node(TaskDAGNode(id="task-running", status=TaskDAGStatus.RUNNING))
    plan.add_node(TaskDAGNode(id="task-ready", status=TaskDAGStatus.READY))

    selection = select_next_ready_task(plan)

    assert selection["reason"] == "running_task_present"
    assert selection["selectedTaskId"] == ""
    assert selection["readyTaskIds"] == []


@pytest.mark.parametrize("dependency_status", ["succeeded", "skipped"])
def test_p4b4_ready_selector_satisfied_dependencies_unblock(
    dependency_status: str,
) -> None:
    plan = TaskDAGPlan(id=f"plan-{dependency_status}")
    plan.add_node(TaskDAGNode(id="task-a", status=dependency_status))
    plan.add_node(TaskDAGNode(id="task-b", status="ready", depends_on=["task-a"]))

    selection = select_next_ready_task(plan)

    assert selection["reason"] == "selected"
    assert selection["selectedTaskId"] == "task-b"
    assert selection["selectedStatus"] == "ready"
    assert selection["readyTaskIds"] == ["task-b"]
    assert selection["blockedTaskIds"] == []
    assert selection["dependencySummary"] == {
        "satisfiedDependencyCount": 1,
        "blockingDependencyCount": 0,
    }


@pytest.mark.parametrize(
    "dependency_status",
    ["failed", "blocked", "insufficient", "proposed"],
)
def test_p4b4_ready_selector_unsatisfied_dependencies_block(
    dependency_status: str,
) -> None:
    plan = TaskDAGPlan(id=f"plan-blocked-{dependency_status}")
    plan.add_node(TaskDAGNode(id="task-a", status=dependency_status))
    plan.add_node(TaskDAGNode(id="task-b", status="ready", depends_on=["task-a"]))

    selection = select_next_ready_task(plan)

    assert selection["reason"] == "blocked_by_dependencies"
    assert selection["selectedTaskId"] == ""
    assert selection["readyTaskIds"] == []
    assert selection["blockedTaskIds"] == ["task-b"]
    assert selection["dependencySummary"] == {
        "satisfiedDependencyCount": 0,
        "blockingDependencyCount": 1,
    }


def test_p4b4_ready_dependency_blocks_dependent_when_dependency_is_not_selectable() -> None:
    plan = TaskDAGPlan(id="plan-ready-dependency")
    plan.add_node(TaskDAGNode(id="root", status="failed"))
    plan.add_node(TaskDAGNode(id="task-a", status="ready", depends_on=["root"]))
    plan.add_node(TaskDAGNode(id="task-b", status="ready", depends_on=["task-a"]))

    selection = select_next_ready_task(plan)

    assert selection["reason"] == "blocked_by_dependencies"
    assert selection["selectedTaskId"] == ""
    assert selection["readyTaskIds"] == []
    assert selection["blockedTaskIds"] == ["task-a", "task-b"]
    assert selection["dependencySummary"] == {
        "satisfiedDependencyCount": 0,
        "blockingDependencyCount": 2,
    }


def test_p4b4_running_dependency_uses_global_running_guard() -> None:
    plan = TaskDAGPlan(id="plan-running-dependency")
    plan.add_node(TaskDAGNode(id="task-a", status="running"))
    plan.add_node(TaskDAGNode(id="task-b", status="ready", depends_on=["task-a"]))

    selection = select_next_ready_task(plan)

    assert selection["reason"] == "running_task_present"
    assert selection["selectedTaskId"] == ""
    assert selection["readyTaskIds"] == []


def test_p4b4_ready_selector_is_deterministic_after_round_trip() -> None:
    plan = TaskDAGPlan(id="plan-deterministic")
    plan.add_node(TaskDAGNode(id="task-first", status="ready", created_at=3.0))
    plan.add_node(TaskDAGNode(id="task-second", status="ready", created_at=1.0))

    restored = task_dag_plan_from_dict(task_dag_plan_to_dict(plan))

    assert select_next_ready_task(plan)["selectedTaskId"] == "task-first"
    assert select_next_ready_task(restored)["selectedTaskId"] == "task-first"
    assert select_next_ready_task(restored)["readyTaskIds"] == [
        "task-first",
        "task-second",
    ]


def test_p4b4_status_transitions_happy_paths_are_atomic_copies() -> None:
    plan = TaskDAGPlan(id="plan-transitions")
    plan.add_node(TaskDAGNode(id="task-a", status="succeeded"))
    plan.add_node(TaskDAGNode(id="task-b", status="proposed", depends_on=["task-a"]))
    plan.add_node(TaskDAGNode(id="task-skip", status="proposed"))
    plan.add_node(TaskDAGNode(id="task-block", status="ready"))

    ready_plan = mark_task_ready(plan, "task-b", reason="deps done")
    running_plan = mark_task_running(ready_plan, "task-b", started_at=123.0)
    succeeded_plan = mark_task_finished(
        running_plan,
        "task-b",
        status="succeeded",
        receipt_id="receipt-b",
        solve_node_id="node-b",
        trace_ids=["trace-b"],
        claim_ids=["claim-b"],
        verification_record_ids=["verification-b"],
    )
    skipped_plan = mark_task_finished(plan, "task-skip", status="skipped")
    blocked_plan = mark_task_finished(plan, "task-block", status="blocked")

    assert plan.get_node("task-b").status is TaskDAGStatus.PROPOSED
    assert ready_plan.get_node("task-b").status is TaskDAGStatus.READY
    assert ready_plan.get_node("task-b").metadata["readyReason"] == "deps done"
    assert running_plan.get_node("task-b").status is TaskDAGStatus.RUNNING
    assert running_plan.get_node("task-b").metadata["startedAt"] == 123.0
    assert succeeded_plan.get_node("task-b").status is TaskDAGStatus.SUCCEEDED
    assert succeeded_plan.get_node("task-b").receipt_ids == ["receipt-b"]
    assert succeeded_plan.get_node("task-b").solve_node_id == "node-b"
    assert succeeded_plan.get_node("task-b").trace_ids == ["trace-b"]
    assert succeeded_plan.get_node("task-b").claim_ids == ["claim-b"]
    assert succeeded_plan.get_node("task-b").verification_record_ids == [
        "verification-b"
    ]
    assert skipped_plan.get_node("task-skip").status is TaskDAGStatus.SKIPPED
    assert blocked_plan.get_node("task-block").status is TaskDAGStatus.BLOCKED


@pytest.mark.parametrize("terminal_status", ["failed", "insufficient"])
def test_p4b4_running_task_can_finish_failed_or_insufficient(
    terminal_status: str,
) -> None:
    plan = TaskDAGPlan(id=f"plan-{terminal_status}")
    plan.add_node(TaskDAGNode(id="task-a", status="running"))

    finished = mark_task_finished(
        plan,
        "task-a",
        status=terminal_status,
        receipt_id=f"receipt-{terminal_status}",
    )

    assert finished.get_node("task-a").status.value == terminal_status
    assert finished.get_node("task-a").receipt_ids == [f"receipt-{terminal_status}"]


def test_p4b4_status_transition_rejects_preserve_original_plan() -> None:
    plan = TaskDAGPlan(id="plan-rejects")
    plan.add_node(TaskDAGNode(id="dep", status="failed"))
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            status="proposed",
            depends_on=["dep"],
            receipt_ids=["receipt-original"],
            trace_ids=["trace-original"],
        )
    )
    plan.add_node(TaskDAGNode(id="task-terminal", status="succeeded"))
    before = task_dag_plan_to_dict(plan)

    with pytest.raises(TaskDAGTransitionError, match="unknown task"):
        mark_task_running(plan, "missing")
    with pytest.raises(TaskDAGTransitionError, match="dependencies are not satisfied"):
        mark_task_ready(plan, "task-a")
    with pytest.raises(TaskDAGTransitionError, match="terminal"):
        mark_task_running(plan, "task-terminal")
    with pytest.raises(TaskDAGTransitionError, match="invalid finish status"):
        mark_task_finished(
            plan,
            "task-a",
            status="verified",
            receipt_id="receipt-illegal",
            trace_ids=["trace-illegal"],
        )

    assert task_dag_plan_to_dict(plan) == before
    assert plan.get_node("task-a").receipt_ids == ["receipt-original"]
    assert plan.get_node("task-a").trace_ids == ["trace-original"]


def test_p4b4_readback_session_and_prompt_remain_compact(tmp_path) -> None:
    run_id = "run-p4b4-compact"
    plan = TaskDAGPlan(id="plan-compact", metadata={"token": "plan-token"})
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            title="PING 127.0.0.1\n64 bytes from 127.0.0.1",
            goal="collect password=goal-password",
            status="ready",
            metadata={"authorization": "Bearer node-auth"},
        )
    )
    updated = mark_task_running(plan, "task-a")
    updated = mark_task_finished(
        updated,
        "task-a",
        status="failed",
        receipt_id="receipt-a",
        trace_ids=["trace-a"],
    )
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.set_task_dag_plan(updated)
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    readback = build_task_dag_plan_readback(updated)
    text = ContextAssembler(_StubAgent(project_root=tmp_path, run_id=run_id)).assemble()

    assert readback["summary"]["statusCounts"] == {"failed": 1}
    assert "task_dag_nodes=1" in text
    assert "task_dag_statuses=failed:1" in text
    for forbidden in (
        "taskDagPlanReadback",
        "task_dag_plan",
        "task-a",
        "receipt-a",
        "trace-a",
        "PING 127.0.0.1",
        "64 bytes from",
        "goal-password",
        "plan-token",
        "node-auth",
    ):
        assert forbidden not in text


def test_p4b4_selection_and_transition_helpers_do_not_emit_proof_fields() -> None:
    plan = TaskDAGPlan()
    plan.add_node(TaskDAGNode(id="task-a", status="ready"))

    selection = select_next_ready_task(plan)
    running = mark_task_running(plan, "task-a")
    succeeded = mark_task_finished(
        running,
        "task-a",
        status="succeeded",
        receipt_id="receipt-success",
        claim_ids=["claim-candidate"],
    )
    text = repr(
        {
            "selection": selection,
            "plan": task_dag_plan_to_dict(succeeded),
        }
    )

    for forbidden in (
        "verifiedFlags",
        "verification_decision",
        "verifierProof",
        'level="verified"',
        "level='verified'",
    ):
        assert forbidden not in text
