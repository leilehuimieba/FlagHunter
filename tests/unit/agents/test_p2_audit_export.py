from __future__ import annotations

import json

import pytest

from flaghunter.agents.pa_agent.audit_views import build_audit_evidence_export
from flaghunter.agents.pa_agent.ctf_state import CTFState
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


@pytest.mark.asyncio
async def test_p2f_audit_export_includes_claims_records_and_traces(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    runtime = type("RuntimeWithState", (), {"ctf_state": state})()
    executor = ToolExecutor(runtime=runtime)
    candidate_result = await executor.execute(
        _tool_returning("flag{audit_candidate}"),
        {"url": "http://ctf.local/"},
    )
    state.local_challenge_auto_verify = True
    await CTFVerifier(runtime=None).verify_flag(
        state,
        flag="flag{audit_verified}",
        evidence_source="http-response",
        rationale="local challenge accepted",
    )

    export = build_audit_evidence_export(state)
    claims = {item["contentPreview"]: item for item in export["claims"]}
    records = export["verificationRecords"]
    traces = {item["traceId"]: item for item in export["executionTraces"]}

    assert export["schemaVersion"] == "p2.audit_evidence.v1"
    assert export["target"] == "http://ctf.local"
    assert export["goal"] == "get flag"
    assert claims["flag{audit_candidate}"]["level"] == "conjecture"
    assert claims["flag{audit_candidate}"]["status"] == "active"
    assert claims["flag{audit_candidate}"]["latestVerificationDecision"] == ""
    assert claims["flag{audit_candidate}"]["primaryTraceId"] == candidate_result.trace_id
    assert candidate_result.trace_id in claims["flag{audit_candidate}"]["evidenceTraceIds"]
    assert claims["flag{audit_verified}"]["level"] == "verified"
    assert claims["flag{audit_verified}"]["latestVerificationDecision"] == "verified"
    assert records
    assert any(item["decision"] == "verified" and item["passed"] is True for item in records)
    assert candidate_result.trace_id in traces
    assert traces[candidate_result.trace_id]["kind"] == "tool_receipt"
    assert traces[candidate_result.trace_id]["producer"] == "tool:probe"
    assert traces[candidate_result.trace_id]["success"] is True


def test_p2f_audit_export_redacts_sensitive_content_and_allowlists_metadata(
    monkeypatch,
) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(
        target="http://ctf.local/?token=target-token",
        goal="login with password=goal-password token=goal-token",
    )
    state.stop_reason = "stopped because secret=stop-secret"
    trace = state.record_tool_receipt(
        tool_name="login_probe",
        arguments={"url": "http://ctf.local/login"},
        output_summary=(
            "HTTP/1.1 200 OK\n"
            "Set-Cookie: session=super-secret-cookie\n"
            "Authorization: Bearer top-secret-token\n"
            "password=output-password token=output-token"
        ),
        success=False,
        artifact_refs=[
            "file://loot/password=artifact-password.txt",
            "http://ctf.local/artifact?token=artifact-token",
        ],
        metadata={
            "tool_name": "login_probe",
            "status": "error",
            "error_class": "auth",
            "duration_ms": 12.5,
            "cache_hit": False,
            "secret": "metadata-secret",
            "headers": {"Authorization": "Bearer metadata-token"},
        },
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

    export = build_audit_evidence_export(state)
    claim_export = next(item for item in export["claims"] if item["claimId"] == claim.id)
    trace_export = next(item for item in export["executionTraces"] if item["traceId"] == trace.id)
    export_text = repr(export)

    assert claim_export["contentPreview"] == (
        "username=admin password=<redacted> token=<redacted>"
    )
    assert export["target"] == "http://ctf.local/?token=<redacted>"
    assert export["goal"] == "login with password=<redacted> token=<redacted>"
    assert export["stopReason"] == "stopped because secret=<redacted>"
    assert trace_export["outputPreview"]
    assert trace_export["artifactRefs"] == [
        "file://loot/password=<redacted>",
        "http://ctf.local/artifact?token=<redacted>",
    ]
    assert trace_export["metadata"] == {
        "tool_name": "login_probe",
        "status": "error",
        "error_class": "auth",
        "duration_ms": 12.5,
        "cache_hit": False,
    }
    for secret in (
        "super-secret-password",
        "top-secret-token",
        "super-secret-cookie",
        "output-password",
        "output-token",
        "metadata-secret",
        "metadata-token",
        "target-token",
        "goal-password",
        "goal-token",
        "stop-secret",
        "artifact-password",
        "artifact-token",
        "Set-Cookie",
        "Authorization",
    ):
        assert secret not in export_text


def test_p2f_audit_export_redacts_jsonish_sensitive_trace_fields(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    trace = state.record_execution_trace(
        kind="tool_receipt",
        producer="tool:legacy",
        output_summary=json.dumps(
            {
                "token": "json-output-token",
                "password": "json-output-password",
            }
        ),
        success=False,
        artifact_refs=[
            json.dumps({"secret": "json-artifact-secret"}),
            "http://ctf.local/a?api_key=json-artifact-key",
        ],
        metadata={
            "status": json.dumps({"authorization": "Bearer json-status-auth"}),
            "error_class": json.dumps({"cookie": "json-error-cookie"}),
            "stop_reason": json.dumps({"session": "json-stop-session"}),
            "source_channel": "legacy",
        },
    )

    export = build_audit_evidence_export(state)
    exported_trace = next(
        item for item in export["executionTraces"] if item["traceId"] == trace.id
    )
    export_text = repr(export)

    assert exported_trace["outputPreview"]
    assert exported_trace["metadata"]["source_channel"] == "legacy"
    for leaked in (
        "json-output-token",
        "json-output-password",
        "json-artifact-secret",
        "json-artifact-key",
        "json-status-auth",
        "json-error-cookie",
        "json-stop-session",
    ):
        assert leaked not in export_text


def test_p2h_audit_export_includes_redacted_control_receipt_without_claim_upgrade(
    monkeypatch,
) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    tool_trace = state.record_tool_receipt(
        tool_name="probe",
        output_summary="flag{audit_control_candidate}",
        success=True,
    )
    claim = state.create_claim(
        kind="flag_found",
        content="flag{audit_control_candidate}",
        producer_type="tool",
        producer_id="probe",
        primary_trace_id=tool_trace.id,
        level="conjecture",
        evidence_trace_ids=[tool_trace.id],
    )
    control_trace = state.record_execution_trace(
        kind="control_receipt",
        producer="control:finish",
        input_summary="action=complete step_id=1 password=input-password",
        output_summary=(
            "answered without proof\n"
            "Cookie: session=control-cookie\n"
            "Authorization: Bearer control-token\n"
            "secret=control-secret password=control-password"
        ),
        success=True,
        artifact_refs=["file://loot/token=artifact-token.txt"],
        metadata={
            "stop_reason": "all_steps_complete",
            "finish_status": "answered",
            "selected_claim_id": claim.id,
            "selected_trace_id": tool_trace.id,
            "selected_verification_record_id": "",
            "answer_kind": "plan_completion",
            "source_channel": "finish_tool",
            "token": "metadata-token",
            "Authorization": "Bearer metadata-authorization",
        },
    )

    export = build_audit_evidence_export(state)
    exported_trace = next(
        item
        for item in export["executionTraces"]
        if item["traceId"] == control_trace.id
    )
    exported_claim = next(item for item in export["claims"] if item["claimId"] == claim.id)
    export_text = repr(export)

    assert exported_trace["kind"] == "control_receipt"
    assert exported_trace["producer"] == "control:finish"
    assert exported_trace["metadata"] == {
        "answer_kind": "plan_completion",
        "finish_status": "answered",
        "selected_claim_id": claim.id,
        "selected_trace_id": tool_trace.id,
        "selected_verification_record_id": "",
        "source_channel": "finish_tool",
        "stop_reason": "all_steps_complete",
    }
    assert exported_claim["level"] == "conjecture"
    assert exported_claim["latestVerificationDecision"] == ""
    assert state.get_claim(claim.id).level.value == "conjecture"
    assert state.verified_flags == []
    for secret in (
        "input-password",
        "control-cookie",
        "control-token",
        "control-secret",
        "control-password",
        "artifact-token",
        "metadata-token",
        "metadata-authorization",
        "Cookie",
        "Authorization",
    ):
        assert secret not in export_text


def test_p2f_audit_export_limits_and_reports_truncation(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    for idx in range(3):
        trace = state.record_tool_receipt(
            tool_name=f"probe_{idx}",
            output_summary=f"output {idx}",
            success=True,
        )
        state.create_claim(
            kind="flag_found",
            content=f"flag{{audit_limit_{idx}}}",
            producer_type="tool",
            producer_id=f"probe_{idx}",
            primary_trace_id=trace.id,
            level="conjecture",
            evidence_trace_ids=[trace.id],
        )

    export = build_audit_evidence_export(state, claim_limit=2, trace_limit=2)

    assert len(export["claims"]) == 2
    assert len(export["executionTraces"]) == 2
    assert export["summary"]["claimCount"] == 3
    assert export["summary"]["exportedClaimCount"] == 2
    assert export["summary"]["truncatedClaimCount"] == 1
    assert export["summary"]["executionTraceCount"] == 3
    assert export["summary"]["exportedExecutionTraceCount"] == 2
    assert export["summary"]["truncatedExecutionTraceCount"] == 1


def test_p2f_audit_export_empty_state_has_stable_shape() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")

    export = build_audit_evidence_export(state)
    empty_p3_solve_snapshot = build_p3_solve_readback(state, preview_limit=200)

    assert export == {
        "schemaVersion": "p2.audit_evidence.v1",
        "target": "http://ctf.local",
        "goal": "get flag",
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
    }
