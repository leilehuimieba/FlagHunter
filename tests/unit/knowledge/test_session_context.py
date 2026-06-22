from __future__ import annotations

from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.harness.artifact_registry import ArtifactRegistry
from flaghunter.harness.checkpoint_store import CheckpointStore
from flaghunter.harness.session_ledger import SessionLedger
from flaghunter.agents.pa_agent.session_context import (
    SessionContextView,
    build_workspace_run_context,
)


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
    assert context["resumeContext"] == {
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
