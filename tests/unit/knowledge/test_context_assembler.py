from __future__ import annotations

import json
from types import SimpleNamespace

from flaghunter.agents.base_agent import AgentMessage
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
from flaghunter.agents.pa_agent.context_assembler import ContextAssembler


class _StubAgent:
    def __init__(self, *, project_root, run_id: str):
        self.target = "http://ctf.local"
        self.rag_engine = None
        self.run_id = run_id
        self.project_root = project_root
        self.conversation_history = [
            AgentMessage(role="user", content="continue from current run state")
        ]


def test_context_assembler_includes_harness_session_context_summary(tmp_path) -> None:
    run_id = "run-context-assembler-1"
    SessionLedger(tmp_path / "loot" / "session_ledgers").append_event(
        run_id,
        "task_finished",
        {"success": True, "flag": "flag{ctx_summary_ok}"},
    )
    ArtifactRegistry(tmp_path / "loot" / "artifact_registry").register_artifact(
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
        "flag{ctx_summary_ok}",
        level="verified",
        evidence_source="http-response",
        confidence=1.0,
    )
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={"success": True},
    )

    text = ContextAssembler(_StubAgent(project_root=tmp_path, run_id=run_id)).assemble()

    assert f"run_id={run_id}" in text
    assert "flag{ctx_summary_ok}" in text
    assert "flag_verified" in text
    assert "ctf_backup_candidate" in text
    assert "task_finished" in text


def test_context_assembler_appends_resume_ingress_lineage_to_session_summary(
    tmp_path,
) -> None:
    run_id = "run-context-assembler-resume"
    SessionLedger(tmp_path / "loot" / "session_ledgers").append_event(
        run_id,
        "dispatcher_started",
        {
            "has_resume_context": True,
            "resume_run_id": "run-prev-1",
            "resume_checkpoint_id": "checkpoint-prev-1",
        },
    )
    SessionLedger(tmp_path / "loot" / "session_ledgers").append_event(
        run_id,
        "task_finished",
        {"success": False},
    )
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_reason = "wrong_flag_feedback"
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={"success": False},
    )

    text = ContextAssembler(_StubAgent(project_root=tmp_path, run_id=run_id)).assemble()

    assert f"run_id={run_id}" in text
    assert "wrong_flag_feedback" in text
    assert "resumed_from_run=run-prev-1" in text
    assert "resumed_from_checkpoint=checkpoint-prev-1" in text


def test_context_assembler_includes_local_challenge_root_summary_from_session_artifacts(
    tmp_path,
) -> None:
    run_id = "run-context-assembler-local-root"

    SessionLedger(tmp_path / "loot" / "session_ledgers").append_event(
        run_id,
        "dispatcher_started",
        {"target": "http://ctf.local"},
    )
    SessionLedger(tmp_path / "loot" / "session_ledgers").append_event(
        run_id,
        "task_finished",
        {"success": False},
    )

    ArtifactRegistry(tmp_path / "loot" / "artifact_registry").register_artifact(
        run_id=run_id,
        kind="local_challenge_root_summary",
        title="easy_login summary",
        path=r"D:\webstudy\CTF\easy_login",
        location=r"D:\webstudy\CTF\easy_login",
        producer="local_challenge_context",
        metadata={
            "kind": "challenge_root_summary",
            "root_name": "easy_login",
            "has_compose": True,
            "key_files": ["README.md", "app.py", "requirements.txt"],
            "detected_stack": ["python"],
            "file_count": 5,
        },
    )

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_reason = "needs_local_analysis"
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={"success": False},
    )

    text = ContextAssembler(_StubAgent(project_root=tmp_path, run_id=run_id)).assemble()

    assert f"run_id={run_id}" in text
    assert "local_root=easy_login" in text
    assert "local_stack=python" in text
    assert "local_key_files=README.md, app.py, requirements.txt" in text
    assert "local_has_compose=true" in text


def test_context_assembler_includes_compact_claim_trace_evidence_summary(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    run_id = "run-context-assembler-p2e"
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    trace = state.record_tool_receipt(
        tool_name="probe",
        arguments={"url": "http://ctf.local/"},
        output_summary=(
            "HTTP/1.1 200 OK\n"
            "Set-Cookie: <redacted>\n"
            "Authorization: Bearer <redacted>\n"
            "flag{asm_candidate}"
        ),
        success=True,
    )
    claim = state.create_claim(
        kind="flag_found",
        content="flag{asm_candidate}",
        producer_type="tool",
        producer_id="probe",
        primary_trace_id=trace.id,
        level="conjecture",
        source_channel="tool_flag_scan",
        evidence_trace_ids=[trace.id],
        metadata={
            "source_tool": "probe",
            "source_trace_id": trace.id,
            "source_receipt_id": trace.receipt_id,
        },
    )
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="candidate_found",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    text = ContextAssembler(_StubAgent(project_root=tmp_path, run_id=run_id)).assemble()

    assert "claim_evidence=" in text
    assert claim.id in text
    assert "flag_found/conjecture/active" in text
    assert "flag{asm_candidate}" in text
    assert f"trace={trace.id}" in text
    assert f"receipt={trace.receipt_id}" in text
    assert "tool=probe" in text
    assert "candidate_found" in text
    assert "Set-Cookie" not in text
    assert "Authorization" not in text
    assert "super-secret-cookie" not in text
    assert "top-secret-token" not in text


def test_context_assembler_redacts_non_flag_claim_content_in_prompt_summary(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    run_id = "run-context-assembler-p2e-redacted-claim"
    state = CTFState(target="http://ctf.local", goal="拿到flag")
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
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="candidate_found",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    text = ContextAssembler(_StubAgent(project_root=tmp_path, run_id=run_id)).assemble()

    assert claim.id in text
    assert "credential_valid/conjecture/active" in text
    assert "username=admin" in text
    assert "password=<redacted>" in text
    assert "token=<redacted>" in text
    assert "super-secret-password" not in text
    assert "top-secret-token" not in text


def test_context_assembler_compacts_raw_body_claim_content_in_prompt_summary(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    run_id = "run-context-assembler-p4a2-raw-body-claim"
    state = CTFState(target="http://ctf.local", goal="get flag")
    trace = state.record_tool_receipt(
        tool_name="probe",
        arguments={"url": "http://ctf.local/"},
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
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="latest",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    text = ContextAssembler(_StubAgent(project_root=tmp_path, run_id=run_id)).assemble()

    assert "claim_evidence=" in text
    assert claim.id in text
    assert "credential_valid/conjecture/active" in text
    assert f"trace={trace.id}" in text
    assert f"receipt={trace.receipt_id}" in text
    assert "tool=probe" in text
    assert "<redacted raw body>" in text
    assert "auditEvidenceExport" not in text
    assert "p3SolveSnapshot" not in text
    assert "crewTrace" not in text
    for leaked in (
        "PING 127.0.0.1",
        "64 bytes from",
        "uid=33",
        "hunter2",
        "Bearer abc",
    ):
        assert leaked not in text


def test_context_assembler_does_not_inline_full_audit_export(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    run_id = "run-context-assembler-p2g-audit-export"
    state = CTFState(
        target="http://ctf.local/?token=target-token",
        goal="login with password=goal-password",
    )
    state.stop_reason = "stopped because secret=stop-secret"
    trace = state.record_tool_receipt(
        tool_name="probe",
        output_summary="password=output-password token=output-token",
        success=True,
    )
    state.create_claim(
        kind="credential_valid",
        content="username=admin password=claim-password token=claim-token",
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
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="candidate_found",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    text = ContextAssembler(_StubAgent(project_root=tmp_path, run_id=run_id)).assemble()

    assert "auditEvidenceExport" not in text
    assert "p2.audit_evidence.v1" not in text
    assert "password=<redacted>" in text
    for leaked in (
        "target-token",
        "goal-password",
        "stop-secret",
        "output-password",
        "output-token",
        "claim-password",
        "claim-token",
    ):
        assert leaked not in text


def test_context_assembler_includes_compact_p3_solve_signal(tmp_path) -> None:
    run_id = "run-context-assembler-p3-solve"
    state = CTFState(target="http://ctf.local", goal="get flag")
    node_id = state.record_solve_node(
        SolveNode(
            id="node-asm-p3",
            title=json.dumps({"token": "node-token"}),
            summary="password=node-password",
        )
    )
    brief_id = state.record_task_brief(
        TaskBrief(
            id="brief-asm-p3",
            node_id=node_id,
            objective="token=brief-token",
        )
    )
    state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-asm-p3",
            node_id=node_id,
            input_brief_id=brief_id,
            status="completed",
            output_summary=json.dumps({"authorization": "receipt-auth"}),
        )
    )
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    text = ContextAssembler(_StubAgent(project_root=tmp_path, run_id=run_id)).assemble()

    assert "solve_nodes=1" in text
    assert "task_briefs=1" in text
    assert "node_receipts=1" in text
    assert "p3SolveSnapshot" not in text
    for leaked in (
        "node-token",
        "node-password",
        "brief-token",
        "receipt-auth",
    ):
        assert leaked not in text


def test_context_assembler_includes_compact_p3_crew_trace_signal(tmp_path) -> None:
    run_id = "run-context-assembler-p3-crew"
    state = CTFState(target="http://ctf.local", goal="get flag")
    node_id = state.record_solve_node(
        SolveNode(
            id="node-crew-asm",
            title=json.dumps({"token": "node-token"}),
        )
    )
    brief_id = state.record_task_brief(
        TaskBrief(
            id="brief-crew-asm",
            node_id=node_id,
            worker_type="web token=worker-token",
            objective="password=brief-password",
        )
    )
    state.record_solve_node_receipt(
        SolveNodeReceipt(
            id="receipt-crew-asm",
            node_id=node_id,
            input_brief_id=brief_id,
            worker_id="worker-web cookie=worker-cookie",
            worker_type="web token=worker-token",
            status="completed",
            output_summary=json.dumps({"authorization": "receipt-auth"}),
        )
    )
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    text = ContextAssembler(_StubAgent(project_root=tmp_path, run_id=run_id)).assemble()

    assert "crew_workers=1" in text
    assert "crew_receipts=1" in text
    assert "worker_types=web token=<redacted>:1" in text
    assert "crewTrace" not in text
    for leaked in (
        "node-token",
        "worker-token",
        "brief-password",
        "worker-cookie",
        "receipt-auth",
    ):
        assert leaked not in text


def test_context_assembler_includes_compact_task_dag_signal_only(tmp_path) -> None:
    run_id = "run-context-assembler-p4b-task-dag"
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = TaskDAGPlan(id="plan-asm", metadata={"token": "plan-token"})
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            title="HTTP/1.1 200 OK\n<html>secret=body-secret</html>",
            goal="collect password=goal-password",
            status=TaskDAGStatus.SUCCEEDED,
        )
    )
    plan.add_node(
        TaskDAGNode(
            id="task-b",
            status=TaskDAGStatus.BLOCKED,
            depends_on=["task-a"],
            metadata={"authorization": "Bearer node-auth"},
        )
    )
    state.set_task_dag_plan(plan)
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    text = ContextAssembler(_StubAgent(project_root=tmp_path, run_id=run_id)).assemble()

    assert "task_dag_nodes=2" in text
    assert "task_dag_edges=1" in text
    assert "task_dag_statuses=blocked:1,succeeded:1" in text
    for forbidden in (
        "taskDagPlanReadback",
        "task_dag_plan",
        "nodes_by_id",
        "task-a",
        "task-b",
        "HTTP/1.1 200 OK",
        "<html",
        "body-secret",
        "goal-password",
        "plan-token",
        "node-auth",
    ):
        assert forbidden not in text
