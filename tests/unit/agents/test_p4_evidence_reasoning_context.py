from __future__ import annotations

import json
from pathlib import Path

import pytest

from flaghunter.agents.base_agent import AgentMessage
from flaghunter.agents.pa_agent.context_assembler import ContextAssembler
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.reasoning_evidence_context import (
    build_evidence_reasoning_context,
)
from flaghunter.agents.pa_agent.session_context import SessionContextView
from flaghunter.agents.pa_agent.solve_node import SolveNode, SolveNodeReceipt, TaskBrief
from flaghunter.agents.pa_agent.verifier import CTFVerifier
from flaghunter.harness.checkpoint_store import CheckpointStore


class _StubAgent:
    def __init__(self, *, project_root: Path, run_id: str):
        self.target = "http://ctf.local"
        self.rag_engine = None
        self.run_id = run_id
        self.project_root = project_root
        self.conversation_history = [
            AgentMessage(role="user", content="continue from compact evidence")
        ]


def _enable_claims_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")


def _candidate_only_state() -> CTFState:
    state = CTFState(
        target="http://ctf.local/?token=target-token",
        goal="inspect source password=goal-password",
    )
    trace = state.record_tool_receipt(
        tool_name="raw_probe",
        output_summary=(
            "HTTP/1.1 200 OK\n"
            "PING 127.0.0.1 (127.0.0.1): 56 data bytes\n"
            "64 bytes from 127.0.0.1: icmp_seq=0 ttl=64 time=0.041 ms\n"
            "uid=33(www-data) gid=33(www-data) groups=33(www-data)\n"
            "Set-Cookie: session=trace-cookie\n"
            "Authorization: Bearer trace-auth\n"
            "password=trace-password token=trace-token"
        ),
        success=True,
        artifact_refs=["http://ctf.local/body?api_key=artifact-key"],
        metadata={
            "source_channel": "p4_test",
            "status": "candidate_only",
            "token": "metadata-token",
        },
    )
    claim = state.create_claim(
        kind="credential_valid",
        content="username=admin password=claim-password token=claim-token",
        producer_type="tool",
        producer_id="raw_probe",
        primary_trace_id=trace.id,
        level="conjecture",
        evidence_trace_ids=[trace.id],
        metadata={
            "source_tool": "raw_probe",
            "source_trace_id": trace.id,
            "source_receipt_id": trace.receipt_id,
        },
    )
    state.record_execution_trace(
        kind="control_receipt",
        producer="control:trial",
        input_summary="prompt=input-prompt completion=input-completion",
        output_summary="<html><body>secret=html-secret</body></html>",
        success=False,
        metadata={
            "source_channel": "p4_test",
            "stop_reason": "insufficient_verification",
            "selected_claim_id": claim.id,
            "selected_trace_id": trace.id,
        },
    )
    node_id = state.record_solve_node(
        SolveNode(
            id="node-p4-candidate",
            title=json.dumps({"token": "node-token"}),
            summary="password=node-password",
        )
    )
    brief_id = state.record_task_brief(
        TaskBrief(
            id="brief-p4-candidate",
            node_id=node_id,
            worker_type="web token=worker-token",
            objective="inspect without cookie=brief-cookie",
        )
    )
    state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-p4-candidate",
            node_id=node_id,
            input_brief_id=brief_id,
            worker_type="web token=worker-token",
            status="failed",
            output_summary=json.dumps({"authorization": "receipt-auth"}),
            error_summary="secret=receipt-secret",
        )
    )
    state.stop_reason = "insufficient_verification"
    return state


@pytest.mark.parametrize("state", [None, CTFState(target="http://ctf.local", goal="get flag")])
def test_p4a_evidence_reasoning_context_empty_shape_is_stable(state) -> None:
    context = build_evidence_reasoning_context(state)

    assert context == {
        "schemaVersion": "p4.evidence_reasoning_context.v1",
        "summary": {
            "claimCount": 0,
            "verifiedClaimCount": 0,
            "candidateClaimCount": 0,
            "verificationRecordCount": 0,
            "traceSignalCount": 0,
            "hasVerifiedClaim": False,
            "hasControlReceipt": False,
            "hasToolReceipt": False,
            "hasVerificationReceipt": False,
            "p3NodeCount": 0,
            "p3ReceiptCount": 0,
            "crewWorkerCount": 0,
            "text": "",
        },
        "claimRefs": [],
        "verificationRefs": [],
        "traceSignals": [],
        "p3Summary": {},
        "crewSummary": {},
    }


def test_p4a_candidate_receipts_do_not_upgrade_to_proof_and_are_redacted(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = _candidate_only_state()
    before_snapshot = state.to_snapshot()

    context = build_evidence_reasoning_context(state)
    text = repr(context)

    assert context["summary"]["claimCount"] == 1
    assert context["summary"]["candidateClaimCount"] == 1
    assert context["summary"]["verifiedClaimCount"] == 0
    assert context["summary"]["verificationRecordCount"] == 0
    assert context["summary"]["hasControlReceipt"] is True
    assert context["summary"]["hasToolReceipt"] is True
    assert context["summary"]["hasVerifiedClaim"] is False
    assert context["p3Summary"]["receiptStatusCounts"] == {"failed": 1}
    assert context["claimRefs"][0]["level"] == "conjecture"
    assert context["verificationRefs"] == []
    assert state.verified_flags == []
    assert state.to_snapshot() == before_snapshot

    for leaked in (
        "PING 127.0.0.1",
        "64 bytes from 127.0.0.1",
        "uid=33(www-data)",
        "gid=33(www-data)",
        "<html",
        "input-prompt",
        "input-completion",
        "target-token",
        "goal-password",
        "trace-cookie",
        "trace-auth",
        "trace-password",
        "trace-token",
        "artifact-key",
        "metadata-token",
        "claim-password",
        "claim-token",
        "node-token",
        "node-password",
        "worker-token",
        "brief-cookie",
        "receipt-auth",
        "receipt-secret",
        "Set-Cookie",
        "Authorization",
    ):
        assert leaked not in text
    assert "<redacted>" in text or "<redacted raw body>" in text


def test_p4a_claim_content_preview_does_not_dump_raw_body(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    trace = state.record_tool_receipt(
        tool_name="probe",
        output_summary="compact trace",
        success=True,
    )
    state.create_claim(
        kind="credential_valid",
        content=(
            "PING 127.0.0.1\n"
            "64 bytes from 127.0.0.1\n"
            "uid=33(www-data)\n"
            "<html><body>token=body-token</body></html>"
        ),
        producer_type="test",
        producer_id="probe",
        primary_trace_id=trace.id,
        level="conjecture",
    )

    context = build_evidence_reasoning_context(state)
    text = repr(context)

    assert context["claimRefs"]
    assert context["claimRefs"][0]["contentPreview"] == "<redacted raw body>"
    for leaked in (
        "PING 127.0.0.1",
        "64 bytes from 127.0.0.1",
        "uid=33(www-data)",
        "<html",
        "body-token",
    ):
        assert leaked not in text


@pytest.mark.asyncio
async def test_p4a_verified_record_is_read_side_summary_only(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.local_challenge_auto_verify = True
    await CTFVerifier(runtime=None).verify_flag(
        state,
        flag="flag{p4_verified}",
        evidence_source="http-response",
        rationale="runtime proof accepted",
    )
    before_snapshot = state.to_snapshot()

    context = build_evidence_reasoning_context(state)

    assert context["summary"]["verifiedClaimCount"] == 1
    assert context["summary"]["verificationRecordCount"] == 1
    assert context["summary"]["hasVerifiedClaim"] is True
    assert context["claimRefs"][0]["contentPreview"] == "flag{p4_verified}"
    assert context["verificationRefs"][0]["decision"] == "verified"
    assert context["verificationRefs"][0]["passed"] is True
    assert context["verificationRefs"][0]["sufficientForUpgrade"] is True
    assert state.to_snapshot() == before_snapshot


def test_p4a_verification_rationale_preview_does_not_dump_raw_body(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    trace = state.record_verification_receipt(
        verifier_id="ctf_verifier",
        decision="verified",
        flag="flag{p4_rationale}",
        evidence_source="http-response",
        rationale=(
            "PING 127.0.0.1\n"
            "64 bytes from 127.0.0.1\n"
            "uid=33(www-data)\n"
            "Authorization: Bearer rationale-auth"
        ),
        success=True,
    )
    claim = state.create_claim(
        kind="flag_found",
        content="flag{p4_rationale}",
        producer_type="verifier",
        producer_id="ctf_verifier",
        primary_trace_id=trace.id,
        level="conjecture",
    )
    state.append_verification_record(
        claim.id,
        verifier_type="verifier",
        verifier_id="ctf_verifier",
        method="runtime_http",
        decision="verified",
        trace_id=trace.id,
        passed=True,
        sufficient_for_upgrade=True,
        rationale=(
            "PING 127.0.0.1\n"
            "64 bytes from 127.0.0.1\n"
            "uid=33(www-data)\n"
            "cookie=rationale-cookie"
        ),
        evidence_summary="compact evidence",
    )

    context = build_evidence_reasoning_context(state)
    text = repr(context)

    assert context["verificationRefs"]
    assert context["verificationRefs"][0]["rationalePreview"] == "<redacted raw body>"
    assert context["verificationRefs"][0]["decision"] == "verified"
    assert context["verificationRefs"][0]["passed"] is True
    assert context["verificationRefs"][0]["sufficientForUpgrade"] is True
    for leaked in (
        "PING 127.0.0.1",
        "64 bytes from 127.0.0.1",
        "uid=33(www-data)",
        "rationale-auth",
        "rationale-cookie",
        "Authorization",
    ):
        assert leaked not in text


def test_p4a_session_context_and_context_assembler_prompt_hook(monkeypatch, tmp_path) -> None:
    _enable_claims_v1(monkeypatch)
    run_id = "run-p4-evidence-context"
    state = _candidate_only_state()
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="candidate_only",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    session_context = SessionContextView(
        ledger_root=tmp_path / "loot" / "session_ledgers",
        artifact_root=tmp_path / "loot" / "artifact_registry",
        checkpoint_root=tmp_path / "loot" / "checkpoints",
    ).build_run_context(run_id)
    prompt_text = ContextAssembler(
        _StubAgent(project_root=tmp_path, run_id=run_id)
    ).assemble()

    assert session_context["latestCheckpoint"]["evidenceReasoningContext"][
        "schemaVersion"
    ] == "p4.evidence_reasoning_context.v1"
    assert session_context["resumeContext"]["hasEvidenceReasoningContext"] is True
    assert "evidence_claims=1" in session_context["resumeContext"]["summary"]
    assert "evidence_verified=0" in session_context["resumeContext"]["summary"]
    assert "evidence_traces=2" in session_context["resumeContext"]["summary"]
    assert "p3_receipts=1" in session_context["resumeContext"]["summary"]
    assert "evidence_claims=1" in prompt_text

    prompt_forbidden = (
        "auditEvidenceExport",
        "p3SolveSnapshot",
        "crewTrace",
        "full prompt",
        "completion",
        "stdout",
        "HTTP/1.1 200 OK",
        "PING 127.0.0.1",
        "64 bytes from 127.0.0.1",
        "uid=33(www-data)",
        "trace-cookie",
        "trace-auth",
        "trace-password",
        "trace-token",
    )
    for leaked in prompt_forbidden:
        assert leaked not in prompt_text
