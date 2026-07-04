from __future__ import annotations

import json

import pytest

from flaghunter.agents.pa_agent.ctf_state import (
    CTFState,
    ClaimKind,
    ClaimLevel,
    VerificationDecision,
    VerificationMethod,
)
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher, SolveResult
from flaghunter.agents.pa_agent.coordinator import CTFCoordinator
from flaghunter.agents.pa_agent.verifier import CTFVerifier
from flaghunter.harness.checkpoint_store import CheckpointStore


def _enable_claims_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")


def _flag_claim(state: CTFState):
    return state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content="flag{manual_trace_check}",
        producer_type="verifier",
        producer_id="ctf_verifier",
        primary_trace_id="trace-without-receipt",
    )


def _last_verification_record(state: CTFState):
    assert state.verification_records_by_id
    return list(state.verification_records_by_id.values())[-1]


class _RuntimeSignalDispatcher:
    def __init__(self, state: CTFState):
        self.state = state
        self._notes_log = []
        self._ingress_handoff = {}
        self.finalized = []
        self.events = []
        self.verifier = CTFVerifier(runtime=None)

    def _record_session_event(self, event_type, payload):
        self.events.append((event_type, dict(payload or {})))

    def _write_checkpoint(self, label, payload):
        return None

    async def _observe_flag(self, flag, target, **kwargs):
        return await self.verifier.verify_flag(self.state, flag=flag, **kwargs)

    async def _finalize_solve_result(self, result):
        self.finalized.append(result)
        return result


class _Runtime:
    environment = None


class _StrategyMemory:
    def build_fingerprint(self, state):
        return type("Fingerprint", (), {"id": "p2-h-fingerprint"})()

    def build_entry(self, *, state, fingerprint, chain_used, solved):
        return type("Entry", (), {"id": "p2-h-entry"})()

    async def save(self, entry):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "decision", "setup"),
    [
        ("flag{p2_runtime_trace}", VerificationDecision.RUNTIME_SUPPORTED, "runtime"),
        ("flag{p2_verified_trace}", VerificationDecision.VERIFIED, "verified"),
        ("flag{p2_rejected_trace}", VerificationDecision.REJECTED, "rejected"),
    ],
)
async def test_p2_verifier_records_reference_real_receipt_trace(
    monkeypatch,
    flag: str,
    decision: VerificationDecision,
    setup: str,
) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    verifier = CTFVerifier(runtime=None)

    if setup == "verified":
        state.local_challenge_auto_verify = True
    if setup == "rejected":
        result = verifier.reject_flag(
            state,
            flag=flag,
            evidence_source="platform-submit",
            rationale="platform rejected flag",
        )
    else:
        result = await verifier.verify_flag(
            state,
            flag=flag,
            evidence_source="http-response",
            rationale="runtime evidence from target",
        )

    record = _last_verification_record(state)
    claim = state.claims_by_id[record.claim_id]
    trace = state.execution_traces_by_id[record.trace_id]

    assert record.decision == decision
    assert result.metadata["trace_id"] == trace.id
    assert result.metadata["receipt_id"] == trace.receipt_id
    assert claim.primary_trace_id == trace.id
    assert record.trace_id == trace.id
    assert record.metadata["receipt_id"] == trace.receipt_id
    assert trace.kind == "verification_receipt"
    assert trace.producer == "ctf_verifier"
    assert trace.success is (decision != VerificationDecision.REJECTED)
    assert trace.metadata["decision"] == result.decision
    assert trace.metadata["flag"] == flag


@pytest.mark.asyncio
async def test_p2_checkpoint_round_trip_preserves_verifier_trace_links(
    monkeypatch,
    tmp_path,
) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.local_challenge_auto_verify = True
    verifier = CTFVerifier(runtime=None)

    await verifier.verify_flag(
        state,
        flag="flag{p2_checkpoint_trace}",
        evidence_source="http-response",
        rationale="runtime evidence from target",
    )
    record = _last_verification_record(state)
    claim = state.claims_by_id[record.claim_id]
    trace = state.execution_traces_by_id[record.trace_id]

    store = CheckpointStore(tmp_path / "checkpoints")
    store.save_checkpoint(
        run_id="run-p2-trace",
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    restored = CTFState.from_snapshot(
        store.latest_checkpoint("run-p2-trace")["state"]
    )
    restored_claim = restored.get_claim(claim.id)
    restored_record = restored.verification_records_by_id[record.id]
    restored_trace = restored.execution_traces_by_id[trace.id]

    assert json.dumps(restored.to_snapshot())
    assert restored_claim is not None
    assert restored_claim.primary_trace_id == restored_trace.id
    assert restored_record.trace_id == restored_trace.id
    assert restored_record.metadata["receipt_id"] == restored_trace.receipt_id
    assert restored_trace.kind == "verification_receipt"
    assert restored_trace.metadata["decision"] == "verified"


@pytest.mark.asyncio
async def test_p2_existing_claim_primary_trace_moves_to_latest_receipt_trace(
    monkeypatch,
) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content="flag{p2_existing_claim_upgrade}",
        producer_type="solver",
        producer_id="legacy-source",
        primary_trace_id="legacy-synthetic-trace",
        confidence=0.3,
    )
    verifier = CTFVerifier(runtime=None)

    runtime = await verifier.verify_flag(
        state,
        flag="flag{p2_existing_claim_upgrade}",
        evidence_source="http-response",
        rationale="runtime evidence from target",
    )
    runtime_record = _last_verification_record(state)
    runtime_trace = state.execution_traces_by_id[runtime_record.trace_id]

    assert runtime.decision == "runtime"
    assert claim.primary_trace_id == runtime_trace.id

    state.local_challenge_auto_verify = True
    verified = await verifier.verify_flag(
        state,
        flag="flag{p2_existing_claim_upgrade}",
        evidence_source="http-response",
        rationale="strong runtime evidence from local challenge",
    )
    verified_record = _last_verification_record(state)
    verified_trace = state.execution_traces_by_id[verified_record.trace_id]

    assert verified.decision == "verified"
    assert claim.primary_trace_id == verified_trace.id
    assert claim.metadata["verified_trace_id"] == verified_trace.id
    assert claim.metadata["verified_receipt_id"] == verified_trace.receipt_id
    assert claim.primary_trace_id != "legacy-synthetic-trace"


def test_p2_unbacked_verified_upgrade_is_not_marked_receipt_backed(
    monkeypatch,
) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    claim = _flag_claim(state)
    record = state.append_verification_record(
        claim.id,
        verifier_type="verifier",
        verifier_id="ctf_verifier",
        method=VerificationMethod.PLATFORM_SUBMIT,
        decision=VerificationDecision.VERIFIED,
        passed=True,
        sufficient_for_upgrade=True,
        trace_id="trace-without-receipt",
        rationale="legacy unit test style verification",
    )

    state.upgrade_claim_to_verified(
        claim.id,
        verification_record_id=record.id,
        verifier_id="ctf_verifier",
    )

    assert claim.level == ClaimLevel.VERIFIED
    assert record.trace_id not in state.execution_traces_by_id
    assert "verified_receipt_id" not in claim.metadata
    assert (
        claim.metadata["verified_trace_warning"]
        == "verification_record_trace_missing_receipt"
    )


@pytest.mark.asyncio
async def test_p2_control_runtime_signal_links_control_receipt_to_verifier_trace(
    monkeypatch,
) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    dispatcher = _RuntimeSignalDispatcher(state)
    hint = (
        "[control_decision]\n"
        "decisionKind=direct_execute\n"
        "nextAction=verify_runtime_signal\n"
        "driver=blackboard.runtime_flag\n"
        "runtimeFlag=flag{p2_control_runtime}"
    )

    result = await CTFCoordinator()._apply_runtime_signal_contract(
        dispatcher,
        target="http://ctf.local",
        hint=hint,
    )

    record = _last_verification_record(state)
    verification_trace = state.execution_traces_by_id[record.trace_id]
    control_traces = [
        trace
        for trace in state.execution_traces_by_id.values()
        if trace.kind == "control_receipt"
    ]

    assert result is None
    assert len(control_traces) == 1
    assert control_traces[0].producer == "control:verify_runtime_signal"
    assert verification_trace.metadata["control_trace_id"] == control_traces[0].id
    assert record.evidence_trace_ids == [control_traces[0].id]


@pytest.mark.asyncio
async def test_p2h_dispatcher_finalize_writes_stop_control_receipt(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    dispatcher = CTFTaskDispatcher(runtime=_Runtime(), progress_callback=None)
    dispatcher.strategy_memory = _StrategyMemory()  # type: ignore[assignment]
    dispatcher.state = CTFState(target="http://ctf.local", goal="get flag")
    trace = dispatcher.state.record_tool_receipt(
        tool_name="probe",
        output_summary="flag{candidate_stop}",
        success=True,
    )
    claim = dispatcher.state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content="flag{candidate_stop}",
        producer_type="tool",
        producer_id="probe",
        primary_trace_id=trace.id,
        level=ClaimLevel.CONJECTURE,
        evidence_trace_ids=[trace.id],
    )

    result = await dispatcher._finalize_solve_result(
        SolveResult(success=False, reason="no_progress", chain_used=["web"])
    )

    control_traces = [
        item
        for item in dispatcher.state.execution_traces_by_id.values()
        if item.kind.value == "control_receipt"
    ]
    assert result.success is False
    assert len(control_traces) == 1
    receipt = control_traces[0]
    assert dispatcher.state.get_execution_trace(receipt.id) is receipt
    assert receipt.producer == "control:stop"
    assert receipt.success is False
    assert receipt.metadata["stop_reason"] == "no_progress"
    assert receipt.metadata["finish_status"] == "insufficient"
    assert receipt.metadata["selected_claim_id"] == claim.id
    assert receipt.metadata["selected_trace_id"] == trace.id
    assert receipt.metadata["answer_kind"] == "solve_result"
    assert receipt.metadata["source_channel"] == "ctf_dispatcher"
    assert dispatcher.state.get_claim(claim.id).level == ClaimLevel.CONJECTURE
    assert dispatcher.state.verified_flags == []
