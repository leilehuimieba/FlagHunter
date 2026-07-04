from __future__ import annotations

import json

import pytest

from flaghunter.agents.base_agent import AgentMessage
from flaghunter.agents.pa_agent.context_assembler import ContextAssembler
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.solve_node import (
    SolveNodeReceipt,
    build_solve_node_receipt_readback,
)
from flaghunter.agents.pa_agent.task_dag_local_caller import (
    local_dag_apply_receipt,
    local_dag_start_next,
)
from flaghunter.agents.pa_agent.task_dag_plan import (
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
    task_dag_plan_to_dict,
)
from flaghunter.agents.pa_agent.task_dag_receipt_factory import (
    TaskDAGReceiptFactoryError,
    TaskDAGReceiptOutcome,
    build_local_task_dag_receipt,
    task_dag_receipt_outcome_from_dict,
    task_dag_receipt_outcome_to_dict,
)
from flaghunter.harness.checkpoint_store import CheckpointStore


class _StubAgent:
    def __init__(self, *, project_root, run_id: str):
        self.target = "http://ctf.local"
        self.rag_engine = None
        self.run_id = run_id
        self.project_root = project_root
        self.conversation_history = [
            AgentMessage(role="user", content="continue from DAG receipt factory")
        ]


def _ready_plan() -> TaskDAGPlan:
    plan = TaskDAGPlan(id="plan-factory")
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            kind="exploit",
            title="Exploit upload",
            goal="Run upload primitive",
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


def test_p4b4l_empty_outcome_rejects() -> None:
    for bad in (None, {}):
        with pytest.raises(TaskDAGReceiptFactoryError):
            build_local_task_dag_receipt(bad)


def test_p4b4l_minimal_completed_outcome_builds_sanitized_receipt() -> None:
    outcome = TaskDAGReceiptOutcome(
        task_id=" task-a ",
        solve_node_id=" node-a ",
        task_brief_id=" brief-a ",
        run_id=" run-a ",
        status="completed",
        output_summary="completed compactly",
        trace_ids=["trace-a"],
        claim_ids=["claim-a"],
        metadata={"outcome_kind": "manual"},
    )

    receipt = build_local_task_dag_receipt(outcome)

    assert isinstance(receipt, SolveNodeReceipt)
    assert receipt.id
    assert receipt.node_id == "node-a"
    assert receipt.input_brief_id == "brief-a"
    assert receipt.run_id == "run-a"
    assert receipt.worker_id == "local_task_dag"
    assert receipt.worker_type == "manual_local_task_dag"
    assert receipt.status == "completed"
    assert receipt.output_summary == "completed compactly"
    assert receipt.trace_ids == ["trace-a"]
    assert receipt.claim_ids == ["claim-a"]
    assert receipt.metadata == {
        "adapter_version": "p4.task_dag_receipt_factory.v1",
        "outcome_kind": "manual",
        "source_channel": "task_dag_receipt_factory",
        "task_dag_task_id": "task-a",
        "warning_count": 0,
    }


def test_p4b4l_failed_outcome_bounds_error_fields() -> None:
    receipt = build_local_task_dag_receipt(
        {
            "task_id": "task-a",
            "solve_node_id": "node-a",
            "status": "error",
            "error_class": "X" * 200,
            "error_summary": "failed with secret=error-secret " + ("E" * 300),
        }
    )
    text = repr(receipt.to_dict())

    assert receipt.status == "failed"
    assert len(receipt.error_class) == 80
    assert len(receipt.error_summary) <= 160
    assert "<redacted>" in text
    assert "error-secret" not in text


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("partial", "partial"),
        ("insufficient", "partial"),
        ("no_evidence", "partial"),
        ("blocked", "blocked"),
        ("skipped", "skipped"),
        ("success", "completed"),
    ],
)
def test_p4b4l_status_aliases_map_to_canonical_receipt_status(
    status: str,
    expected: str,
) -> None:
    receipt = build_local_task_dag_receipt(
        {
            "task_id": "task-a",
            "solve_node_id": "node-a",
            "status": status,
        }
    )

    assert receipt.status == expected


def test_p4b4l_unknown_status_rejects_without_becoming_completed() -> None:
    with pytest.raises(TaskDAGReceiptFactoryError, match="invalid status"):
        build_local_task_dag_receipt(
            {
                "task_id": "task-a",
                "status": "future-success-ish",
            }
        )


def test_p4b4l_redacts_truncates_and_dedupes_refs_and_metadata() -> None:
    receipt = build_local_task_dag_receipt(
        TaskDAGReceiptOutcome(
            task_id="task-a",
            solve_node_id="node-a",
            status="failed",
            output_summary="Authorization: Bearer output-auth token=output-token "
            + ("O" * 300),
            error_summary="password=error-password secret=error-secret " + ("E" * 300),
            artifact_refs=[
                "file://loot/password=artifact-pass.txt",
                "file://loot/password=artifact-pass.txt",
                "A" * 300,
            ],
            trace_ids=["trace-a", "trace-a", "T" * 300],
            claim_ids=["claim-a", "claim-a", "C" * 300],
            warnings=["cookie=warn-cookie", "session=warn-session"] * 6,
            metadata={
                "outcome_kind": "manual token=metadata-token",
                "raw_tool_result": {"secret": "metadata-secret"},
                "verification_decision": "verified",
                "recovery": "switch-chain",
                "nested": {"password": "nested-password"},
                "long_value": "L" * 300,
            },
        )
    )
    text = repr({"receipt": receipt.to_dict(), "readback": build_solve_node_receipt_readback([receipt])})

    assert len(receipt.output_summary) <= 160
    assert len(receipt.error_summary) <= 160
    assert len(receipt.artifact_refs) == 2
    assert len(receipt.trace_ids) == 2
    assert len(receipt.claim_ids) == 2
    assert all(len(item) <= 160 for item in receipt.artifact_refs)
    assert all(len(item) <= 160 for item in receipt.trace_ids)
    assert all(len(item) <= 160 for item in receipt.claim_ids)
    assert receipt.metadata["warning_count"] == 10
    assert "raw_tool_result" not in receipt.metadata
    assert "verification_decision" not in receipt.metadata
    assert "recovery" not in receipt.metadata
    assert "nested" not in receipt.metadata
    assert "<redacted>" in text
    for leaked in (
        "output-auth",
        "output-token",
        "error-password",
        "error-secret",
        "artifact-pass",
        "warn-cookie",
        "warn-session",
        "metadata-token",
        "metadata-secret",
        "nested-password",
    ):
        assert leaked not in text


def test_p4b4l_raw_execution_fields_are_ignored_or_compacted() -> None:
    receipt = build_local_task_dag_receipt(
        {
            "task_id": "task-a",
            "solve_node_id": "node-a",
            "status": "partial",
            "output_summary": "HTTP/1.1 200 OK\n<html>secret=body-secret</html>",
            "error_summary": "PING 127.0.0.1\n64 bytes from 127.0.0.1",
            "stdout": "uid=33(www-data) token=stdout-token",
            "stderr": "gid=33(www-data) secret=stderr-secret",
            "body": json.dumps({"authorization": "Bearer body-auth"}) * 50,
            "prompt": "password=prompt-password",
            "completion": "api_key=completion-key",
        }
    )
    text = repr(receipt.to_dict())

    assert receipt.output_summary == "<redacted raw body>"
    assert receipt.error_summary == "<redacted raw body>"
    assert "uid=33" not in text
    assert "gid=33" not in text
    for leaked in (
        "body-secret",
        "stdout-token",
        "stderr-secret",
        "body-auth",
        "prompt-password",
        "completion-key",
    ):
        assert leaked not in text


def test_p4b4l_outcome_dict_round_trip_preserves_allowlisted_shape() -> None:
    outcome = task_dag_receipt_outcome_from_dict(
        {
            "task_id": "task-a",
            "solve_node_id": "node-a",
            "task_brief_id": "brief-a",
            "status": "completed",
            "trace_ids": "trace-a",
            "claim_ids": ["claim-a", None, ""],
            "artifact_refs": ("artifact-a",),
            "unknown": "ignored",
        }
    )
    payload = task_dag_receipt_outcome_to_dict(outcome)

    assert payload["task_id"] == "task-a"
    assert payload["solve_node_id"] == "node-a"
    assert payload["task_brief_id"] == "brief-a"
    assert payload["status"] == "completed"
    assert payload["trace_ids"] == ["trace-a"]
    assert payload["claim_ids"] == ["claim-a"]
    assert payload["artifact_refs"] == ["artifact-a"]
    assert "unknown" not in payload


def test_p4b4l_factory_returns_receipt_without_mutating_state() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    before = _state_snapshot(state)

    receipt = build_local_task_dag_receipt(
        {
            "task_id": "task-a",
            "solve_node_id": "node-a",
            "status": "completed",
        }
    )

    assert isinstance(receipt, SolveNodeReceipt)
    assert _state_snapshot(state) == before


@pytest.mark.parametrize(
    ("status", "expected_dag_status"),
    [
        ("completed", TaskDAGStatus.SUCCEEDED),
        ("failed", TaskDAGStatus.FAILED),
        ("partial", TaskDAGStatus.INSUFFICIENT),
    ],
)
def test_p4b4l_generated_receipt_integrates_through_local_caller(
    status: str,
    expected_dag_status: TaskDAGStatus,
) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    start = local_dag_start_next(state, plan=_ready_plan())
    receipt = build_local_task_dag_receipt(
        {
            "task_id": "task-a",
            "solve_node_id": start.solve_node_id,
            "task_brief_id": start.task_brief_id,
            "status": status,
            "output_summary": f"{status} compactly",
        }
    )

    result = local_dag_apply_receipt(state, "task-a", receipt)

    assert result.ok is True
    assert state.get_task_dag_plan().get_node("task-a").status is expected_dag_status


def test_p4b4l_readback_session_and_prompt_remain_compact(tmp_path) -> None:
    run_id = "run-p4b4l-compact"
    state = CTFState(target="http://ctf.local", goal="get flag")
    start = local_dag_start_next(state, plan=_ready_plan(), run_id=run_id)
    receipt = build_local_task_dag_receipt(
        {
            "task_id": "task-a",
            "solve_node_id": start.solve_node_id,
            "task_brief_id": start.task_brief_id,
            "run_id": run_id,
            "status": "completed",
            "output_summary": "Authorization: Bearer receipt-auth",
            "metadata": {"outcome_kind": "manual token=metadata-token"},
        }
    )
    local_dag_apply_receipt(state, "task-a", receipt)
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    prompt_text = ContextAssembler(
        _StubAgent(project_root=tmp_path, run_id=run_id)
    ).assemble()

    assert "node_receipts=1" in prompt_text
    assert "task_dag_statuses=succeeded:1" in prompt_text
    for forbidden in (
        "taskDagPlanReadback",
        "task_dag_plan",
        "task-a",
        "receipt-auth",
        "metadata-token",
    ):
        assert forbidden not in prompt_text
