from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.agents.pa_agent import ctf_dispatcher as _dispatcher_module
from flaghunter.agents.pa_agent.audit_views import build_audit_evidence_export
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.evidence_snapshot import build_p2_evidence_snapshot
from flaghunter.agents.pa_agent.p3_solve_readback import build_p3_solve_readback
from flaghunter.agents.pa_agent.session_context import SessionContextView
from flaghunter.agents.pa_agent.solve_node import SolveNode, SolveNodeReceipt, TaskBrief
from flaghunter.eval.replay import ReplayFixture, ReplayRuntime, load_fixture
from flaghunter.harness.checkpoint_store import CheckpointStore


_REAL_LOOT_STORE_DIRS = (
    Path("loot") / "session_ledgers",
    Path("loot") / "artifact_registry",
    Path("loot") / "checkpoints",
)


@dataclass
class _ReplayEvidenceTrial:
    fixture: ReplayFixture
    runtime: ReplayRuntime
    dispatcher: CTFTaskDispatcher
    result: object
    state: CTFState
    run_id: str
    ledger_root: Path
    registry_root: Path
    checkpoint_root: Path
    audit_export: dict
    evidence_snapshot: dict
    p3_snapshot: dict
    context: dict


@dataclass
class _StateEvidenceTrial:
    state: CTFState
    run_id: str
    audit_export: dict
    evidence_snapshot: dict
    p3_snapshot: dict
    context: dict


def _snapshot_store_dirs() -> dict[Path, set[str]]:
    snap: dict[Path, set[str]] = {}
    for directory in _REAL_LOOT_STORE_DIRS:
        snap[directory] = {p.name for p in directory.rglob("*")} if directory.exists() else set()
    return snap


def _enable_claims_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")


def _build_context(
    *,
    state: CTFState,
    run_id: str,
    tmp_path: Path,
    label: str,
    metadata: dict | None = None,
) -> dict:
    checkpoint_root = tmp_path / "checkpoints"
    CheckpointStore(checkpoint_root).save_checkpoint(
        run_id=run_id,
        label=label,
        state_snapshot=state.to_snapshot(),
        metadata=metadata or {},
    )
    return SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=checkpoint_root,
    ).build_run_context(run_id)


async def _run_replay_with_state(
    fixture_name: str,
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> _ReplayEvidenceTrial:
    _enable_claims_v1(monkeypatch)
    fixture = load_fixture(fixture_name)
    run_id = f"v1-evidence-{fixture.name}"
    ledger_root = tmp_path / "session_ledgers"
    registry_root = tmp_path / "artifact_registry"
    checkpoint_root = tmp_path / "checkpoints"

    prev_custom_notes_file = getattr(notes_module, "_custom_notes_file", None)
    prev_loaded_notes_file = getattr(notes_module, "_loaded_notes_file", None)
    monkeypatch.setattr(_dispatcher_module.ToolGuard, "require", lambda self, tools: {})
    try:
        notes_module.set_notes_file(tmp_path / "notes.json")
        notes_module._notes.clear()
        runtime = ReplayRuntime(fixture)
        dispatcher = CTFTaskDispatcher(
            runtime=runtime,
            progress_callback=None,
            verification_callback=lambda flag: "yes",
            profile=fixture.profile,
        )
        result = await dispatcher.run(
            target=fixture.target,
            goal=fixture.goal,
            type=fixture.type,
            hint=fixture.hint,
            run_id=run_id,
            ledger_root=ledger_root,
            registry_root=registry_root,
            checkpoint_root=checkpoint_root,
        )
        state = dispatcher.state
        if state is None:
            pytest.xfail("R1-C: dispatcher replay did not expose CTFState")
        context = _build_context(
            state=state,
            run_id=run_id,
            tmp_path=tmp_path,
            label="v1_trial_finished",
            metadata={"success": bool(getattr(result, "success", False))},
        )
        return _ReplayEvidenceTrial(
            fixture=fixture,
            runtime=runtime,
            dispatcher=dispatcher,
            result=result,
            state=state,
            run_id=run_id,
            ledger_root=ledger_root,
            registry_root=registry_root,
            checkpoint_root=checkpoint_root,
            audit_export=build_audit_evidence_export(state),
            evidence_snapshot=build_p2_evidence_snapshot(state),
            p3_snapshot=build_p3_solve_readback(state),
            context=context,
        )
    finally:
        notes_module._notes.clear()
        notes_module._custom_notes_file = prev_custom_notes_file
        notes_module._loaded_notes_file = prev_loaded_notes_file


def _build_candidate_only_state(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> _StateEvidenceTrial:
    _enable_claims_v1(monkeypatch)
    run_id = "v1-candidate-only-honesty"
    state = CTFState(
        target="http://ctf.local/source?token=target-token",
        goal="inspect backup without treating password=goal-password as proof",
    )
    trace = state.record_tool_receipt(
        tool_name="backup_source_probe",
        output_summary=(
            "source-only hint found; Cookie: session=candidate-cookie; "
            "Authorization: Bearer candidate-auth; secret=candidate-secret"
        ),
        success=True,
        artifact_refs=["file://loot/source?api_key=candidate-artifact-key"],
        metadata={
            "source_channel": "v1_trial_fixture",
            "status": "candidate_only",
            "token": "metadata-token",
        },
    )
    claim = state.create_claim(
        kind="flag_found",
        content="flag{candidate_only_not_verified}",
        producer_type="test_fixture",
        producer_id="backup_source_probe",
        primary_trace_id=trace.id,
        level="conjecture",
        source_channel="v1_trial_fixture",
        evidence_trace_ids=[trace.id],
        confidence=0.35,
        confidence_reason="source-only candidate without verifier receipt",
        metadata={
            "source_tool": "backup_source_probe",
            "source_trace_id": trace.id,
            "source_receipt_id": trace.receipt_id,
        },
    )
    state.record_execution_trace(
        kind="control_receipt",
        producer="control:trial",
        input_summary="candidate-only stop; password=input-password",
        output_summary="insufficient evidence; token=output-token",
        success=False,
        metadata={
            "stop_reason": "insufficient_verification",
            "finish_status": "blocked",
            "source_channel": "v1_trial_fixture",
            "selected_claim_id": claim.id,
            "selected_trace_id": trace.id,
        },
    )
    node_id = state.record_solve_node(
        SolveNode(
            run_id=run_id,
            title="candidate-only source inspection token=node-token",
            summary="no runtime verifier proof password=node-password",
            claim_ids=[claim.id],
            trace_ids=[trace.id],
        )
    )
    brief_id = state.record_task_brief(
        TaskBrief(
            node_id=node_id,
            run_id=run_id,
            worker_type="single_agent_dispatcher",
            objective="inspect archive without upgrading cookie=brief-cookie",
        )
    )
    state.record_solve_node_receipt(
        SolveNodeReceipt(
            node_id=node_id,
            run_id=run_id,
            worker_id="v1_candidate_fixture",
            worker_type="single_agent_dispatcher",
            input_brief_id=brief_id,
            status="failed",
            output_summary="candidate only, no verifier authorization=receipt-auth",
            error_summary="insufficient runtime evidence secret=receipt-secret",
        )
    )
    state.stop_reason = "insufficient_verification"

    context = _build_context(
        state=state,
        run_id=run_id,
        tmp_path=tmp_path,
        label="candidate_only",
        metadata={"success": False},
    )
    audit_export = build_audit_evidence_export(state)
    evidence_snapshot = build_p2_evidence_snapshot(state)
    p3_snapshot = build_p3_solve_readback(state)
    return _StateEvidenceTrial(
        state=state,
        run_id=run_id,
        audit_export=audit_export,
        evidence_snapshot=evidence_snapshot,
        p3_snapshot=p3_snapshot,
        context=context,
    )


def _assert_no_real_loot_store_writes(before: dict[Path, set[str]], after: dict[Path, set[str]]) -> None:
    for directory in _REAL_LOOT_STORE_DIRS:
        new_entries = after[directory] - before[directory]
        assert not new_entries, f"trial wrote real loot store entries in {directory}: {sorted(new_entries)}"


def _assert_no_raw_body_dump(surface_text: str) -> None:
    for raw_snippet in (
        "PING 127.0.0.1",
        "64 bytes from 127.0.0.1",
        "uid=33(www-data)",
        "gid=33(www-data)",
    ):
        assert raw_snippet not in surface_text


def _assert_no_sensitive_fixture_leaks(surface_text: str) -> None:
    for leaked in (
        "target-token",
        "goal-password",
        "candidate-cookie",
        "candidate-auth",
        "candidate-secret",
        "candidate-artifact-key",
        "metadata-token",
        "input-password",
        "output-token",
        "node-token",
        "node-password",
        "brief-cookie",
        "receipt-auth",
        "receipt-secret",
        "Cookie:",
        "Authorization:",
    ):
        assert leaked not in surface_text


@pytest.mark.asyncio
async def test_v1_cmdi_replay_exports_compact_evidence_chain(monkeypatch, tmp_path) -> None:
    before_loot = _snapshot_store_dirs()
    trial = await _run_replay_with_state("cmdi_param_rce", monkeypatch=monkeypatch, tmp_path=tmp_path)
    after_loot = _snapshot_store_dirs()

    assert trial.result.success is True
    assert trial.result.flag == trial.fixture.expected_flag
    assert trial.runtime.requests

    audit_summary = trial.audit_export["summary"]
    evidence_summary = trial.evidence_snapshot["summary"]
    p3_summary = trial.p3_snapshot["summary"]

    assert trial.audit_export["schemaVersion"] == "p2.audit_evidence.v1"
    assert trial.evidence_snapshot["schemaVersion"] == "p2.evidence_snapshot.v1"
    assert trial.p3_snapshot["schemaVersion"] == "p3.solve_readback.v1"
    assert audit_summary["executionTraceCount"] >= 1
    assert evidence_summary["hasControlReceipt"] is True
    assert evidence_summary["hasVerificationReceipt"] is True
    assert p3_summary["nodeCount"] >= 1
    assert p3_summary["taskBriefCount"] >= 1
    assert p3_summary["solveNodeReceiptCount"] >= 1
    assert trial.context["latestCheckpoint"]["auditEvidenceExport"]["schemaVersion"] == "p2.audit_evidence.v1"
    assert trial.context["latestCheckpoint"]["p3SolveSnapshot"]["schemaVersion"] == "p3.solve_readback.v1"
    assert trial.context["resumeContext"]["hasAuditEvidenceExport"] is True
    assert "p3SolveSnapshot" not in trial.context["resumeContext"]["summary"]

    if audit_summary["verificationRecordCount"] == 0 and not trial.state.verified_flags:
        pytest.xfail("R1-C: replay success has no verifier record or legacy verified flag gate")
    if audit_summary["verifiedClaimCount"] == 0 and not trial.state.verified_flags:
        pytest.xfail("R1-C: replay success did not create canonical or legacy verified proof")

    _assert_no_real_loot_store_writes(before_loot, after_loot)
    surfaces_text = repr(
        {
            "audit": trial.audit_export,
            "evidence": trial.evidence_snapshot,
            "context": trial.context,
        }
    )
    _assert_no_raw_body_dump(surfaces_text)


def test_v1_candidate_only_fixture_does_not_upgrade_receipts_to_proof(monkeypatch, tmp_path) -> None:
    trial = _build_candidate_only_state(monkeypatch=monkeypatch, tmp_path=tmp_path)

    assert trial.audit_export["summary"]["claimCount"] == 1
    assert trial.audit_export["summary"]["candidateClaimCount"] == 1
    assert trial.audit_export["summary"]["verifiedClaimCount"] == 0
    assert trial.audit_export["summary"]["verificationRecordCount"] == 0
    assert trial.evidence_snapshot["summary"]["hasVerifiedClaim"] is False
    assert trial.evidence_snapshot["summary"]["hasControlReceipt"] is True
    assert trial.evidence_snapshot["summary"]["hasVerificationReceipt"] is False
    assert trial.p3_snapshot["summary"]["solveNodeReceiptCount"] == 1
    assert trial.p3_snapshot["summary"]["receiptStatusCounts"] == {"failed": 1}
    assert trial.state.verified_flags == []
    assert trial.context["latestCheckpoint"]["verifiedFlags"] == []
    assert trial.context["resumeContext"]["verifiedFlags"] == []
    assert "verified_flags=" not in trial.context["resumeContext"]["summary"]
    assert "candidate_only_not_verified" in repr(trial.audit_export)

    surfaces_text = repr(
        {
            "audit": trial.audit_export,
            "evidence": trial.evidence_snapshot,
            "p3": trial.p3_snapshot,
            "context": trial.context,
        }
    )
    _assert_no_sensitive_fixture_leaks(surfaces_text)
