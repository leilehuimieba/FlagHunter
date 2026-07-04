from __future__ import annotations

import json

import pytest

from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.solve_node import (
    SolveNode,
    SolveNodeReceipt,
    TaskBrief,
)
from flaghunter.agents.pa_agent.task_dag_plan import (
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
)
from flaghunter.harness.artifact_registry import ArtifactRegistry
from flaghunter.harness.checkpoint_store import CheckpointStore
from flaghunter.harness.session_ledger import SessionLedger
from flaghunter.agents.pa_agent.session_context import (
    SessionContextView,
    build_workspace_run_context,
)
from flaghunter.agents.pa_agent.evidence_snapshot import build_p2_evidence_snapshot
from flaghunter.agents.pa_agent.verifier import CTFVerifier
from flaghunter.tools.executor import ToolExecutor
from flaghunter.tools.registry import Tool, ToolSchema


def test_session_context_view_builds_recent_events_artifacts_and_latest_checkpoint(tmp_path) -> None:
    run_id = "run-session-context-1"

    ledger = SessionLedger(tmp_path / "session_ledgers")
    ledger.append_event(run_id, "dispatcher_started", {"target": "http://ctf.local"})
    ledger.append_event(run_id, "verification_decision", {"decision": "verified"})
    ledger.append_event(run_id, "task_finished", {"success": True, "flag": "flag{ctx_ok}"})

    registry = ArtifactRegistry(tmp_path / "artifact_registry")
    registry.register_artifact(
        run_id=run_id,
        kind="artifact",
        title="ctf_backup_candidate",
        location="http://ctf.local/www.zip",
        producer="notes",
        metadata={"category": "artifact"},
    )

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_reason = "flag_verified"
    state.add_flag(
        "flag{ctx_ok}",
        level="verified",
        evidence_source="http-response",
        confidence=1.0,
    )
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    checkpoints.save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={"success": True, "flag": "flag{ctx_ok}"},
    )

    view = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    )
    context = view.build_run_context(run_id)

    assert context["runId"] == run_id
    assert [event["type"] for event in context["recentEvents"]] == [
        "dispatcher_started",
        "verification_decision",
        "task_finished",
    ]
    assert context["artifacts"][0]["title"] == "ctf_backup_candidate"
    assert context["latestCheckpoint"]["label"] == "task_finished"
    assert context["latestCheckpoint"]["stopReason"] == "flag_verified"
    assert context["latestCheckpoint"]["verifiedFlags"] == ["flag{ctx_ok}"]
    expected_resume_subset = {
        "runId": run_id,
        "checkpointId": context["latestCheckpoint"]["checkpointId"],
        "checkpointLabel": "task_finished",
        "stopReason": "flag_verified",
        "verifiedFlags": ["flag{ctx_ok}"],
        "runtimeFlags": [],
        "rejectedFlags": [],
        "recentEventTypes": [
            "dispatcher_started",
            "verification_decision",
            "task_finished",
        ],
        "artifactRefs": [
            {
                "artifactId": context["artifacts"][0]["artifactId"],
                "kind": "artifact",
                "title": "ctf_backup_candidate",
                "location": "http://ctf.local/www.zip",
                "path": None,
            }
        ],
        "summary": (
            f"run_id={run_id}; latest_checkpoint=task_finished; "
            "stop_reason=flag_verified; verified_flags=flag{ctx_ok}; "
            "recent_events=dispatcher_started, verification_decision, task_finished; "
            "artifacts=ctf_backup_candidate"
        ),
    }
    for key, value in expected_resume_subset.items():
        assert context["resumeContext"][key] == value
    assert "traceRefs" not in context["resumeContext"]


def test_session_context_recent_events_redact_jsonish_sensitive_payloads(tmp_path) -> None:
    run_id = "run-session-context-jsonish-event-redaction"
    ledger = SessionLedger(tmp_path / "session_ledgers")
    ledger.append_event(
        run_id,
        "handoff_created",
        {
            "target": json.dumps({"token": "json-event-token"}),
            "next_action": json.dumps({"password": "json-event-password"}),
            "metadata": {
                "authorization": "Bearer json-event-auth",
                "cookie": "json-event-cookie",
            },
        },
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    context_text = repr(context)
    assert context["recentEvents"][0]["payload"]["target"] == (
        '{"token": "<redacted>"}'
    )
    assert "ledgerEventRefs" in context["resumeContext"]
    for leaked in (
        "json-event-token",
        "json-event-password",
        "json-event-auth",
        "json-event-cookie",
    ):
        assert leaked not in context_text


def test_session_context_view_returns_stable_empty_shape_without_run_data(tmp_path) -> None:
    view = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    )

    context = view.build_run_context("missing-run")

    assert context["runId"] == "missing-run"
    assert context["recentEvents"] == []
    assert context["artifacts"] == []
    assert context["latestCheckpoint"] is None
    assert context["resumeContext"] is None


def test_session_context_view_projects_resume_ingress_from_dispatcher_started_event(
    tmp_path,
) -> None:
    run_id = "run-session-context-resume"

    ledger = SessionLedger(tmp_path / "session_ledgers")
    ledger.append_event(
        run_id,
        "dispatcher_started",
        {
            "target": "http://ctf.local",
            "has_resume_context": True,
            "resume_run_id": "run-prev-1",
            "resume_checkpoint_id": "checkpoint-prev-1",
        },
    )
    ledger.append_event(run_id, "task_finished", {"success": False})

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_reason = "wrong_flag_feedback"
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={"success": False},
    )

    view = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    )
    context = view.build_run_context(run_id)

    assert context["resumeIngress"] == {
        "hasResumeContext": True,
        "runId": "run-prev-1",
        "checkpointId": "checkpoint-prev-1",
        "sourceEvent": "dispatcher_started",
    }


def test_session_context_view_includes_rejected_flags_in_resume_summary_for_wrong_flag_feedback(
    tmp_path,
) -> None:
    run_id = "run-session-context-wrong-flag"

    ledger = SessionLedger(tmp_path / "session_ledgers")
    ledger.append_event(run_id, "verification_decision", {"decision": "rejected"})
    ledger.append_event(run_id, "task_finished", {"success": False})

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_reason = "wrong_flag_feedback"
    state.add_flag(
        "flag{wrong_ctx}",
        level="rejected",
        evidence_source="submit-endpoint",
        rationale="platform rejected",
        confidence=1.0,
    )
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={"success": False, "reason": "wrong_flag_feedback"},
    )

    view = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    )
    context = view.build_run_context(run_id)

    assert context["latestCheckpoint"]["stopReason"] == "wrong_flag_feedback"
    assert context["latestCheckpoint"]["rejectedFlags"] == ["flag{wrong_ctx}"]
    assert "rejected_flags=flag{wrong_ctx}" in context["resumeContext"]["summary"]


def test_build_workspace_run_context_merges_artifacts_from_legacy_and_new_roots(
    tmp_path,
) -> None:
    run_id = "run-session-context-artifact-roots"

    SessionLedger(tmp_path / "loot" / "session_ledgers").append_event(
        run_id,
        "task_finished",
        {"success": True},
    )
    ArtifactRegistry(tmp_path / "loot" / "artifact_registry").register_artifact(
        run_id=run_id,
        kind="artifact",
        title="legacy artifact",
        location="file:///legacy.txt",
        producer="notes",
    )
    ArtifactRegistry(tmp_path / "loot" / "artifacts").register_artifact(
        run_id=run_id,
        kind="log_capture",
        title="new artifact",
        location="file:///new.log",
        producer="exploit",
    )

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_reason = "done"
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={"success": True},
    )

    context = build_workspace_run_context(tmp_path, run_id)

    titles = [item["title"] for item in context["artifacts"]]
    assert titles == ["legacy artifact", "new artifact"]
    assert context["latestCheckpoint"]["label"] == "task_finished"
    assert "artifacts=legacy artifact, new artifact" in context["resumeContext"]["summary"]


def _enable_claims_v1(monkeypatch) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")


def _tool_returning(output: str) -> Tool:
    async def fn(arguments: dict, runtime) -> str:
        return output

    return Tool(name="probe", description="", schema=ToolSchema(), execute_fn=fn)


async def _state_with_candidate_and_verified_claims() -> CTFState:
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    runtime = type("RuntimeWithState", (), {"ctf_state": state})()
    executor = ToolExecutor(runtime=runtime)
    await executor.execute(
        _tool_returning(
            "Set-Cookie: session=super-secret-cookie\n"
            "Authorization: Bearer top-secret-token\n"
            "flag{ctx_candidate}"
        ),
        {"url": "http://ctf.local/"},
    )
    state.local_challenge_auto_verify = True
    await CTFVerifier(runtime=None).verify_flag(
        state,
        flag="flag{ctx_verified}",
        evidence_source="http-response",
        rationale="local challenge accepted",
    )
    return state


@pytest.mark.asyncio
async def test_session_context_surfaces_compact_claim_evidence_refs(
    monkeypatch,
    tmp_path,
) -> None:
    _enable_claims_v1(monkeypatch)
    run_id = "run-session-context-p2e-evidence"
    state = await _state_with_candidate_and_verified_claims()
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    evidence_refs = context["latestCheckpoint"]["claimEvidenceRefs"]
    by_content = {item["contentPreview"]: item for item in evidence_refs}

    assert "flag{ctx_candidate}" in by_content
    assert "flag{ctx_verified}" in by_content
    candidate = by_content["flag{ctx_candidate}"]
    verified = by_content["flag{ctx_verified}"]
    assert candidate["level"] == "conjecture"
    assert candidate["status"] == "active"
    assert candidate["sourceTool"] == "probe"
    assert candidate["sourceTraceId"]
    assert candidate["sourceReceiptId"]
    assert candidate["primaryTrace"]["kind"] == "tool_receipt"
    assert verified["level"] == "verified"
    assert verified["status"] == "active"
    assert verified["latestVerificationDecision"] == "verified"
    assert context["resumeContext"]["claimEvidenceRefs"] == evidence_refs
    context_text = repr(context)
    assert "super-secret-cookie" not in context_text
    assert "top-secret-token" not in context_text
    assert "Set-Cookie" not in context_text
    assert "Authorization" not in context_text


@pytest.mark.asyncio
async def test_session_context_surfaces_small_audit_evidence_export(
    monkeypatch,
    tmp_path,
) -> None:
    _enable_claims_v1(monkeypatch)
    run_id = "run-session-context-p2g-audit-export"
    state = await _state_with_candidate_and_verified_claims()
    state.target = "http://ctf.local/?token=target-token"
    state.goal = "login with password=goal-password token=goal-token"
    state.stop_reason = "stopped because secret=stop-secret"
    trace = state.record_tool_receipt(
        tool_name="artifact_probe",
        output_summary="artifact found",
        success=True,
        artifact_refs=[
            "file://loot/password=artifact-password.txt",
            "http://ctf.local/a?token=artifact-token",
        ],
    )
    state.create_claim(
        kind="credential_valid",
        content="username=admin password=claim-password token=claim-token",
        producer_type="tool",
        producer_id="artifact_probe",
        primary_trace_id=trace.id,
        level="conjecture",
        evidence_trace_ids=[trace.id],
        metadata={
            "source_tool": "artifact_probe",
            "source_trace_id": trace.id,
            "source_receipt_id": trace.receipt_id,
        },
    )
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    export = context["latestCheckpoint"]["auditEvidenceExport"]
    summary = context["resumeContext"]["auditEvidenceSummary"]
    assert export["schemaVersion"] == "p2.audit_evidence.v1"
    assert export["target"] == "http://ctf.local/?token=<redacted>"
    assert export["goal"] == "login with password=<redacted> token=<redacted>"
    assert export["stopReason"] == "stopped because secret=<redacted>"
    assert export["summary"]["claimCount"] >= 3
    assert export["summary"]["verifiedClaimCount"] >= 1
    assert export["summary"]["candidateClaimCount"] >= 1
    assert export["summary"]["executionTraceCount"] >= 3
    assert summary["schemaVersion"] == "p2.audit_evidence.v1"
    assert summary["claimCount"] == export["summary"]["claimCount"]
    assert summary["executionTraceCount"] == export["summary"]["executionTraceCount"]
    assert context["resumeContext"]["hasAuditEvidenceExport"] is True
    context_text = repr(context)
    for leaked in (
        "target-token",
        "goal-password",
        "goal-token",
        "stop-secret",
        "artifact-password",
        "artifact-token",
        "claim-password",
        "claim-token",
        "super-secret-cookie",
        "top-secret-token",
    ):
        assert leaked not in context_text


@pytest.mark.asyncio
async def test_session_context_reuses_p2_evidence_snapshot_without_shape_change(
    monkeypatch,
    tmp_path,
) -> None:
    _enable_claims_v1(monkeypatch)
    run_id = "run-session-context-p2i-snapshot"
    state = await _state_with_candidate_and_verified_claims()
    state.record_execution_trace(
        kind="control_receipt",
        producer="control:finish",
        input_summary="action=complete",
        output_summary="All steps complete",
        success=True,
        metadata={
            "stop_reason": "all_steps_complete",
            "finish_status": "answered",
            "source_channel": "finish_tool",
            "answer_kind": "plan_completion",
        },
    )
    expected_snapshot = build_p2_evidence_snapshot(
        state,
        trace_ref_limit=5,
        claim_evidence_limit=5,
        audit_claim_limit=5,
        audit_trace_limit=10,
        audit_verification_record_limit=10,
        preview_limit=160,
    )
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    assert "evidenceSnapshot" not in context["latestCheckpoint"]
    assert "evidenceSnapshot" not in context["resumeContext"]
    assert context["latestCheckpoint"]["traceRefs"] == expected_snapshot["traceRefs"]
    assert (
        context["latestCheckpoint"]["claimEvidenceRefs"]
        == expected_snapshot["claimEvidenceRefs"]
    )
    assert (
        context["latestCheckpoint"]["auditEvidenceExport"]
        == expected_snapshot["auditEvidenceExport"]
    )
    assert context["resumeContext"]["traceRefs"] == expected_snapshot["traceRefs"]
    assert (
        context["resumeContext"]["claimEvidenceRefs"]
        == expected_snapshot["claimEvidenceRefs"]
    )
    assert context["resumeContext"]["hasAuditEvidenceExport"] is True


def test_session_context_empty_checkpoint_surfaces_empty_audit_export(
    tmp_path,
) -> None:
    run_id = "run-session-context-p2g-empty-audit-export"
    state = CTFState(target="http://ctf.local", goal="get flag")
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="checkpoint_empty",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    export = context["latestCheckpoint"]["auditEvidenceExport"]
    assert export["claims"] == []
    assert export["verificationRecords"] == []
    assert export["executionTraces"] == []
    assert export["summary"]["claimCount"] == 0
    assert context["resumeContext"]["hasAuditEvidenceExport"] is True


def test_session_context_surfaces_compact_p3_solve_snapshot(tmp_path) -> None:
    run_id = "run-session-context-p3-solve"
    state = CTFState(target="http://ctf.local", goal="get flag")
    node_id = state.record_solve_node(
        SolveNode(
            id="node-session-p3",
            title=json.dumps({"token": "node-token"}),
            summary="password=node-password",
            metadata={"secret": "node-secret"},
        )
    )
    brief_id = state.record_task_brief(
        TaskBrief(
            id="brief-session-p3",
            node_id=node_id,
            objective="token=brief-token",
            allowed_tool_names=["curl api_key=brief-key"],
        )
    )
    state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-session-p3",
            node_id=node_id,
            input_brief_id=brief_id,
            status="completed",
            output_summary=json.dumps({"authorization": "receipt-auth"}),
            error_summary="secret=receipt-secret",
        )
    )
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    p3 = context["latestCheckpoint"]["p3SolveSnapshot"]
    assert p3["summary"]["nodeCount"] == 1
    assert p3["summary"]["taskBriefCount"] == 1
    assert p3["summary"]["solveNodeReceiptCount"] == 1
    assert context["resumeContext"]["p3SolveSummary"]["nodeCount"] == 1
    assert context["resumeContext"]["p3SolveSummary"]["solveNodeReceiptCount"] == 1
    assert "solve_nodes=1" in context["resumeContext"]["summary"]
    assert "node_receipts=1" in context["resumeContext"]["summary"]

    context_text = repr(context)
    for leaked in (
        "node-token",
        "node-password",
        "node-secret",
        "brief-token",
        "brief-key",
        "receipt-auth",
        "receipt-secret",
    ):
        assert leaked not in context_text


def test_session_context_surfaces_compact_p3_crew_trace_summary(tmp_path) -> None:
    run_id = "run-session-context-p3-crew"
    state = CTFState(target="http://ctf.local", goal="get flag")
    node_id = state.record_solve_node(
        SolveNode(
            id="node-crew-session",
            title=json.dumps({"token": "node-token"}),
        )
    )
    brief_id = state.record_task_brief(
        TaskBrief(
            id="brief-crew-session",
            node_id=node_id,
            worker_type="web token=worker-token",
            objective="password=brief-password",
        )
    )
    state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-crew-session",
            node_id=node_id,
            input_brief_id=brief_id,
            worker_id="worker-web cookie=worker-cookie",
            worker_type="web token=worker-token",
            status="completed",
            output_summary=json.dumps({"authorization": "receipt-auth"}),
        )
    )
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    crew = context["latestCheckpoint"]["p3SolveSnapshot"]["crewTrace"]
    assert crew["summary"]["workerCount"] == 1
    assert crew["summary"]["receiptCount"] == 1
    assert context["resumeContext"]["p3SolveSummary"]["crewWorkerCount"] == 1
    assert "crew_workers=1" in context["resumeContext"]["summary"]
    assert "crew_receipts=1" in context["resumeContext"]["summary"]
    assert "worker_types=web token=<redacted>:1" in context["resumeContext"]["summary"]

    context_text = repr(context)
    for leaked in (
        "node-token",
        "worker-token",
        "brief-password",
        "worker-cookie",
        "receipt-auth",
    ):
        assert leaked not in context_text


def test_session_context_surfaces_compact_task_dag_plan_summary(tmp_path) -> None:
    run_id = "run-session-context-p4b-task-dag"
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = TaskDAGPlan(id="plan-session", metadata={"token": "plan-token"})
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            title="PING 127.0.0.1\n64 bytes from 127.0.0.1",
            goal="collect password=goal-password",
            status=TaskDAGStatus.SUCCEEDED,
            metadata={"secret": "node-secret"},
        )
    )
    plan.add_node(
        TaskDAGNode(
            id="task-b",
            status=TaskDAGStatus.INSUFFICIENT,
            depends_on=["task-a"],
        )
    )
    state.set_task_dag_plan(plan)
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    latest = context["latestCheckpoint"]
    resume = context["resumeContext"]
    assert latest["taskDagPlanReadback"]["summary"]["nodeCount"] == 2
    assert latest["taskDagPlanReadback"]["summary"]["edgeCount"] == 1
    assert resume["taskDagPlanSummary"]["nodeCount"] == 2
    assert resume["taskDagPlanSummary"]["edgeCount"] == 1
    assert resume["taskDagPlanSummary"]["statusCounts"] == {
        "insufficient": 1,
        "succeeded": 1,
    }
    assert "task_dag_nodes=2" in resume["summary"]
    assert "task_dag_edges=1" in resume["summary"]
    assert "task_dag_statuses=insufficient:1,succeeded:1" in resume["summary"]
    context_text = repr(context)
    for leaked in (
        "PING 127.0.0.1",
        "64 bytes from",
        "goal-password",
        "plan-token",
        "node-secret",
    ):
        assert leaked not in context_text


def test_session_context_empty_task_dag_plan_is_not_noisy(tmp_path) -> None:
    run_id = "run-session-context-p4b-empty-task-dag"
    state = CTFState(target="http://ctf.local", goal="get flag")
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    assert "taskDagPlanSummary" not in context["resumeContext"]
    assert "task_dag" not in context["resumeContext"]["summary"]


def test_session_context_redacts_non_flag_claim_content_in_summary(
    monkeypatch,
    tmp_path,
) -> None:
    _enable_claims_v1(monkeypatch)
    run_id = "run-session-context-p2e-redacted-claim"
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    trace = state.record_tool_receipt(
        tool_name="login_probe",
        arguments={"url": "http://ctf.local/login"},
        output_summary="credential check completed",
        success=True,
    )
    state.create_claim(
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
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="candidate_found",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    context_text = repr(context["latestCheckpoint"]["claimEvidenceRefs"])
    trace_refs_text = repr(context["latestCheckpoint"]["traceRefs"])
    resume_trace_refs_text = repr(context["resumeContext"]["traceRefs"])
    full_context_text = repr(context)
    summary = context["resumeContext"]["summary"]
    assert "credential_valid" in context_text
    assert "credential_valid" in trace_refs_text
    assert "credential_valid" in summary
    assert "super-secret-password" not in context_text
    assert "top-secret-token" not in context_text
    assert "super-secret-password" not in trace_refs_text
    assert "top-secret-token" not in trace_refs_text
    assert "super-secret-password" not in resume_trace_refs_text
    assert "top-secret-token" not in resume_trace_refs_text
    assert "super-secret-password" not in full_context_text
    assert "top-secret-token" not in full_context_text
    assert "super-secret-password" not in summary
    assert "top-secret-token" not in summary
    assert "password=<redacted>" in trace_refs_text
    assert "token=<redacted>" in trace_refs_text
    assert "password=<redacted>" in summary
    assert "token=<redacted>" in summary


def test_session_context_resume_summary_compacts_raw_body_claim_preview(
    monkeypatch,
    tmp_path,
) -> None:
    _enable_claims_v1(monkeypatch)
    run_id = "run-session-context-p4a2-raw-body-summary"
    state = CTFState(target="http://ctf.local", goal="get flag")
    trace = state.record_tool_receipt(
        tool_name="probe",
        output_summary="compact probe signal",
        success=True,
    )
    claim = state.create_claim(
        kind="credential_valid",
        content=(
            "PING 127.0.0.1\n"
            "64 bytes from 127.0.0.1\n"
            "uid=33(www-data)\n"
            "password=hunter2 Authorization: Bearer abc"
        ),
        producer_type="tool",
        producer_id="probe",
        primary_trace_id=trace.id,
        level="conjecture",
        evidence_trace_ids=[trace.id],
        metadata={
            "source_tool": "probe",
            "source_trace_id": trace.id,
            "source_receipt_id": trace.receipt_id,
        },
    )
    CheckpointStore(tmp_path / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="latest",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    summary = context["resumeContext"]["summary"]
    assert "claim_evidence=" in summary
    assert claim.id in summary
    assert "credential_valid/conjecture/active" in summary
    assert f"trace={trace.id}" in summary
    assert f"receipt={trace.receipt_id}" in summary
    assert "tool=probe" in summary
    assert "<redacted raw body>" in summary
    for leaked in (
        "PING 127.0.0.1",
        "64 bytes from",
        "uid=33",
        "hunter2",
        "Bearer abc",
    ):
        assert leaked not in summary
