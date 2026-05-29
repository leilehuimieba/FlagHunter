from __future__ import annotations

from pentestagent.agents.pa_agent.ctf_state import CTFState
from pentestagent.harness.checkpoint_store import CheckpointStore


def test_ctf_state_snapshot_roundtrip_preserves_artifacts_flags_and_stop_reason() -> None:
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.add_observation(
        "response_body",
        "flag candidate in source",
        source="backup_source_leak",
    )
    state.add_artifact(
        "ctf_backup_candidate",
        location="http://ctf.local/www.zip",
        source="notes",
        metadata={"category": "artifact"},
    )
    state.add_flag(
        "flag{checkpoint_runtime_ok}",
        level="verified",
        evidence_source="http-response",
        rationale="verified from runtime",
        confidence=1.0,
    )
    state.stop_reason = "flag_verified"

    restored = CTFState.from_snapshot(state.to_snapshot())

    assert restored.target == "http://ctf.local"
    assert restored.goal == "拿到flag"
    assert restored.observations[0].kind == "response_body"
    assert restored.artifacts[0].name == "ctf_backup_candidate"
    assert restored.verified_flags[0].value == "flag{checkpoint_runtime_ok}"
    assert restored.stop_reason == "flag_verified"


def test_checkpoint_store_saves_and_loads_latest_state_snapshot(tmp_path) -> None:
    store = CheckpointStore(tmp_path)
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_reason = "verification_pending"

    first = store.save_checkpoint(
        run_id="run-checkpoint-1",
        label="dispatcher_started",
        state_snapshot=state.to_snapshot(),
        metadata={"phase": "start"},
    )

    state.stop_reason = "flag_verified"
    state.add_flag(
        "flag{checkpoint_latest_ok}",
        level="verified",
        evidence_source="http-response",
        confidence=1.0,
    )
    second = store.save_checkpoint(
        run_id="run-checkpoint-1",
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={"phase": "finish", "success": True},
    )

    checkpoints = store.list_checkpoints("run-checkpoint-1")
    latest = store.latest_checkpoint("run-checkpoint-1")

    assert [item["checkpoint_id"] for item in checkpoints] == [
        first["checkpoint_id"],
        second["checkpoint_id"],
    ]
    assert latest is not None
    assert latest["label"] == "task_finished"
    assert latest["metadata"]["success"] is True
    restored = CTFState.from_snapshot(latest["state"])
    assert restored.stop_reason == "flag_verified"
    assert restored.verified_flags[0].value == "flag{checkpoint_latest_ok}"
