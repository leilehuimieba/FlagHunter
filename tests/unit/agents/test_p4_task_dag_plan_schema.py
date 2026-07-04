from __future__ import annotations

import json

import pytest

from flaghunter.agents.pa_agent.task_dag_plan import (
    TASK_DAG_PLAN_SCHEMA_VERSION,
    TaskDAGEdge,
    TaskDAGGraphError,
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
    build_task_dag_plan_readback,
    empty_task_dag_plan_readback,
    task_dag_node_from_dict,
    task_dag_node_to_dict,
    task_dag_plan_from_dict,
    task_dag_plan_to_dict,
)


def test_p4b2_empty_task_dag_plan_readback_and_restore_are_stable() -> None:
    assert empty_task_dag_plan_readback() == {
        "schemaVersion": TASK_DAG_PLAN_SCHEMA_VERSION,
        "planId": "",
        "nodes": [],
        "edges": [],
        "summary": {
            "nodeCount": 0,
            "edgeCount": 0,
            "exportedNodeCount": 0,
            "exportedEdgeCount": 0,
            "truncatedNodeCount": 0,
            "truncatedEdgeCount": 0,
            "statusCounts": {},
            "relationCounts": {},
            "restoreWarningCount": 0,
        },
        "restoreWarnings": [],
    }

    restored_none = TaskDAGPlan.from_dict(None)
    restored_empty = task_dag_plan_from_dict({})

    assert restored_none.to_dict()["schemaVersion"] == TASK_DAG_PLAN_SCHEMA_VERSION
    assert restored_none.nodes_by_id == {}
    assert restored_none.edges == []
    assert restored_empty.to_dict()["nodes"] == []
    assert build_task_dag_plan_readback(None) == empty_task_dag_plan_readback()


def test_p4b2_node_edge_plan_round_trip_preserves_contract_links() -> None:
    plan = TaskDAGPlan(id="plan-1", metadata={"source": "unit"})
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            kind="recon",
            title="Collect facts",
            goal="Identify endpoints",
            status=TaskDAGStatus.SUCCEEDED,
            task_brief_id="brief-a",
            solve_node_id="node-a",
            receipt_ids=["receipt-a"],
            claim_ids=["claim-a"],
            trace_ids=["trace-a"],
            verification_record_ids=["verification-a"],
            metadata={"priority": "high"},
        )
    )
    plan.add_node(
        TaskDAGNode(
            id="task-b",
            kind="exploit",
            title="Try exploit",
            goal="Use candidate credential",
            status="ready",
            depends_on=["task-a"],
            task_brief_id="brief-b",
            solve_node_id="node-b",
            receipt_ids=["receipt-b"],
            claim_ids=["claim-b"],
            trace_ids=["trace-b"],
            verification_record_ids=["verification-b"],
        )
    )

    payload = task_dag_plan_to_dict(plan)
    restored = task_dag_plan_from_dict(payload)

    assert payload["schemaVersion"] == TASK_DAG_PLAN_SCHEMA_VERSION
    assert payload["id"] == "plan-1"
    assert payload["nodes"][1]["depends_on"] == ["task-a"]
    assert payload["edges"][0]["source_id"] == "task-a"
    assert payload["edges"][0]["target_id"] == "task-b"
    assert restored.get_node("task-a").status is TaskDAGStatus.SUCCEEDED
    assert restored.get_node("task-b").depends_on == ["task-a"]
    assert restored.get_node("task-b").task_brief_id == "brief-b"
    assert restored.get_node("task-b").solve_node_id == "node-b"
    assert restored.get_node("task-b").receipt_ids == ["receipt-b"]
    assert restored.get_node("task-b").claim_ids == ["claim-b"]
    assert restored.get_node("task-b").trace_ids == ["trace-b"]
    assert restored.get_node("task-b").verification_record_ids == ["verification-b"]


def test_p4b2_unknown_future_fields_and_status_fallback_are_safe() -> None:
    restored = task_dag_node_from_dict(
        {
            "id": "",
            "kind": "verify",
            "title": "future",
            "status": "verified",
            "depends_on": "task-a",
            "receipt_ids": "receipt-a",
            "claim_ids": ["claim-a", None, ""],
            "trace_ids": {"bad": "shape"},
            "verification_record_ids": ("verification-a",),
            "metadata": "not-a-dict",
            "future_field": "ignored",
        }
    )

    payload = task_dag_node_to_dict(restored)

    assert restored.id.startswith("task_")
    assert restored.status is TaskDAGStatus.PROPOSED
    assert restored.depends_on == ["task-a"]
    assert restored.receipt_ids == ["receipt-a"]
    assert restored.claim_ids == ["claim-a"]
    assert restored.trace_ids == []
    assert restored.verification_record_ids == ["verification-a"]
    assert restored.metadata == {}
    assert "future_field" not in payload


def test_p4b2_dependency_guard_rejects_missing_self_and_cycles() -> None:
    plan = TaskDAGPlan()
    plan.add_node(TaskDAGNode(id="task-a"))
    plan.add_node(TaskDAGNode(id="task-b"))
    plan.add_node(TaskDAGNode(id="task-c"))

    first = plan.add_edge("task-a", "task-b")
    second = plan.add_edge("task-a", "task-b")
    plan.add_edge("task-b", "task-c")

    assert first is second
    assert len(plan.edges) == 2
    with pytest.raises(TaskDAGGraphError, match="missing target"):
        plan.add_edge("task-a", "task-missing")
    with pytest.raises(TaskDAGGraphError, match="missing source"):
        plan.add_edge("task-missing", "task-a")
    with pytest.raises(TaskDAGGraphError, match="self edge"):
        plan.add_edge("task-a", "task-a")
    with pytest.raises(TaskDAGGraphError, match="cycle"):
        plan.add_edge("task-c", "task-a")


def test_p4b2_add_node_missing_dependency_is_atomic() -> None:
    plan = TaskDAGPlan()

    with pytest.raises(TaskDAGGraphError, match="missing source"):
        plan.add_node(TaskDAGNode(id="task-b", depends_on=["missing"]))

    assert plan.nodes_by_id == {}
    assert plan.edges == []


def test_p4b2_add_node_cycle_rejects_without_replacing_existing_node() -> None:
    plan = TaskDAGPlan()
    plan.add_node(TaskDAGNode(id="a"))
    plan.add_node(TaskDAGNode(id="b"))
    plan.add_edge("a", "b")

    with pytest.raises(TaskDAGGraphError, match="cycle"):
        plan.add_node(TaskDAGNode(id="a", title="replacement", depends_on=["b"]))

    assert {node_id: node.title for node_id, node in plan.nodes_by_id.items()} == {
        "a": "",
        "b": "",
    }
    assert [(edge.source_id, edge.target_id) for edge in plan.edges] == [("a", "b")]
    assert plan.get_node("a").depends_on == []
    assert plan.get_node("b").depends_on == ["a"]


def test_p4b2_duplicate_node_id_upserts_last_and_keeps_readback_deterministic() -> None:
    plan = TaskDAGPlan()
    plan.add_node(TaskDAGNode(id="task-a", title="first", status="proposed"))
    plan.add_node(TaskDAGNode(id="task-a", title="second", status="ready"))

    readback = build_task_dag_plan_readback(plan)

    assert plan.get_node("task-a").title == "second"
    assert plan.get_node("task-a").status is TaskDAGStatus.READY
    assert readback["summary"]["nodeCount"] == 1
    assert readback["nodes"][0]["titlePreview"] == "second"


def test_p4b2_readback_limits_counts_and_dependency_projection() -> None:
    plan = TaskDAGPlan(id="plan-limits")
    for index, status in enumerate(("proposed", "ready", "failed")):
        plan.add_node(
            TaskDAGNode(
                id=f"task-{index}",
                title=f"Task {index}",
                status=status,
            )
        )
    plan.add_edge("task-0", "task-1")
    plan.add_edge("task-1", "task-2", relation="unblocks")

    readback = build_task_dag_plan_readback(plan, node_limit=2, edge_limit=1)

    assert [item["taskId"] for item in readback["nodes"]] == ["task-1", "task-2"]
    assert readback["nodes"][0]["dependsOn"] == ["task-0"]
    assert readback["nodes"][1]["dependsOn"] == []
    assert readback["edges"] == [
        {
            "sourceTaskId": "task-1",
            "targetTaskId": "task-2",
            "relation": "unblocks",
            "metadata": {},
        }
    ]
    assert readback["summary"]["nodeCount"] == 3
    assert readback["summary"]["edgeCount"] == 2
    assert readback["summary"]["exportedNodeCount"] == 2
    assert readback["summary"]["exportedEdgeCount"] == 1
    assert readback["summary"]["truncatedNodeCount"] == 1
    assert readback["summary"]["truncatedEdgeCount"] == 1
    assert readback["summary"]["statusCounts"] == {
        "failed": 1,
        "proposed": 1,
        "ready": 1,
    }
    assert readback["summary"]["relationCounts"] == {"depends_on": 1, "unblocks": 1}


def test_p4b2_readback_redacts_sensitive_and_raw_body_text() -> None:
    plan = TaskDAGPlan(
        id="plan-redact",
        metadata={
            "note": json.dumps({"token": "plan-token"}),
            "cookie": "plan-cookie",
        },
    )
    plan.add_node(
        TaskDAGNode(
            id="task-redact",
            title=(
                "PING 127.0.0.1\n"
                "64 bytes from 127.0.0.1\n"
                "uid=33(www-data)"
            ),
            goal="Use password=goal-password Authorization: Bearer goal-auth",
            metadata={
                "output_summary": "HTTP/1.1 200 OK\n<html>secret=body-secret</html>",
                "api_key": "metadata-key",
                "note": json.dumps({"session": "metadata-session"}),
            },
        )
    )

    readback = build_task_dag_plan_readback(plan)
    text = repr(readback)
    node = readback["nodes"][0]

    assert node["titlePreview"] == "<redacted raw body>"
    assert "password=<redacted>" in node["goalPreview"]
    assert node["metadata"]["output_summary"] == "<redacted raw body>"
    assert node["metadata"]["api_key"] == "<redacted>"
    assert "<redacted>" in text
    for leaked in (
        "PING 127.0.0.1",
        "64 bytes from",
        "uid=33",
        "goal-password",
        "goal-auth",
        "body-secret",
        "metadata-key",
        "metadata-session",
        "plan-token",
        "plan-cookie",
    ):
        assert leaked not in text


def test_p4b2_status_and_receipt_links_do_not_emit_proof_fields() -> None:
    plan = TaskDAGPlan()
    for status in ("succeeded", "failed", "insufficient"):
        plan.add_node(
            TaskDAGNode(
                id=f"task-{status}",
                status=status,
                receipt_ids=[f"receipt-{status}"],
                claim_ids=[f"claim-{status}"],
                trace_ids=[f"trace-{status}"],
            )
        )

    payload = task_dag_plan_to_dict(plan)
    readback = build_task_dag_plan_readback(plan)
    text = repr({"payload": payload, "readback": readback})

    assert readback["summary"]["statusCounts"] == {
        "failed": 1,
        "insufficient": 1,
        "succeeded": 1,
    }
    for forbidden in (
        "verifiedFlags",
        "verification_decision",
        "verifierProof",
        "level=\"verified\"",
        "level='verified'",
    ):
        assert forbidden not in text


def test_p4b2_task_dag_plan_module_has_no_proof_write_tokens() -> None:
    from pathlib import Path

    path = Path("flaghunter/agents/pa_agent/task_dag_plan.py")
    text = path.read_text(encoding="utf-8")
    forbidden_tokens = {
        "upgrade_claim_to_verified",
        "append_verification_record",
        "build_verification_decision_event",
        "verification_decision",
        "add_flag(",
        'level="verified"',
        "level='verified'",
        "verified_flags",
    }

    offenders = sorted(token for token in forbidden_tokens if token in text)

    assert offenders == []
