from __future__ import annotations

from dataclasses import asdict

import pytest

from flaghunter.agents.base_agent import AgentMessage
from flaghunter.agents.pa_agent.context_assembler import ContextAssembler
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.solve_node import SolveNodeReceipt
from flaghunter.agents.pa_agent.task_dag_local_caller import (
    local_dag_apply_receipt,
    local_dag_start_next,
)
from flaghunter.agents.pa_agent.task_dag_outcome_source import (
    TaskDAGOutcomeSourceError,
    build_manual_task_dag_outcome,
    manual_task_dag_outcome_from_dict,
)
from flaghunter.agents.pa_agent.task_dag_plan import (
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
    task_dag_plan_to_dict,
)
from flaghunter.agents.pa_agent.task_dag_receipt_factory import (
    TaskDAGReceiptOutcome,
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
            AgentMessage(role="user", content="continue from DAG outcome source")
        ]


def _ready_plan() -> TaskDAGPlan:
    plan = TaskDAGPlan(id="plan-outcome")
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


def test_p4b4n_empty_dict_input_rejects() -> None:
    for bad in (None, {}):
        with pytest.raises(TaskDAGOutcomeSourceError):
            manual_task_dag_outcome_from_dict(bad)


def test_p4b4n_missing_or_empty_task_id_rejects() -> None:
    for bad in ("", "   "):
        with pytest.raises(TaskDAGOutcomeSourceError, match="task_id"):
            build_manual_task_dag_outcome(task_id=bad)
    with pytest.raises(TaskDAGOutcomeSourceError, match="task_id"):
        manual_task_dag_outcome_from_dict({"status": "completed"})


def test_p4b4n_minimal_completed_outcome_is_stripped_and_compact() -> None:
    outcome = build_manual_task_dag_outcome(
        task_id=" task-a ",
        solve_node_id=" node-a ",
        task_brief_id=" brief-a ",
        run_id=" run-a ",
        status=" completed ",
        output_summary=" completed compactly ",
        metadata={"outcome_kind": " manual ", "source_kind": " fixture "},
    )

    assert isinstance(outcome, TaskDAGReceiptOutcome)
    assert outcome.task_id == "task-a"
    assert outcome.solve_node_id == "node-a"
    assert outcome.task_brief_id == "brief-a"
    assert outcome.run_id == "run-a"
    assert outcome.status == "completed"
    assert outcome.output_summary == "completed compactly"
    assert outcome.metadata == {
        "outcome_kind": "manual",
        "source_channel": "manual_task_dag_outcome_source",
        "source_kind": "fixture",
    }


def test_p4b4n_failed_outcome_preserves_bounded_error_fields() -> None:
    outcome = build_manual_task_dag_outcome(
        task_id="task-a",
        status="error",
        error_class="X" * 200,
        error_summary="password=error-password " + ("E" * 300),
    )
    text = repr(asdict(outcome))

    assert outcome.status == "failed"
    assert len(outcome.error_class) == 80
    assert len(outcome.error_summary) <= 160
    assert "<redacted>" in text
    assert "error-password" not in text


@pytest.mark.parametrize("status", ["partial", "blocked", "skipped"])
def test_p4b4n_canonical_non_success_statuses_are_accepted(status: str) -> None:
    outcome = build_manual_task_dag_outcome(task_id="task-a", status=status)

    assert outcome.status == status


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("success", "completed"),
        ("error", "failed"),
        ("insufficient", "partial"),
        ("no_evidence", "partial"),
    ],
)
def test_p4b4n_status_aliases_normalize_consistently_with_factory(
    status: str,
    expected: str,
) -> None:
    outcome = build_manual_task_dag_outcome(task_id="task-a", status=status)

    assert outcome.status == expected


def test_p4b4n_unknown_status_rejects_without_becoming_completed() -> None:
    with pytest.raises(TaskDAGOutcomeSourceError, match="invalid status"):
        build_manual_task_dag_outcome(task_id="task-a", status="future-success-ish")


def test_p4b4n_refs_and_warnings_are_deduped_bounded_and_redacted() -> None:
    outcome = build_manual_task_dag_outcome(
        task_id="task-a",
        trace_ids=["trace-a", "trace-a", "T" * 300],
        claim_ids=["claim-a", "claim-a", "C" * 300],
        artifact_refs=["file://loot/token=artifact-token", "file://loot/token=artifact-token"],
        warnings=["cookie=warn-cookie", "session=warn-session"] * 6,
    )
    text = repr(asdict(outcome))

    assert outcome.trace_ids == ["trace-a", "T" * 160]
    assert outcome.claim_ids == ["claim-a", "C" * 160]
    assert len(outcome.artifact_refs) == 1
    assert len(outcome.warnings) == 10
    assert all(len(item) <= 160 for item in outcome.trace_ids)
    assert all(len(item) <= 160 for item in outcome.claim_ids)
    assert all(len(item) <= 160 for item in outcome.artifact_refs)
    assert all(len(item) <= 160 for item in outcome.warnings)
    assert "<redacted>" in text
    for leaked in ("artifact-token", "warn-cookie", "warn-session"):
        assert leaked not in text


@pytest.mark.parametrize(
    "raw_key",
    [
        "stdout",
        "stderr",
        "body",
        "http_body",
        "raw_body",
        "raw_output",
        "prompt",
        "completion",
        "tool_result",
        "request",
        "response",
    ],
)
def test_p4b4n_raw_execution_fields_reject(raw_key: str) -> None:
    with pytest.raises(TaskDAGOutcomeSourceError, match="raw field"):
        manual_task_dag_outcome_from_dict(
            {"task_id": "task-a", "status": "partial", raw_key: "secret=raw-secret"}
        )


@pytest.mark.parametrize(
    "proof_key",
    [
        "verification_decision",
        "verified_flags",
        "verifierProof",
        "proof_level",
        "verificationRecordId",
        "verifiedFlag",
    ],
)
def test_p4b4n_proof_like_fields_reject(proof_key: str) -> None:
    with pytest.raises(TaskDAGOutcomeSourceError, match="proof-like field"):
        manual_task_dag_outcome_from_dict(
            {"task_id": "task-a", "status": "completed", proof_key: "verified"}
        )


def test_p4b4n_summaries_metadata_and_raw_markers_are_sanitized() -> None:
    outcome = build_manual_task_dag_outcome(
        task_id="task-a",
        output_summary="HTTP/1.1 200 OK\n<html>secret=body-secret</html>",
        error_summary="Authorization: Bearer error-auth " + ("E" * 300),
        metadata={
            "outcome_kind": "manual token=metadata-token",
            "source_kind": "fixture secret=source-secret",
            "raw_tool_result": "password=tool-password",
            "recovery": "switch",
            "dispatcher": "ctf_dispatcher",
            "verification_decision": "verified",
        },
    )
    text = repr(asdict(outcome))

    assert outcome.output_summary == "<redacted raw body>"
    assert len(outcome.error_summary) <= 160
    assert set(outcome.metadata) == {"outcome_kind", "source_channel", "source_kind"}
    for forbidden_key in (
        "raw_tool_result",
        "recovery",
        "dispatcher",
        "verification_decision",
    ):
        assert forbidden_key not in outcome.metadata
    for leaked in (
        "body-secret",
        "error-auth",
        "metadata-token",
        "source-secret",
        "tool-password",
        "ctf_dispatcher",
    ):
        assert leaked not in text


def test_p4b4n_source_returns_only_outcome_without_mutating_state() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    before = _state_snapshot(state)

    outcome = build_manual_task_dag_outcome(task_id="task-a", status="completed")

    assert isinstance(outcome, TaskDAGReceiptOutcome)
    assert not isinstance(outcome, SolveNodeReceipt)
    assert _state_snapshot(state) == before


@pytest.mark.parametrize(
    ("status", "expected_dag_status"),
    [
        ("completed", TaskDAGStatus.SUCCEEDED),
        ("failed", TaskDAGStatus.FAILED),
        ("partial", TaskDAGStatus.INSUFFICIENT),
    ],
)
def test_p4b4n_outcome_integrates_externally_through_factory_and_caller(
    status: str,
    expected_dag_status: TaskDAGStatus,
) -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    start = local_dag_start_next(state, plan=_ready_plan())
    outcome = build_manual_task_dag_outcome(
        task_id="task-a",
        solve_node_id=start.solve_node_id,
        task_brief_id=start.task_brief_id,
        status=status,
        output_summary=f"{status} compactly",
    )
    receipt = build_local_task_dag_receipt(outcome)

    result = local_dag_apply_receipt(state, "task-a", receipt)

    assert result.ok is True
    assert state.get_task_dag_plan().get_node("task-a").status is expected_dag_status


def test_p4b4n_readback_session_and_prompt_remain_compact(tmp_path) -> None:
    run_id = "run-p4b4n-compact"
    state = CTFState(target="http://ctf.local", goal="get flag")
    start = local_dag_start_next(state, plan=_ready_plan(), run_id=run_id)
    outcome = build_manual_task_dag_outcome(
        task_id="task-a",
        solve_node_id=start.solve_node_id,
        task_brief_id=start.task_brief_id,
        run_id=run_id,
        status="completed",
        output_summary="Authorization: Bearer outcome-auth",
        metadata={"outcome_kind": "manual token=metadata-token"},
    )
    receipt = build_local_task_dag_receipt(outcome)
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
        "outcome-auth",
        "metadata-token",
    ):
        assert forbidden not in prompt_text
