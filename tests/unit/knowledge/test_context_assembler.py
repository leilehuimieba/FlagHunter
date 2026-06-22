from __future__ import annotations

from types import SimpleNamespace

from flaghunter.agents.base_agent import AgentMessage
from flaghunter.agents.pa_agent.ctf_state import CTFState
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
