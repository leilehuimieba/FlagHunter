from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.coordinator import CTFCoordinator
from flaghunter.agents.pa_agent.ctf_state import CTFState, ClaimKind
from flaghunter.agents.pa_agent.flag_observer import FlagObserver
from flaghunter.agents.pa_agent.session_context import SessionContextView
from flaghunter.agents.pa_agent.verifier import CTFVerifier
from flaghunter.harness.checkpoint_store import CheckpointStore
from flaghunter.tools.executor import ToolExecutor
from flaghunter.tools.registry import Tool, ToolSchema


def _enable_claims_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")


def _last_verification_record(state: CTFState):
    return list(state.verification_records_by_id.values())[-1]


def _candidate_claim(state: CTFState, value: str):
    return state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content=value,
        producer_type="solver",
        producer_id="unit-test",
        primary_trace_id=f"legacy:{value}",
        confidence=0.2,
    )


def _tool_returning(output: str) -> Tool:
    async def fn(arguments: dict, runtime) -> str:
        return output

    return Tool(name="probe", description="", schema=ToolSchema(), execute_fn=fn)


async def _verified_state() -> tuple[CTFState, object, object]:
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.local_challenge_auto_verify = True
    verifier = CTFVerifier(runtime=None)
    await verifier.verify_flag(
        state,
        flag="flag{p2b_verified}",
        evidence_source="http-response",
        rationale="local challenge runtime flag",
    )
    record = _last_verification_record(state)
    claim = state.claims_by_id[record.claim_id]
    return state, claim, record


@pytest.mark.asyncio
async def test_p2b_claim_and_verification_trace_read_api(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state, claim, record = await _verified_state()

    claim_trace = state.get_claim_trace(claim.id)
    verification_trace = state.get_verification_trace(record.id)
    chain = state.get_claim_trace_chain(claim.id)

    assert claim_trace is not None
    assert claim_trace.id == claim.primary_trace_id
    assert verification_trace is not None
    assert verification_trace.id == record.trace_id
    assert chain["claim_id"] == claim.id
    assert chain["primary_trace"]["id"] == claim_trace.id
    assert chain["verification_traces"][0]["id"] == verification_trace.id
    assert chain["verification_traces"][0]["receipt_id"] == verification_trace.receipt_id


class _RuntimeSignalDispatcher:
    def __init__(self, state: CTFState):
        self.state = state
        self._notes_log = []
        self._ingress_handoff = {}
        self.verifier = CTFVerifier(runtime=None)
        self.finalized = []

    def _record_session_event(self, event_type, payload):
        return None

    def _write_checkpoint(self, label, payload):
        return None

    async def _observe_flag(self, flag, target, **kwargs):
        return await self.verifier.verify_flag(self.state, flag=flag, **kwargs)

    async def _finalize_solve_result(self, result):
        self.finalized.append(result)
        return result


@pytest.mark.asyncio
async def test_p2b_control_and_verification_trace_relation_is_readable(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    dispatcher = _RuntimeSignalDispatcher(state)
    hint = (
        "[control_decision]\n"
        "decisionKind=direct_execute\n"
        "nextAction=verify_runtime_signal\n"
        "driver=blackboard.runtime_flag\n"
        "runtimeFlag=flag{p2b_runtime_control}"
    )

    await CTFCoordinator()._apply_runtime_signal_contract(
        dispatcher,
        target="http://ctf.local",
        hint=hint,
    )
    record = _last_verification_record(state)
    claim = state.claims_by_id[record.claim_id]
    chain = state.get_claim_trace_chain(claim.id)

    assert chain["verification_traces"][0]["id"] == record.trace_id
    assert chain["verification_traces"][0]["evidence_trace_ids"]
    control_trace_id = chain["verification_traces"][0]["evidence_trace_ids"][0]
    control_trace = state.get_execution_trace(control_trace_id)
    verification_trace = state.get_verification_trace(record.id)
    assert control_trace is not None
    assert control_trace.kind == "control_receipt"
    assert verification_trace.metadata["control_trace_id"] == control_trace.id


@pytest.mark.asyncio
async def test_p2b_trace_read_api_survives_checkpoint_round_trip(
    monkeypatch,
    tmp_path,
) -> None:
    _enable_claims_v1(monkeypatch)
    state, claim, record = await _verified_state()
    store = CheckpointStore(tmp_path / "checkpoints")
    store.save_checkpoint(
        run_id="run-p2b",
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    restored = CTFState.from_snapshot(
        store.latest_checkpoint("run-p2b")["state"]
    )
    chain = restored.get_claim_trace_chain(claim.id)

    assert restored.get_claim_trace(claim.id).id == claim.primary_trace_id
    assert restored.get_verification_trace(record.id).id == record.trace_id
    assert chain["primary_trace"]["id"] == claim.primary_trace_id


@pytest.mark.asyncio
async def test_p2b_flag_observer_event_and_notes_include_trace_refs(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.local_challenge_auto_verify = True
    verifier = CTFVerifier(runtime=None)
    events = []
    notes = []

    async def _store_note(**kwargs):
        notes.append(kwargs)

    await FlagObserver().observe_flag(
        state,
        verifier=verifier,
        store_note=_store_note,
        record_session_event=lambda event_type, payload: events.append((event_type, payload)),
        hydrate_flag_proof=lambda *args, **kwargs: None,
        record_wrong_flag_feedback=lambda *args, **kwargs: None,
        active_hypothesis_context=SimpleNamespace(id="hyp-1", kind="web"),
        active_strategy_context=SimpleNamespace(kind="xss"),
        flag="flag{p2b_observer}",
        target="http://ctf.local",
        evidence_source="http-response",
        rationale="observer routed runtime flag",
    )
    record = _last_verification_record(state)
    trace = state.get_verification_trace(record.id)

    assert events
    assert events[0][0] == "verification_decision"
    assert events[0][1]["trace_id"] == trace.id
    assert events[0][1]["receipt_id"] == trace.receipt_id
    assert notes
    assert notes[0]["trace_id"] == trace.id
    assert notes[0]["receipt_id"] == trace.receipt_id


@pytest.mark.asyncio
async def test_p2b_session_context_surfaces_compact_trace_refs(
    monkeypatch,
    tmp_path,
) -> None:
    _enable_claims_v1(monkeypatch)
    state, claim, record = await _verified_state()
    workspace = tmp_path / "workspace"
    checkpoint_root = workspace / "loot" / "checkpoints"
    CheckpointStore(checkpoint_root).save_checkpoint(
        run_id="run-p2b-context",
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=workspace / "loot" / "session_ledgers",
        artifact_root=workspace / "loot" / "artifacts",
        checkpoint_root=checkpoint_root,
    ).build_run_context("run-p2b-context")

    trace_refs = context["latestCheckpoint"]["traceRefs"]
    assert trace_refs[0]["claimId"] == claim.id
    assert trace_refs[0]["primaryTraceId"] == claim.primary_trace_id
    assert trace_refs[0]["verificationTraceIds"] == [record.trace_id]
    assert context["resumeContext"]["traceRefs"] == trace_refs


def test_p2h_session_context_surfaces_completion_control_receipt(
    monkeypatch,
    tmp_path,
) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    receipt = state.record_execution_trace(
        kind="control_receipt",
        producer="control:finish",
        input_summary="mode=single action=complete step_id=1",
        output_summary="All steps complete",
        success=True,
        metadata={
            "stop_reason": "all_steps_complete",
            "finish_status": "answered",
            "selected_claim_id": "",
            "selected_verification_record_id": "",
            "selected_trace_id": "",
            "answer_kind": "plan_completion",
            "source_channel": "finish_tool",
        },
    )
    workspace = tmp_path / "workspace"
    checkpoint_root = workspace / "loot" / "checkpoints"
    CheckpointStore(checkpoint_root).save_checkpoint(
        run_id="run-p2h-context",
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=workspace / "loot" / "session_ledgers",
        artifact_root=workspace / "loot" / "artifacts",
        checkpoint_root=checkpoint_root,
    ).build_run_context("run-p2h-context")

    audit_export = context["latestCheckpoint"]["auditEvidenceExport"]
    control_export = next(
        item
        for item in audit_export["executionTraces"]
        if item["traceId"] == receipt.id
    )

    assert control_export["kind"] == "control_receipt"
    assert control_export["producer"] == "control:finish"
    assert control_export["metadata"]["finish_status"] == "answered"
    assert context["resumeContext"]["hasAuditEvidenceExport"] is True
    assert context["resumeContext"]["auditEvidenceSummary"]["executionTraceCount"] == 1


@pytest.mark.asyncio
async def test_p2b_claim_trace_refs_prefers_recently_updated_old_claim(
    monkeypatch,
) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    claims = [
        _candidate_claim(state, f"flag{{p2b_recent_{idx}}}")
        for idx in range(6)
    ]
    for idx, claim in enumerate(claims):
        claim.updated_at = float(idx + 1)
    verifier = CTFVerifier(runtime=None)

    await verifier.verify_flag(
        state,
        flag="flag{p2b_recent_0}",
        evidence_source="http-response",
        rationale="late runtime evidence for first claim",
    )
    refs = state.claim_trace_refs(limit=5)

    assert len(refs) == 5
    assert claims[0].id in [item["claimId"] for item in refs]
    assert claims[1].id not in [item["claimId"] for item in refs]
    assert refs[-1]["claimId"] == claims[0].id


def test_p2b_claim_trace_refs_non_positive_limit_returns_empty(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    _candidate_claim(state, "flag{p2b_limit}")

    assert state.claim_trace_refs(limit=0) == []
    assert state.claim_trace_refs(limit=-10) == []


@pytest.mark.asyncio
async def test_p2b_session_context_trace_refs_use_recent_update_selection(
    monkeypatch,
    tmp_path,
) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    claims = [
        _candidate_claim(state, f"flag{{p2b_context_recent_{idx}}}")
        for idx in range(6)
    ]
    for idx, claim in enumerate(claims):
        claim.updated_at = float(idx + 1)
    verifier = CTFVerifier(runtime=None)
    await verifier.verify_flag(
        state,
        flag="flag{p2b_context_recent_0}",
        evidence_source="http-response",
        rationale="late runtime evidence for first claim",
    )
    workspace = tmp_path / "workspace"
    checkpoint_root = workspace / "loot" / "checkpoints"
    CheckpointStore(checkpoint_root).save_checkpoint(
        run_id="run-p2b-selection",
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=workspace / "loot" / "session_ledgers",
        artifact_root=workspace / "loot" / "artifacts",
        checkpoint_root=checkpoint_root,
    ).build_run_context("run-p2b-selection")
    latest_refs = context["latestCheckpoint"]["traceRefs"]

    assert len(latest_refs) == 5
    assert claims[0].id in [item["claimId"] for item in latest_refs]
    assert claims[1].id not in [item["claimId"] for item in latest_refs]
    assert context["resumeContext"]["traceRefs"] == latest_refs


@pytest.mark.asyncio
async def test_p2d_tool_receipt_is_readable_and_links_candidate_evidence(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    runtime = type("RuntimeWithState", (), {"ctf_state": state})()
    executor = ToolExecutor(runtime=runtime)

    result = await executor.execute(_tool_returning("flag{tool_candidate_only}"), {})
    trace = state.get_execution_trace(result.trace_id)

    assert trace is not None
    assert trace.kind == "tool_receipt"
    assert trace.metadata["tool_name"] == "probe"
    assert trace.output_summary == "flag{tool_candidate_only}"
    # P2-D links scanner-discovered candidates to the tool receipt, but the
    # receipt remains evidence lineage only and cannot prove verification.
    claims = list(state.claims_by_id.values())
    assert len(claims) == 1
    assert claims[0].content == "flag{tool_candidate_only}"
    assert claims[0].kind.value == "flag_found"
    assert claims[0].level.value != "verified"
    assert claims[0].primary_trace_id == result.trace_id
    assert state.verified_flags == []


@pytest.mark.asyncio
async def test_p2e_claim_evidence_refs_surface_candidate_tool_receipt_safely(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    runtime = type("RuntimeWithState", (), {"ctf_state": state})()
    executor = ToolExecutor(runtime=runtime)

    first = await executor.execute(
        _tool_returning(
            "Set-Cookie: session=super-secret-cookie\n"
            "Authorization: Bearer top-secret-token\n"
            "flag{p2e_candidate}"
        ),
        {"url": "http://ctf.local/a"},
    )
    second = await executor.execute(
        _tool_returning("flag{p2e_candidate}"),
        {"url": "http://ctf.local/b"},
    )

    refs = state.claim_evidence_refs(limit=5)

    assert len(refs) == 1
    ref = refs[0]
    assert ref["contentPreview"] == "flag{p2e_candidate}"
    assert ref["kind"] == "flag_found"
    assert ref["level"] == "conjecture"
    assert ref["status"] == "active"
    assert ref["primaryTraceId"] == first.trace_id
    assert ref["sourceTool"] == "probe"
    assert ref["sourceTraceId"] == second.trace_id
    assert ref["sourceReceiptId"] == second.receipt_id
    assert first.trace_id in ref["evidenceTraceIds"]
    assert second.trace_id in ref["evidenceTraceIds"]
    assert len(ref["evidenceTraceIds"]) == len(set(ref["evidenceTraceIds"]))
    assert ref["primaryTrace"]["kind"] == "tool_receipt"
    assert ref["primaryTrace"]["producer"] == "tool:probe"
    assert ref["primaryTrace"]["success"] is True
    ref_text = repr(ref)
    assert "super-secret-cookie" not in ref_text
    assert "top-secret-token" not in ref_text
    assert "Set-Cookie" not in ref_text
    assert "Authorization" not in ref_text


@pytest.mark.asyncio
async def test_p2e_claim_evidence_refs_distinguish_candidate_and_verified(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    runtime = type("RuntimeWithState", (), {"ctf_state": state})()
    executor = ToolExecutor(runtime=runtime)
    await executor.execute(_tool_returning("flag{p2e_candidate_only}"), {})

    state.local_challenge_auto_verify = True
    verifier = CTFVerifier(runtime=None)
    await verifier.verify_flag(
        state,
        flag="flag{p2e_verified}",
        evidence_source="http-response",
        rationale="local challenge accepted",
    )

    refs = state.claim_evidence_refs(limit=10)
    by_content = {item["contentPreview"]: item for item in refs}

    assert by_content["flag{p2e_candidate_only}"]["level"] == "conjecture"
    assert by_content["flag{p2e_candidate_only}"]["latestVerificationDecision"] == ""
    assert by_content["flag{p2e_verified}"]["level"] == "verified"
    assert by_content["flag{p2e_verified}"]["latestVerificationDecision"] == "verified"
    assert by_content["flag{p2e_verified}"]["latestVerificationTraceId"]


def test_p2e_claim_evidence_refs_redact_non_flag_claim_content(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    trace = state.record_tool_receipt(
        tool_name="login_probe",
        arguments={"url": "http://ctf.local/login"},
        output_summary="credential check completed",
        success=True,
    )
    claim = state.create_claim(
        kind="credential_valid",
        content="username=admin password=super-secret-password token=top-secret-token",
        producer_type="tool",
        producer_id="login_probe",
        primary_trace_id=trace.id,
        level="conjecture",
        evidence_trace_ids=[trace.id],
        metadata={
            "source_tool": "login_probe",
            "source_trace_id": trace.id,
            "source_receipt_id": trace.receipt_id,
        },
    )

    refs = state.claim_evidence_refs(limit=5)
    ref = next(item for item in refs if item["claimId"] == claim.id)

    assert ref["kind"] == "credential_valid"
    assert "username=admin" in ref["contentPreview"]
    assert "super-secret-password" not in ref["contentPreview"]
    assert "top-secret-token" not in ref["contentPreview"]
    assert "password=<redacted>" in ref["contentPreview"]
    assert "token=<redacted>" in ref["contentPreview"]


def test_p2e_claim_evidence_refs_redact_jsonish_claim_and_trace_previews(
    monkeypatch,
) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    trace = state.record_execution_trace(
        kind="tool_receipt",
        producer="tool:legacy",
        output_summary=json.dumps({"token": "json-trace-token"}),
        success=True,
    )
    claim = state.create_claim(
        kind="credential_valid",
        content=json.dumps({"password": "json-claim-password"}),
        producer_type="tool",
        producer_id="legacy",
        primary_trace_id=trace.id,
        level="conjecture",
        evidence_trace_ids=[trace.id],
    )

    refs = state.claim_evidence_refs(limit=5)
    ref = next(item for item in refs if item["claimId"] == claim.id)
    ref_text = repr(ref)

    assert '{"password": "<redacted>"}' in ref["contentPreview"]
    assert "json-claim-password" not in ref_text
    assert "json-trace-token" not in ref_text


def test_p2e_claim_trace_refs_redact_non_flag_claim_content(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    trace = state.record_tool_receipt(
        tool_name="login_probe",
        arguments={"url": "http://ctf.local/login"},
        output_summary="credential check completed",
        success=True,
    )
    claim = state.create_claim(
        kind="credential_valid",
        content="username=admin password=super-secret-password token=top-secret-token",
        producer_type="tool",
        producer_id="login_probe",
        primary_trace_id=trace.id,
        level="conjecture",
        evidence_trace_ids=[trace.id],
    )

    refs = state.claim_trace_refs(limit=5)
    ref = next(item for item in refs if item["claimId"] == claim.id)

    assert ref["kind"] == "credential_valid"
    assert "username=admin" in ref["content"]
    assert "super-secret-password" not in ref["content"]
    assert "top-secret-token" not in ref["content"]
    assert "password=<redacted>" in ref["content"]
    assert "token=<redacted>" in ref["content"]


def test_p2e_claim_trace_refs_redact_jsonish_claim_content(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    trace = state.record_tool_receipt(
        tool_name="login_probe",
        output_summary="credential check completed",
        success=True,
    )
    claim = state.create_claim(
        kind="credential_valid",
        content=json.dumps({"secret": "json-claim-secret"}),
        producer_type="tool",
        producer_id="login_probe",
        primary_trace_id=trace.id,
        level="conjecture",
        evidence_trace_ids=[trace.id],
    )

    refs = state.claim_trace_refs(limit=5)
    ref = next(item for item in refs if item["claimId"] == claim.id)

    assert '{"secret": "<redacted>"}' in ref["content"]
    assert "json-claim-secret" not in repr(ref)
