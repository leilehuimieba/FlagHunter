from __future__ import annotations

from pentestagent.agents.pa_agent.ctf_state import CTFState
from pentestagent.harness.artifact_registry import ArtifactRegistry
from pentestagent.harness.checkpoint_store import CheckpointStore
from pentestagent.harness.session_ledger import SessionLedger
from pentestagent.knowledge.session_context import SessionContextView


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
