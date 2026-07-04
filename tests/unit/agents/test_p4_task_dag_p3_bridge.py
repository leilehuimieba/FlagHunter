from __future__ import annotations

import json

import pytest

from flaghunter.agents.base_agent import AgentMessage
from flaghunter.agents.pa_agent.context_assembler import ContextAssembler
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.solve_node import SolveNodeReceipt
from flaghunter.agents.pa_agent.task_dag_p3_bridge import (
    TASK_DAG_P3_BRIDGE_RECEIPT_SCHEMA_VERSION,
    TASK_DAG_P3_BRIDGE_START_SCHEMA_VERSION,
    TaskDAGP3BridgeError,
    record_task_dag_p3_receipt,
    record_task_dag_p3_start,
)
from flaghunter.agents.pa_agent.task_dag_plan import (
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
    build_task_dag_plan_readback,
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
            AgentMessage(role="user", content="continue from DAG/P3 bridge")
        ]


def _plan_with_task(
    *,
    status: TaskDAGStatus | str = TaskDAGStatus.READY,
    solve_node_id: str = "",
    task_brief_id: str = "",
) -> TaskDAGPlan:
    plan = TaskDAGPlan(id="plan-bridge")
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            kind="exploit",
            title="Exploit upload",
            goal="Run upload primitive",
            status=status,
            solve_node_id=solve_node_id,
            task_brief_id=task_brief_id,
            claim_ids=["claim-a"],
            trace_ids=["trace-a"],
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


def test_p4b4f_start_ready_task_records_p3_refs_marks_running_and_persists_plan() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = _plan_with_task(status=TaskDAGStatus.READY)

    result = record_task_dag_p3_start(
        state,
        plan,
        "task-a",
        run_id="run-bridge",
        context_summary="compact context",
        allowed_tool_names=["browser"],
        blocked_tool_names=["sqlmap"],
    )

    persisted = state.get_task_dag_plan()
    node = persisted.get_node("task-a")

    assert result.schema_version == TASK_DAG_P3_BRIDGE_START_SCHEMA_VERSION
    assert result.plan_id == "plan-bridge"
    assert result.task_id == "task-a"
    assert result.previous_status == "ready"
    assert result.next_status == "running"
    assert result.solve_node_id
    assert result.task_brief_id
    assert result.receipt_id == ""
    assert task_dag_plan_to_dict(result.updated_plan) == task_dag_plan_to_dict(persisted)
    assert node.status is TaskDAGStatus.RUNNING
    assert node.solve_node_id == result.solve_node_id
    assert node.task_brief_id == result.task_brief_id
    assert state.get_solve_node(result.solve_node_id) is not None
    assert state.get_task_brief(result.task_brief_id).node_id == result.solve_node_id
    result_text = repr(result.to_dict())
    assert "Exploit upload" not in result_text
    assert "Run upload primitive" not in result_text
    assert "nodes" not in result_text


def test_p4b4f_start_rejects_none_empty_malformed_and_restore_warning_plans() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    before = _state_snapshot(state)
    warning_plan = _plan_with_task()
    warning_plan.restore_warnings.append("bad edge")

    for bad_plan in (None, TaskDAGPlan(id="empty-plan"), {"nodes": "bad"}, warning_plan):
        with pytest.raises(TaskDAGP3BridgeError):
            record_task_dag_p3_start(state, bad_plan, "task-a")

    assert _state_snapshot(state) == before


@pytest.mark.parametrize("status", ["proposed", "succeeded", "failed", "insufficient", "skipped", "blocked"])
def test_p4b4f_start_rejects_proposed_and_terminal_tasks_without_state_mutation(status: str) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = _plan_with_task(status=status)
    state.set_task_dag_plan(plan)
    before = _state_snapshot(state)

    with pytest.raises(TaskDAGP3BridgeError):
        record_task_dag_p3_start(state, plan, "task-a")

    assert _state_snapshot(state) == before


def test_p4b4f_start_rejects_missing_task_without_state_mutation() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = _plan_with_task()
    state.set_task_dag_plan(plan)
    before = _state_snapshot(state)

    with pytest.raises(TaskDAGP3BridgeError, match="unknown task"):
        record_task_dag_p3_start(state, plan, "missing")

    assert _state_snapshot(state) == before


def test_p4b4f_start_running_task_is_idempotent_when_refs_are_already_linked() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    started = record_task_dag_p3_start(state, _plan_with_task(), "task-a")
    before = _state_snapshot(state)

    result = record_task_dag_p3_start(
        state,
        state.get_task_dag_plan(),
        "task-a",
        run_id="run-bridge",
    )

    assert result.previous_status == "running"
    assert result.next_status == "running"
    assert result.solve_node_id == started.solve_node_id
    assert result.task_brief_id == started.task_brief_id
    assert _state_snapshot(state) == before


def test_p4b4f_start_running_task_with_missing_refs_records_and_links_without_status_change() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = _plan_with_task(status=TaskDAGStatus.RUNNING)

    result = record_task_dag_p3_start(state, plan, "task-a")
    node = state.get_task_dag_plan().get_node("task-a")

    assert result.previous_status == "running"
    assert result.next_status == "running"
    assert node.status is TaskDAGStatus.RUNNING
    assert node.solve_node_id == result.solve_node_id
    assert node.task_brief_id == result.task_brief_id
    assert state.solve_node_graph.to_dict()["summary"]["nodeCount"] == 1
    assert len(state.task_briefs_by_id) == 1


def test_p4b4f_start_running_task_with_conflicting_refs_rejects_without_mutation() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    started = record_task_dag_p3_start(state, _plan_with_task(), "task-a")
    conflicting = _plan_with_task(
        status=TaskDAGStatus.RUNNING,
        solve_node_id=started.solve_node_id,
        task_brief_id="other-brief",
    )
    before = _state_snapshot(state)

    with pytest.raises(TaskDAGP3BridgeError, match="conflicting task_brief_id"):
        record_task_dag_p3_start(state, conflicting, "task-a")

    assert _state_snapshot(state) == before


def test_p4b4f_start_running_task_with_dangling_refs_rejects_without_mutation() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    dangling = _plan_with_task(
        status=TaskDAGStatus.RUNNING,
        solve_node_id="missing-node",
        task_brief_id="missing-brief",
    )
    before = _state_snapshot(state)

    with pytest.raises(TaskDAGP3BridgeError, match="unknown solve_node_id"):
        record_task_dag_p3_start(state, dangling, "task-a")

    assert _state_snapshot(state) == before


def test_p4b4f_start_rolls_back_partial_state_writes(monkeypatch) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = _plan_with_task()
    before = _state_snapshot(state)

    def _raise_brief_store_down(_brief):
        raise RuntimeError("brief store down")

    monkeypatch.setattr(state, "record_task_brief", _raise_brief_store_down)

    with pytest.raises(TaskDAGP3BridgeError, match="brief store down"):
        record_task_dag_p3_start(state, plan, "task-a")

    assert _state_snapshot(state) == before


def test_p4b4f_start_rolls_back_when_solve_node_record_fails(monkeypatch) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = _plan_with_task()
    before = _state_snapshot(state)

    def _raise_node_store_down(_node):
        raise RuntimeError("node store down")

    monkeypatch.setattr(state, "record_solve_node", _raise_node_store_down)

    with pytest.raises(TaskDAGP3BridgeError, match="node store down"):
        record_task_dag_p3_start(state, plan, "task-a")

    assert _state_snapshot(state) == before


def test_p4b4f_start_rolls_back_when_plan_persist_fails(monkeypatch) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = _plan_with_task()
    before = _state_snapshot(state)

    def _raise_plan_store_down(_plan):
        raise RuntimeError("plan store down")

    monkeypatch.setattr(state, "set_task_dag_plan", _raise_plan_store_down)

    with pytest.raises(TaskDAGP3BridgeError, match="plan store down"):
        record_task_dag_p3_start(state, plan, "task-a")

    assert _state_snapshot(state) == before


def test_p4b4f_receipt_completed_records_receipt_applies_status_and_persists_plan() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    started = record_task_dag_p3_start(state, _plan_with_task(), "task-a")
    receipt = SolveNodeReceipt(
        id="receipt-completed",
        node_id=started.solve_node_id,
        input_brief_id=started.task_brief_id,
        status="completed",
        trace_ids=["trace-receipt"],
        claim_ids=["claim-receipt"],
    )

    result = record_task_dag_p3_receipt(
        state,
        state.get_task_dag_plan(),
        "task-a",
        receipt,
    )
    node = state.get_task_dag_plan().get_node("task-a")

    assert result.schema_version == TASK_DAG_P3_BRIDGE_RECEIPT_SCHEMA_VERSION
    assert result.previous_status == "running"
    assert result.next_status == "succeeded"
    assert result.receipt_id == "receipt-completed"
    assert node.status is TaskDAGStatus.SUCCEEDED
    assert node.receipt_ids == ["receipt-completed"]
    assert "trace-receipt" in node.trace_ids
    assert "claim-receipt" in node.claim_ids
    assert state.get_solve_node_receipt("receipt-completed") is not None
    assert "output_summary" not in repr(result.to_dict())


@pytest.mark.parametrize(
    ("receipt_status", "initial_status", "expected_status"),
    [
        ("failed", "running", TaskDAGStatus.FAILED),
        ("partial", "running", TaskDAGStatus.INSUFFICIENT),
        ("blocked", "ready", TaskDAGStatus.BLOCKED),
        ("skipped", "proposed", TaskDAGStatus.SKIPPED),
    ],
)
def test_p4b4f_receipt_status_mapping(
    receipt_status: str,
    initial_status: str,
    expected_status: TaskDAGStatus,
) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = _plan_with_task(status=initial_status)
    if initial_status == "running":
        start = record_task_dag_p3_start(state, plan, "task-a")
        plan = state.get_task_dag_plan()
        node_id = start.solve_node_id
    else:
        state.set_task_dag_plan(plan)
        node_id = ""

    result = record_task_dag_p3_receipt(
        state,
        plan,
        "task-a",
        SolveNodeReceipt(
            id=f"receipt-{receipt_status}",
            node_id=node_id,
            status=receipt_status,
        ),
    )

    assert result.next_status == expected_status.value
    assert state.get_task_dag_plan().get_node("task-a").status is expected_status


def test_p4b4f_receipt_rejects_conflicts_and_invalid_status_without_mutation() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    started = record_task_dag_p3_start(state, _plan_with_task(), "task-a")
    before = _state_snapshot(state)

    with pytest.raises(TaskDAGP3BridgeError, match="conflicting solve_node_id"):
        record_task_dag_p3_receipt(
            state,
            state.get_task_dag_plan(),
            "task-a",
            SolveNodeReceipt(id="receipt-conflict", node_id="other-node"),
        )
    with pytest.raises(TaskDAGP3BridgeError, match="receipt id is required"):
        record_task_dag_p3_receipt(
            state,
            state.get_task_dag_plan(),
            "task-a",
            {"id": "", "node_id": started.solve_node_id, "status": "completed"},
        )

    assert _state_snapshot(state) == before


def test_p4b4f_receipt_rejects_missing_task_and_malformed_input_without_mutation() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    started = record_task_dag_p3_start(state, _plan_with_task(), "task-a")
    before = _state_snapshot(state)

    with pytest.raises(TaskDAGP3BridgeError, match="unknown task"):
        record_task_dag_p3_receipt(
            state,
            state.get_task_dag_plan(),
            "missing",
            SolveNodeReceipt(
                id="receipt-missing-task",
                node_id=started.solve_node_id,
                status="completed",
            ),
        )
    with pytest.raises(TaskDAGP3BridgeError, match="invalid solve node receipt"):
        record_task_dag_p3_receipt(
            state,
            state.get_task_dag_plan(),
            "task-a",
            object(),
        )

    assert _state_snapshot(state) == before


def test_p4b4f_receipt_rolls_back_when_plan_persist_fails(monkeypatch) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    started = record_task_dag_p3_start(state, _plan_with_task(), "task-a")
    before = _state_snapshot(state)

    def _raise_plan_store_down(_plan):
        raise RuntimeError("plan store down")

    monkeypatch.setattr(state, "set_task_dag_plan", _raise_plan_store_down)

    with pytest.raises(TaskDAGP3BridgeError, match="plan store down"):
        record_task_dag_p3_receipt(
            state,
            state.get_task_dag_plan(),
            "task-a",
            SolveNodeReceipt(
                id="receipt-rollback",
                node_id=started.solve_node_id,
                status="completed",
            ),
        )

    assert _state_snapshot(state) == before


def test_p4b4f_failed_or_insufficient_receipts_do_not_emit_proof_or_recovery_fields() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    started = record_task_dag_p3_start(state, _plan_with_task(), "task-a")

    result = record_task_dag_p3_receipt(
        state,
        state.get_task_dag_plan(),
        "task-a",
        SolveNodeReceipt(
            id="receipt-partial",
            node_id=started.solve_node_id,
            status="partial",
        ),
    )

    text = repr({"result": result.to_dict(), "plan": task_dag_plan_to_dict(result.updated_plan)})
    assert result.next_status == "insufficient"
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


def test_p4b4f_readback_session_and_prompt_surfaces_remain_compact(tmp_path) -> None:
    run_id = "run-p4b4f-compact"
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = TaskDAGPlan(id="plan-compact", metadata={"token": "plan-token"})
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
    started = record_task_dag_p3_start(
        state,
        plan,
        "task-a",
        run_id=run_id,
        context_summary="Authorization: Bearer context-auth",
    )
    record_task_dag_p3_receipt(
        state,
        state.get_task_dag_plan(),
        "task-a",
        SolveNodeReceipt(
            id="receipt-a",
            node_id=started.solve_node_id,
            input_brief_id=started.task_brief_id,
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

    readback_text = repr(build_task_dag_plan_readback(state.get_task_dag_plan()))
    prompt_text = ContextAssembler(
        _StubAgent(project_root=tmp_path, run_id=run_id)
    ).assemble()

    assert "task_dag_nodes=1" in prompt_text
    assert "task_dag_statuses=succeeded:1" in prompt_text
    assert "receipt-a" in readback_text
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
