"""P2-H completion/control receipt coverage for the finish tool."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.tools.finish import PlanStep, TaskPlan, finish


def _enable_claims_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")


@dataclass
class _Runtime:
    plan: TaskPlan
    ctf_state: CTFState | None = None
    target: str = "http://ctf.local"


@pytest.mark.asyncio
async def test_finish_complete_with_ctf_state_writes_control_receipt(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    monkeypatch.setenv("CPA_M3_REPORTER", "false")
    state = CTFState(target="http://ctf.local", goal="get flag")
    tool_trace = state.record_tool_receipt(
        tool_name="probe",
        arguments={"url": "http://ctf.local/"},
        output_summary="flag{candidate_only}",
        success=True,
    )
    claim = state.create_claim(
        kind="flag_found",
        content="flag{candidate_only}",
        producer_type="tool",
        producer_id="probe",
        primary_trace_id=tool_trace.id,
        evidence_trace_ids=[tool_trace.id],
        level="conjecture",
    )
    runtime = _Runtime(
        plan=TaskPlan(steps=[PlanStep(id=1, description="Deliver answer")]),
        ctf_state=state,
    )

    result = await finish(
        {
            "action": "complete",
            "step_id": 1,
            "result": (
                "answered with password=finish-password token=finish-token "
                "Cookie: session=finish-cookie"
            ),
        },
        runtime,
    )

    control_traces = [
        trace
        for trace in state.execution_traces_by_id.values()
        if trace.kind.value == "control_receipt"
    ]
    assert "All steps complete" in result
    assert len(control_traces) == 1
    receipt = control_traces[0]
    assert state.get_execution_trace(receipt.id) is receipt
    assert receipt.producer == "control:finish"
    assert receipt.success is True
    assert receipt.metadata["stop_reason"] == "all_steps_complete"
    assert receipt.metadata["finish_status"] == "answered"
    assert receipt.metadata["selected_claim_id"] == claim.id
    assert receipt.metadata["selected_trace_id"] == tool_trace.id
    assert receipt.metadata["answer_kind"] == "plan_completion"
    assert receipt.metadata["source_channel"] == "finish_tool"
    receipt_text = repr(receipt)
    assert "finish-password" not in receipt_text
    assert "finish-token" not in receipt_text
    assert "finish-cookie" not in receipt_text
    assert state.get_claim(claim.id).level.value == "conjecture"
    assert state.verified_flags == []


@pytest.mark.asyncio
async def test_finish_without_ctf_state_keeps_legacy_behavior(monkeypatch) -> None:
    monkeypatch.setenv("CPA_M3_REPORTER", "false")
    runtime = _Runtime(
        plan=TaskPlan(steps=[PlanStep(id=1, description="Deliver answer")]),
        ctf_state=None,
    )

    result = await finish(
        {"action": "complete", "step_id": 1, "result": "done"},
        runtime,
    )

    assert result == "Step 1 complete\nResult: done\nAll steps complete"
