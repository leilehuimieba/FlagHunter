from __future__ import annotations

import pytest

from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.evidence_snapshot import build_p2_evidence_snapshot
from flaghunter.agents.pa_agent.p3_solve_readback import build_p3_solve_readback
from flaghunter.agents.pa_agent.verifier import CTFVerifier
from flaghunter.tools.executor import ToolExecutor
from flaghunter.tools.registry import Tool, ToolSchema


def _enable_claims_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")


def _tool_returning(output: str, *, name: str = "probe") -> Tool:
    async def fn(arguments: dict, runtime) -> str:
        return output

    return Tool(name=name, description="", schema=ToolSchema(), execute_fn=fn)


def test_p2i_evidence_snapshot_none_state_has_stable_empty_shape() -> None:
    snapshot = build_p2_evidence_snapshot(None)
    empty_p3_solve_snapshot = build_p3_solve_readback(None)

    assert snapshot == {
        "schemaVersion": "p2.evidence_snapshot.v1",
        "traceRefs": [],
        "claimEvidenceRefs": [],
        "auditEvidenceExport": {
            "schemaVersion": "p2.audit_evidence.v1",
            "target": "",
            "goal": "",
            "stopReason": "",
            "summary": {
                "claimCount": 0,
                "exportedClaimCount": 0,
                "truncatedClaimCount": 0,
                "verificationRecordCount": 0,
                "exportedVerificationRecordCount": 0,
                "truncatedVerificationRecordCount": 0,
                "executionTraceCount": 0,
                "exportedExecutionTraceCount": 0,
                "truncatedExecutionTraceCount": 0,
                "candidateClaimCount": 0,
                "verifiedClaimCount": 0,
                "retractedClaimCount": 0,
            },
            "claims": [],
            "verificationRecords": [],
            "executionTraces": [],
            "p3SolveSnapshot": empty_p3_solve_snapshot,
        },
        "p3SolveSnapshot": empty_p3_solve_snapshot,
        "summary": {
            "claimCount": 0,
            "traceCount": 0,
            "verificationRecordCount": 0,
            "hasVerifiedClaim": False,
            "hasControlReceipt": False,
            "hasToolReceipt": False,
            "hasVerificationReceipt": False,
            "truncated": {
                "traceRefs": 0,
                "claimEvidenceRefs": 0,
                "auditClaims": 0,
                "auditTraces": 0,
                "auditVerificationRecords": 0,
            },
        },
    }


def test_p2i_evidence_snapshot_empty_state_has_stable_shape() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")

    snapshot = build_p2_evidence_snapshot(state)

    assert snapshot["schemaVersion"] == "p2.evidence_snapshot.v1"
    assert snapshot["traceRefs"] == []
    assert snapshot["claimEvidenceRefs"] == []
    assert snapshot["auditEvidenceExport"]["target"] == "http://ctf.local"
    assert snapshot["auditEvidenceExport"]["goal"] == "get flag"
    assert snapshot["summary"]["claimCount"] == 0
    assert snapshot["summary"]["traceCount"] == 0
    assert snapshot["summary"]["verificationRecordCount"] == 0
    assert snapshot["summary"]["hasVerifiedClaim"] is False
    assert snapshot["summary"]["hasControlReceipt"] is False


@pytest.mark.asyncio
async def test_p2i_evidence_snapshot_unifies_claim_trace_audit_models(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    runtime = type("RuntimeWithState", (), {"ctf_state": state})()
    executor = ToolExecutor(runtime=runtime)
    candidate_result = await executor.execute(
        _tool_returning("flag{snapshot_candidate}"),
        {"url": "http://ctf.local/"},
    )
    state.local_challenge_auto_verify = True
    await CTFVerifier(runtime=None).verify_flag(
        state,
        flag="flag{snapshot_verified}",
        evidence_source="http-response",
        rationale="local challenge accepted",
    )
    control_trace = state.record_execution_trace(
        kind="control_receipt",
        producer="control:finish",
        input_summary="action=complete",
        output_summary="All steps complete",
        success=True,
        metadata={
            "stop_reason": "all_steps_complete",
            "finish_status": "answered",
            "answer_kind": "plan_completion",
            "source_channel": "finish_tool",
        },
    )
    before_snapshot = state.to_snapshot()

    snapshot = build_p2_evidence_snapshot(state)
    claims_by_preview = {
        item["contentPreview"]: item
        for item in snapshot["claimEvidenceRefs"]
    }
    trace_kinds = {
        item["traceId"]: item["kind"]
        for item in snapshot["auditEvidenceExport"]["executionTraces"]
    }

    assert "flag{snapshot_candidate}" in claims_by_preview
    assert "flag{snapshot_verified}" in claims_by_preview
    assert claims_by_preview["flag{snapshot_candidate}"]["level"] == "conjecture"
    assert claims_by_preview["flag{snapshot_verified}"]["level"] == "verified"
    assert candidate_result.trace_id in [
        item["primaryTraceId"] for item in snapshot["traceRefs"]
    ]
    assert trace_kinds[candidate_result.trace_id] == "tool_receipt"
    assert control_trace.id in trace_kinds
    assert trace_kinds[control_trace.id] == "control_receipt"
    assert "verification_receipt" in trace_kinds.values()
    assert snapshot["summary"]["claimCount"] == 2
    assert snapshot["summary"]["traceCount"] == 3
    assert snapshot["summary"]["verificationRecordCount"] == 1
    assert snapshot["summary"]["hasVerifiedClaim"] is True
    assert snapshot["summary"]["hasControlReceipt"] is True
    assert snapshot["summary"]["hasToolReceipt"] is True
    assert snapshot["summary"]["hasVerificationReceipt"] is True
    assert state.to_snapshot() == before_snapshot


def test_p2i_evidence_snapshot_limits_and_truncation(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    for index in range(3):
        trace = state.record_tool_receipt(
            tool_name=f"probe_{index}",
            output_summary=f"flag{{snapshot_limit_{index}}}",
            success=True,
        )
        state.create_claim(
            kind="flag_found",
            content=f"flag{{snapshot_limit_{index}}}",
            producer_type="tool",
            producer_id=f"probe_{index}",
            primary_trace_id=trace.id,
            level="conjecture",
            evidence_trace_ids=[trace.id],
        )

    snapshot = build_p2_evidence_snapshot(
        state,
        trace_ref_limit=1,
        claim_evidence_limit=1,
        audit_claim_limit=1,
        audit_trace_limit=1,
        audit_verification_record_limit=1,
    )

    assert len(snapshot["traceRefs"]) == 1
    assert len(snapshot["claimEvidenceRefs"]) == 1
    assert len(snapshot["auditEvidenceExport"]["claims"]) == 1
    assert len(snapshot["auditEvidenceExport"]["executionTraces"]) == 1
    assert snapshot["summary"]["claimCount"] == 3
    assert snapshot["summary"]["traceCount"] == 3
    assert snapshot["summary"]["truncated"] == {
        "traceRefs": 2,
        "claimEvidenceRefs": 2,
        "auditClaims": 2,
        "auditTraces": 2,
        "auditVerificationRecords": 0,
    }


@pytest.mark.asyncio
async def test_p2i_evidence_snapshot_reuses_safe_read_models_for_redaction(
    monkeypatch,
) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(
        target="http://ctf.local/?token=target-token",
        goal="login with password=goal-password token=goal-token",
    )
    runtime = type("RuntimeWithState", (), {"ctf_state": state})()
    executor = ToolExecutor(runtime=runtime)
    await executor.execute(
        _tool_returning(
            "Set-Cookie: session=super-secret-cookie\n"
            "Authorization: Bearer top-secret-token\n"
            "flag{snapshot_redacted}"
        ),
        {"url": "http://ctf.local/"},
    )
    trace = state.record_execution_trace(
        kind="control_receipt",
        producer="control:finish",
        input_summary="password=input-password token=input-token",
        output_summary=(
            "Cookie: session=control-cookie\n"
            "Authorization: Bearer control-token\n"
            "secret=control-secret password=control-password"
        ),
        success=True,
        artifact_refs=["file://loot/token=artifact-token.txt"],
        metadata={
            "stop_reason": "done with secret=metadata-secret",
            "finish_status": "answered",
            "source_channel": "finish_tool",
            "token": "metadata-token",
        },
    )
    state.create_claim(
        kind="credential_valid",
        content="username=admin password=claim-password token=claim-token",
        producer_type="tool",
        producer_id="manual",
        primary_trace_id=trace.id,
        level="conjecture",
        evidence_trace_ids=[trace.id],
    )

    snapshot = build_p2_evidence_snapshot(state)
    snapshot_text = repr(snapshot)

    for leaked in (
        "target-token",
        "goal-password",
        "goal-token",
        "super-secret-cookie",
        "top-secret-token",
        "input-password",
        "input-token",
        "control-cookie",
        "control-token",
        "control-secret",
        "control-password",
        "artifact-token",
        "metadata-secret",
        "metadata-token",
        "claim-password",
        "claim-token",
        "Set-Cookie",
        "Authorization",
    ):
        assert leaked not in snapshot_text


def test_p2i_evidence_snapshot_read_only_with_claims_flag_off(monkeypatch) -> None:
    monkeypatch.delenv("FLAGHUNTER_CTF_CLAIMS_V1", raising=False)
    state = CTFState(target="http://ctf.local", goal="get flag")
    before = state.to_snapshot()

    snapshot = build_p2_evidence_snapshot(state)

    assert snapshot["summary"]["claimCount"] == 0
    assert state.to_snapshot() == before
