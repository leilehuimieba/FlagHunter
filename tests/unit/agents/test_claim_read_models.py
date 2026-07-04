from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from flaghunter.agents.pa_agent.blackboard import project_blackboard
from flaghunter.agents.pa_agent.claim_views import preferred_flag_summary
from flaghunter.agents.pa_agent.context_assembler import ContextAssembler
from flaghunter.agents.pa_agent.ctf_state import (
    CTFState,
    ClaimKind,
    ClaimLevel,
    VerificationDecision,
    VerificationMethod,
)
from flaghunter.agents.pa_agent.hypothesis_engine import HypothesisEngine
from flaghunter.agents.pa_agent.recovery import RecoveryController
from flaghunter.agents.pa_agent.reasoning import ReasoningLayer
from flaghunter.agents.pa_agent.session_context import SessionContextView
from flaghunter.harness.checkpoint_store import CheckpointStore


def _flag_claim(
    state: CTFState,
    value: str,
    *,
    runtime_supported: bool = False,
    verified: bool = False,
    retracted: bool = False,
):
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content=value,
        level=ClaimLevel.CONJECTURE,
        producer_type="test",
        producer_id="claim-read-models",
        primary_trace_id=f"trace:{value}",
        source_channel="test",
        confidence=0.7,
    )
    if runtime_supported:
        state.append_verification_record(
            claim.id,
            verifier_type="verifier",
            verifier_id="ctf_verifier",
            method=VerificationMethod.RUNTIME_HTTP,
            decision=VerificationDecision.RUNTIME_SUPPORTED,
            trace_id=f"verify:runtime:{value}",
            passed=True,
        )
    if verified:
        record = state.append_verification_record(
            claim.id,
            verifier_type="verifier",
            verifier_id="ctf_verifier",
            method=VerificationMethod.LOCAL_CHALLENGE_AUTO_VERIFY,
            decision=VerificationDecision.VERIFIED,
            trace_id=f"verify:verified:{value}",
            passed=True,
            sufficient_for_upgrade=True,
        )
        state.upgrade_claim_to_verified(
            claim.id,
            verification_record_id=record.id,
            verifier_id="ctf_verifier",
        )
    if retracted:
        record = state.append_verification_record(
            claim.id,
            verifier_type="verifier",
            verifier_id="ctf_verifier",
            method=VerificationMethod.PLATFORM_SUBMIT,
            decision=VerificationDecision.REJECTED,
            trace_id=f"verify:rejected:{value}",
            passed=False,
        )
        state.retract_claim(
            claim.id,
            reason="wrong flag",
            trace_id=record.trace_id,
            actor_id="ctf_verifier",
        )
    return claim


def test_blackboard_projects_canonical_flag_claims_when_enabled(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.add_flag(
        "flag{legacy_verified}",
        level="verified",
        evidence_source="legacy",
        confidence=0.99,
    )
    _flag_claim(state, "flag{canonical_verified}", verified=True)
    _flag_claim(state, "flag{canonical_runtime}", runtime_supported=True)
    _flag_claim(state, "flag{canonical_retracted}", retracted=True)

    board = project_blackboard(state)
    facts = board["facts"]

    assert {
        "kind": "verified_flag",
        "value": "flag{canonical_verified}",
        "source": "test",
        "confidence": 1.0,
    } in facts
    assert any(
        item["kind"] == "runtime_flag" and item["value"] == "flag{canonical_runtime}"
        for item in facts
    )
    assert any(
        item["kind"] == "refuted_flag" and item["value"] == "flag{canonical_retracted}"
        for item in facts
    )
    assert not any(item.get("value") == "flag{legacy_verified}" for item in facts)


def test_flag_summary_falls_back_per_bucket_when_only_canonical_candidate(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.add_flag(
        "flag{legacy_verified}",
        level="verified",
        evidence_source="legacy",
        confidence=0.99,
    )
    _flag_claim(state, "flag{canonical_candidate}")

    summary = preferred_flag_summary(state)
    board = project_blackboard(state)

    assert summary["verifiedFlags"] == ["flag{legacy_verified}"]
    assert summary["candidateFlags"] == ["flag{canonical_candidate}"]
    assert any(
        item["kind"] == "verified_flag" and item["value"] == "flag{legacy_verified}"
        for item in board["facts"]
    )
    assert any(
        item["kind"] == "candidate_flag"
        and item["description"] == "flag{canonical_candidate}"
        for item in board["intents"]
    )


def test_flag_summary_falls_back_per_bucket_when_only_canonical_retracted(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.add_flag(
        "flag{legacy_runtime}",
        level="runtime",
        evidence_source="legacy-runtime",
        confidence=0.8,
    )
    _flag_claim(state, "flag{canonical_retracted}", retracted=True)

    summary = preferred_flag_summary(state)
    board = project_blackboard(state)

    assert summary["runtimeFlags"] == ["flag{legacy_runtime}"]
    assert summary["retractedFlags"] == ["flag{canonical_retracted}"]
    assert summary["rejectedFlags"] == ["flag{canonical_retracted}"]
    assert any(
        item["kind"] == "runtime_flag" and item["value"] == "flag{legacy_runtime}"
        for item in board["facts"]
    )
    assert any(
        item["kind"] == "refuted_flag" and item["value"] == "flag{canonical_retracted}"
        for item in board["facts"]
    )


def test_blackboard_uses_legacy_flags_when_claims_disabled(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="get flag")
    _flag_claim(state, "flag{canonical_verified}", verified=True)
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "0")
    state.add_flag(
        "flag{legacy_verified}",
        level="verified",
        evidence_source="legacy",
        confidence=0.9,
    )

    board = project_blackboard(state)
    facts = board["facts"]

    assert any(item["kind"] == "verified_flag" and item["value"] == "flag{legacy_verified}" for item in facts)
    assert not any(item.get("value") == "flag{canonical_verified}" for item in facts)


def test_session_context_prefers_canonical_flag_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.add_flag("flag{legacy_verified}", level="verified", evidence_source="legacy")
    _flag_claim(state, "flag{canonical_verified}", verified=True)
    _flag_claim(state, "flag{canonical_runtime}", runtime_supported=True)
    _flag_claim(state, "flag{canonical_retracted}", retracted=True)
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id="run-canonical-context",
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=tmp_path / "ledgers",
        artifact_root=tmp_path / "artifacts",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context("run-canonical-context")

    latest = context["latestCheckpoint"]
    resume = context["resumeContext"]
    assert latest["verifiedFlags"] == ["flag{canonical_verified}"]
    assert latest["runtimeFlags"] == ["flag{canonical_runtime}"]
    assert latest["retractedFlags"] == ["flag{canonical_retracted}"]
    assert latest["rejectedFlags"] == ["flag{canonical_retracted}"]
    assert "flag{legacy_verified}" not in resume["summary"]
    assert "runtime_flags=flag{canonical_runtime}" in resume["summary"]
    assert "retracted_flags=flag{canonical_retracted}" in resume["summary"]


def test_context_assembler_includes_canonical_runtime_and_retracted_summary():
    class _Knowledge:
        def project_context(self, *, target: str, phase: str) -> str:
            return ""

        def session_run_context(self, run_id: str, *, event_limit: int, artifact_limit: int):
            return {
                "recentEvents": [],
                "artifacts": [],
                "latestCheckpoint": {
                    "label": "task_finished",
                    "verifiedFlags": ["flag{canonical_verified}"],
                    "runtimeFlags": ["flag{canonical_runtime}"],
                    "retractedFlags": ["flag{canonical_retracted}"],
                    "rejectedFlags": ["flag{canonical_retracted}"],
                    "stopReason": "canonical stop",
                },
            }

        def rag_search(self, query: str):
            return []

    agent = SimpleNamespace(
        run_id="run-context-assembler",
        project_root=Path("."),
        target="http://ctf.local",
        conversation_history=[],
    )
    assembler = ContextAssembler(agent)
    assembler._km_cache = _Knowledge()

    summary = assembler._build_session_context_summary()

    assert "verified_flags=flag{canonical_verified}" in summary
    assert "runtime_flags=flag{canonical_runtime}" in summary
    assert "retracted_flags=flag{canonical_retracted}" in summary


def test_recovery_waits_for_canonical_runtime_flag(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="get flag")
    _flag_claim(state, "flag{canonical_runtime}", runtime_supported=True)
    controller = RecoveryController(HypothesisEngine())

    decision = controller.finalize(state, used_chains=["web"], no_progress_count=0)

    assert decision.should_stop is True
    assert decision.action == "wait_for_verification"
    assert "flag{canonical_runtime}" in decision.reason
    assert state.repertoire_miss is False


def test_reasoning_stop_report_reads_canonical_flag_lists(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="get flag")
    _flag_claim(state, "flag{canonical_verified}", verified=True)
    _flag_claim(state, "flag{canonical_runtime}", runtime_supported=True)
    _flag_claim(state, "flag{canonical_retracted}", retracted=True)

    report = ReasoningLayer().generate_stop_report(
        state,
        reason="canonical verified claim",
        missing_capabilities=[],
    )

    assert report.reason == "flag_verified"
    assert report.verified_flags == ["flag{canonical_verified}"]
    assert report.runtime_flags == ["flag{canonical_runtime}"]
    assert report.rejected_flags == ["flag{canonical_retracted}"]
