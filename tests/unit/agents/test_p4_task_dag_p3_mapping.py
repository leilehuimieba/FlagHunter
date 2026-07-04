from __future__ import annotations

import json

import pytest

from flaghunter.agents.base_agent import AgentMessage
from flaghunter.agents.pa_agent.context_assembler import ContextAssembler
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.p3_solve_readback import build_p3_solve_readback
from flaghunter.agents.pa_agent.solve_node import (
    SolveNodeKind,
    SolveNodeReceipt,
    SolveNodeStatus,
    build_solve_graph_readback,
    build_solve_node_receipt_readback,
    build_task_brief_readback,
)
from flaghunter.agents.pa_agent.task_dag_p3_mapping import (
    TaskDAGMappingError,
    apply_solve_node_receipt_to_task,
    build_solve_node_for_dag_node,
    build_task_brief_for_dag_node,
    link_solve_node_to_task,
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
            AgentMessage(role="user", content="continue from DAG/P3 mapping")
        ]


def test_p4b4d_task_brief_mapping_uses_safe_refs_and_metadata_allowlist() -> None:
    plan = TaskDAGPlan(id="plan-brief", metadata={"token": "plan-token"})
    plan.add_node(
        TaskDAGNode(
            id="task-brief",
            kind="exploit",
            title="Exploit upload",
            goal="Run upload primitive",
            status=TaskDAGStatus.READY,
            claim_ids=["claim-a"],
            trace_ids=["trace-a"],
            metadata={
                "constraints": ["stay in scope"],
                "allowed_tool_names": ["browser"],
                "blocked_tool_names": ["sqlmap"],
                "secret": "node-secret",
            },
        )
    )

    brief = build_task_brief_for_dag_node(
        plan,
        "task-brief",
        run_id="run-1",
        worker_type="web",
        context_summary="compact context",
        allowed_tool_names=["curl"],
        blocked_tool_names=["nmap"],
    )

    assert brief.run_id == "run-1"
    assert brief.worker_type == "web"
    assert brief.objective == "Run upload primitive"
    assert "compact context" in brief.context_summary
    assert "Exploit upload" in brief.context_summary
    assert brief.claim_ids == ["claim-a"]
    assert brief.trace_ids == ["trace-a"]
    assert brief.constraints == ["stay in scope"]
    assert brief.allowed_tool_names == ["curl", "browser"]
    assert brief.blocked_tool_names == ["nmap", "sqlmap"]
    assert brief.metadata == {
        "task_dag_plan_id": "plan-brief",
        "task_dag_task_id": "task-brief",
        "task_kind": "exploit",
        "source_channel": "task_dag_plan",
    }
    assert "node-secret" not in repr(brief)


def test_p4b4d_task_brief_mapping_redacts_raw_body_and_sensitive_text() -> None:
    plan = TaskDAGPlan(id="plan-brief-redact")
    plan.add_node(
        TaskDAGNode(
            id="task-redact",
            kind="web token=kind-token",
            title="HTTP/1.1 200 OK\n<html>secret=body-secret</html>",
            goal="PING 127.0.0.1\n64 bytes from 127.0.0.1",
            metadata={
                "constraints": ["avoid password=constraint-password"],
                "allowed_tool_names": ["browser authorization=tool-auth"],
                "blocked_tool_names": ["curl api_key=blocked-key"],
                "note": json.dumps({"session": "metadata-session"}),
            },
        )
    )

    brief = build_task_brief_for_dag_node(
        plan,
        "task-redact",
        context_summary="cookie=context-cookie",
    )
    readback = build_task_brief_readback([brief])
    text = repr({"brief": brief, "readback": readback})

    assert "<redacted raw body>" in text
    assert "<redacted>" in text
    for leaked in (
        "PING 127.0.0.1",
        "64 bytes from",
        "HTTP/1.1 200 OK",
        "<html",
        "body-secret",
        "kind-token",
        "constraint-password",
        "tool-auth",
        "blocked-key",
        "metadata-session",
        "context-cookie",
    ):
        assert leaked not in text


@pytest.mark.parametrize(
    ("dag_status", "solve_status"),
    [
        ("proposed", SolveNodeStatus.PLANNED),
        ("ready", SolveNodeStatus.PLANNED),
        ("running", SolveNodeStatus.RUNNING),
        ("succeeded", SolveNodeStatus.COMPLETED),
        ("failed", SolveNodeStatus.FAILED),
        ("insufficient", SolveNodeStatus.FAILED),
        ("skipped", SolveNodeStatus.SKIPPED),
        ("blocked", SolveNodeStatus.BLOCKED),
    ],
)
def test_p4b4d_solve_node_mapping_status_table(
    dag_status: str,
    solve_status: SolveNodeStatus,
) -> None:
    plan = TaskDAGPlan(id=f"plan-{dag_status}")
    plan.add_node(
        TaskDAGNode(
            id=f"task-{dag_status}",
            kind="verify" if dag_status == "succeeded" else "exploit",
            title="Check candidate",
            goal="Run one step",
            status=dag_status,
            claim_ids=["claim-a"],
            trace_ids=["trace-a"],
            receipt_ids=["receipt-a"],
        )
    )

    node = build_solve_node_for_dag_node(
        plan,
        f"task-{dag_status}",
        run_id="run-1",
        parent_id="parent-a",
    )

    assert node.id != f"task-{dag_status}"
    assert node.run_id == "run-1"
    assert node.parent_id == "parent-a"
    assert node.status is solve_status
    assert node.claim_ids == ["claim-a"]
    assert node.trace_ids == ["trace-a"]
    assert node.receipt_ids == ["receipt-a"]
    assert node.metadata["task_dag_task_id"] == f"task-{dag_status}"
    assert node.metadata["task_dag_plan_id"] == f"plan-{dag_status}"
    assert node.metadata["source_channel"] == "task_dag_plan"
    if dag_status == "insufficient":
        assert node.metadata["dag_status"] == "insufficient"


def test_p4b4d_solve_node_mapping_unknown_kind_is_generic_and_redacted() -> None:
    plan = TaskDAGPlan(id="plan-kind")
    plan.add_node(
        TaskDAGNode(
            id="task-kind",
            kind="custom token=kind-token",
            title="uid=33(www-data)",
            goal="Use password=goal-password",
            status="ready",
        )
    )

    node = build_solve_node_for_dag_node(plan, "task-kind")
    text = repr(build_solve_graph_readback({"nodes": [node.to_dict()], "edges": []}))

    assert node.kind is SolveNodeKind.GENERIC
    assert "<redacted>" in text
    for leaked in ("kind-token", "uid=33", "goal-password"):
        assert leaked not in text


def test_p4b4d_link_helper_sets_refs_idempotently_and_rejects_conflicts() -> None:
    plan = TaskDAGPlan(id="plan-link")
    plan.add_node(TaskDAGNode(id="task-a"))

    linked = link_solve_node_to_task(
        plan,
        "task-a",
        solve_node_id="node-a",
        task_brief_id="brief-a",
    )
    linked_again = link_solve_node_to_task(
        linked,
        "task-a",
        solve_node_id="node-a",
        task_brief_id="brief-a",
    )
    before = task_dag_plan_to_dict(linked_again)

    assert linked.get_node("task-a").solve_node_id == "node-a"
    assert linked.get_node("task-a").task_brief_id == "brief-a"
    assert task_dag_plan_to_dict(linked_again) == before
    with pytest.raises(TaskDAGMappingError, match="conflicting solve_node_id"):
        link_solve_node_to_task(linked_again, "task-a", solve_node_id="node-b")
    with pytest.raises(TaskDAGMappingError, match="unknown task"):
        link_solve_node_to_task(linked_again, "missing", solve_node_id="node-a")
    with pytest.raises(TaskDAGMappingError, match="at least one"):
        link_solve_node_to_task(linked_again, "task-a")
    assert task_dag_plan_to_dict(linked_again) == before


@pytest.mark.parametrize(
    ("receipt_status", "dag_status"),
    [
        ("completed", TaskDAGStatus.SUCCEEDED),
        ("failed", TaskDAGStatus.FAILED),
        ("partial", TaskDAGStatus.INSUFFICIENT),
        ("blocked", TaskDAGStatus.BLOCKED),
        ("skipped", TaskDAGStatus.SKIPPED),
        ("future", TaskDAGStatus.INSUFFICIENT),
    ],
)
def test_p4b4d_receipt_status_mapping_updates_dag_refs(
    receipt_status: str,
    dag_status: TaskDAGStatus,
) -> None:
    initial_status = "ready" if receipt_status in {"blocked", "skipped"} else "running"
    plan = TaskDAGPlan(id=f"plan-receipt-{receipt_status}")
    plan.add_node(TaskDAGNode(id="task-a", status=initial_status))
    receipt = SolveNodeReceipt(
        id=f"receipt-{receipt_status}",
        node_id="node-a",
        status=receipt_status,
        trace_ids=["trace-a"],
        claim_ids=["claim-a"],
        metadata={"verification_record_ids": ["verification-should-not-copy"]},
    )

    updated = apply_solve_node_receipt_to_task(plan, "task-a", receipt)
    node = updated.get_node("task-a")

    assert node.status is dag_status
    assert node.receipt_ids == [f"receipt-{receipt_status}"]
    assert node.solve_node_id == "node-a"
    assert node.trace_ids == ["trace-a"]
    assert node.claim_ids == ["claim-a"]
    assert node.verification_record_ids == []


def test_p4b4d_receipt_mapping_rejects_conflicts_and_preserves_plan() -> None:
    plan = TaskDAGPlan(id="plan-receipt-reject")
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            status="running",
            solve_node_id="node-original",
            receipt_ids=["receipt-original"],
            trace_ids=["trace-original"],
        )
    )
    before = task_dag_plan_to_dict(plan)

    with pytest.raises(TaskDAGMappingError, match="conflicting solve_node_id"):
        apply_solve_node_receipt_to_task(
            plan,
            "task-a",
            SolveNodeReceipt(id="receipt-new", node_id="node-new", status="completed"),
        )
    with pytest.raises(TaskDAGMappingError, match="unknown task"):
        apply_solve_node_receipt_to_task(
            plan,
            "missing",
            SolveNodeReceipt(id="receipt-new", node_id="node-original"),
        )
    assert task_dag_plan_to_dict(plan) == before


def test_p4b4d_helpers_are_pure_and_state_integration_is_explicit() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = TaskDAGPlan(id="plan-state")
    plan.add_node(TaskDAGNode(id="task-a", kind="exploit", goal="Run step"))

    solve_node = build_solve_node_for_dag_node(plan, "task-a", run_id="run-state")
    brief = build_task_brief_for_dag_node(plan, "task-a", run_id="run-state")

    assert state.solve_node_graph.to_dict()["summary"]["nodeCount"] == 0
    assert state.task_briefs_by_id == {}
    solve_node_id = state.record_solve_node(solve_node)
    brief.node_id = solve_node_id
    brief_id = state.record_task_brief(brief)
    linked = link_solve_node_to_task(
        plan,
        "task-a",
        solve_node_id=solve_node_id,
        task_brief_id=brief_id,
    )
    state.set_task_dag_plan(linked)

    assert state.get_task_dag_plan().get_node("task-a").solve_node_id == solve_node_id
    assert state.get_task_dag_plan().get_node("task-a").task_brief_id == brief_id
    assert state.solve_node_graph.to_dict()["summary"]["nodeCount"] == 1
    assert len(state.task_briefs_by_id) == 1


def test_p4b4d_readback_session_and_prompt_surfaces_remain_compact(tmp_path) -> None:
    run_id = "run-p4b4d-compact"
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = TaskDAGPlan(id="plan-compact", metadata={"token": "plan-token"})
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            kind="exploit",
            title="HTTP/1.1 200 OK\n<html>secret=body-secret</html>",
            goal="Use password=goal-password",
            status="running",
        )
    )
    solve_node = build_solve_node_for_dag_node(plan, "task-a", run_id=run_id)
    brief = build_task_brief_for_dag_node(
        plan,
        "task-a",
        run_id=run_id,
        context_summary="Authorization: Bearer context-auth",
    )
    solve_node_id = state.record_solve_node(solve_node)
    brief.node_id = solve_node_id
    brief_id = state.record_task_brief(brief)
    linked = link_solve_node_to_task(
        plan,
        "task-a",
        solve_node_id=solve_node_id,
        task_brief_id=brief_id,
    )
    receipt_id = state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-a",
            node_id=solve_node_id,
            input_brief_id=brief_id,
            status="completed",
            output_summary="token=receipt-token",
            trace_ids=["trace-a"],
            claim_ids=["claim-a"],
        )
    )
    linked = apply_solve_node_receipt_to_task(
        linked,
        "task-a",
        state.get_solve_node_receipt(receipt_id),
    )
    state.set_task_dag_plan(linked)
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    readback_text = repr(
        {
            "p3": build_p3_solve_readback(state),
            "dag": build_task_dag_plan_readback(state.get_task_dag_plan()),
        }
    )
    prompt_text = ContextAssembler(
        _StubAgent(project_root=tmp_path, run_id=run_id)
    ).assemble()

    assert "solve_nodes=1" in prompt_text
    assert "task_briefs=1" in prompt_text
    assert "node_receipts=1" in prompt_text
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
        "receipt-token",
    ):
        assert forbidden not in prompt_text


def test_p4b4d_mapping_outputs_do_not_emit_proof_fields() -> None:
    plan = TaskDAGPlan()
    plan.add_node(TaskDAGNode(id="task-a", status="running"))
    updated = apply_solve_node_receipt_to_task(
        plan,
        "task-a",
        SolveNodeReceipt(
            id="receipt-completed",
            status="completed",
            claim_ids=["claim-candidate"],
            trace_ids=["trace-tool"],
        ),
    )
    text = repr(task_dag_plan_to_dict(updated))

    for forbidden in (
        "verifiedFlags",
        "verification_decision",
        "verifierProof",
        'level="verified"',
        "level='verified'",
    ):
        assert forbidden not in text
