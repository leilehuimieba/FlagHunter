from __future__ import annotations

from types import SimpleNamespace

import pytest

import pentestagent.tools.notes as notes_module
from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from pentestagent.agents.pa_agent.ctf_state import CTFState
from pentestagent.harness.checkpoint_store import CheckpointStore
from pentestagent.harness.session_ledger import SessionLedger
from pentestagent.tools.notes import set_notes_file


class _CheckpointRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "checkpoint-home"}
        if action == "get_content":
            return {
                "content": "welcome flag{checkpoint_verified_ok}",
                "html": "<html><body>flag{checkpoint_verified_ok}</body></html>",
            }
        if action == "get_forms":
            return {"forms": []}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


@pytest.mark.asyncio
async def test_dispatcher_writes_start_and_finish_checkpoints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_checkpoint.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(
        runtime=_CheckpointRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="web",
        hint="",
        run_id="run-checkpoint-dispatcher",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    store = CheckpointStore(tmp_path / "checkpoints")
    events = SessionLedger(tmp_path / "ledgers").read_events("run-checkpoint-dispatcher")
    checkpoints = store.list_checkpoints("run-checkpoint-dispatcher")
    latest = store.latest_checkpoint("run-checkpoint-dispatcher")

    assert result.success is True
    assert result.flag == "flag{checkpoint_verified_ok}"
    assert [item["label"] for item in checkpoints] == [
        "dispatcher_started",
        "task_finished",
    ]
    event_types = [event["event_type"] for event in events]
    assert "dispatcher_started" in event_types
    assert "checkpoint_written" in event_types
    assert "verification_decision" in event_types
    assert "artifact_registered" in event_types
    assert "task_finished" in event_types
    assert event_types.index("dispatcher_started") < event_types.index("checkpoint_written")
    assert event_types.index("checkpoint_written") < event_types.index("verification_decision")
    assert event_types.index("verification_decision") < event_types.index("artifact_registered")
    assert event_types.index("artifact_registered") < event_types.index("task_finished")
    assert event_types[-1] == "checkpoint_written"
    assert latest is not None
    assert latest["metadata"]["success"] is True
    assert latest["metadata"]["flag"] == "flag{checkpoint_verified_ok}"
    assert events[1]["payload"]["label"] == "dispatcher_started"
    artifact_event = next(event for event in events if event["event_type"] == "artifact_registered")
    assert artifact_event["payload"]["title"] == "ctf_flag"
    assert artifact_event["payload"]["producer"] == "verifier"
    assert artifact_event["payload"]["metadata"]["category"] == "flag_verified"
    assert artifact_event["payload"]["metadata"]["note_category"] == "artifact"
    assert events[-1]["payload"]["label"] == "task_finished"
    restored = CTFState.from_snapshot(latest["state"])
    assert restored.target == "http://ctf.local"
    assert restored.verified_flags[0].value == "flag{checkpoint_verified_ok}"


@pytest.mark.asyncio
async def test_dispatcher_persists_resume_ingress_into_start_event_and_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_checkpoint_resume.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(
        runtime=_CheckpointRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="web",
        hint="",
        challenge_context={
            "resumeContext": {
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "checkpointLabel": "task_failed",
                "stopReason": "wrong_flag_feedback",
                "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
            }
        },
        run_id="run-checkpoint-resume",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    store = CheckpointStore(tmp_path / "checkpoints")
    events = SessionLedger(tmp_path / "ledgers").read_events("run-checkpoint-resume")
    checkpoints = store.list_checkpoints("run-checkpoint-resume")
    started_checkpoint = checkpoints[0]

    assert result.success is True
    assert events[0]["event_type"] == "dispatcher_started"
    assert events[0]["payload"]["has_resume_context"] is True
    assert events[0]["payload"]["resume_run_id"] == "run-prev-1"
    assert events[0]["payload"]["resume_checkpoint_id"] == "checkpoint-prev-1"
    assert started_checkpoint["label"] == "dispatcher_started"
    assert started_checkpoint["metadata"]["has_resume_context"] is True
    assert started_checkpoint["metadata"]["resume_run_id"] == "run-prev-1"
    assert started_checkpoint["metadata"]["resume_checkpoint_id"] == "checkpoint-prev-1"
    assert events[1]["event_type"] == "checkpoint_written"
    assert events[1]["payload"]["metadata"]["has_resume_context"] is True
    assert events[1]["payload"]["metadata"]["resume_run_id"] == "run-prev-1"
    assert events[1]["payload"]["metadata"]["resume_checkpoint_id"] == "checkpoint-prev-1"


def test_restore_context_hydrates_state_from_resume_checkpoint(tmp_path) -> None:
    previous_state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    previous_state.add_observation(
        "ssti_engine_identified",
        "tornado",
        source="resume-checkpoint",
        metadata={"engine": "tornado"},
    )
    previous_state.add_flag(
        "flag{runtime_from_checkpoint}",
        level="runtime",
        evidence_source="runtime-http",
        rationale="carried from previous run",
    )
    previous_state.add_flag(
        "flag{rejected_from_checkpoint}",
        level="rejected",
        evidence_source="user-confirm",
        rationale="wrong flag from previous run",
    )

    store = CheckpointStore(tmp_path / "checkpoints")
    record = store.save_checkpoint(
        run_id="run-prev-1",
        label="task_failed",
        state_snapshot=previous_state.to_snapshot(),
        metadata={"reason": "wrong_flag_feedback"},
    )

    dispatcher = CTFTaskDispatcher(
        runtime=_CheckpointRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(target="http://ctf.local", goal="继续拿到flag")
    dispatcher._challenge_context = {
        "resumeContext": {
            "runId": "run-prev-1",
            "checkpointId": record["checkpoint_id"],
            "summary": "resume from prior checkpoint",
        }
    }
    dispatcher._setup_checkpoint_store(
        run_id="run-current-1",
        checkpoint_root=tmp_path / "checkpoints",
    )

    dispatcher._restore_context()

    assert dispatcher.state is not None
    assert dispatcher.state.goal == "继续拿到flag"
    assert dispatcher.state.target == "http://ctf.local"
    assert dispatcher.state.detected_type == "web"
    assert any(
        obs.kind == "ssti_engine_identified" and obs.value == "tornado"
        for obs in dispatcher.state.observations
    )
    assert dispatcher.state.has_flag("flag{runtime_from_checkpoint}", level="runtime")
    assert dispatcher.state.has_flag("flag{rejected_from_checkpoint}", level="rejected")


def test_restored_checkpoint_state_can_change_followup_strategy_choice(tmp_path) -> None:
    previous_state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    previous_state.add_observation(
        "ssti_engine_identified",
        "tornado",
        source="resume-checkpoint",
        metadata={"engine": "tornado"},
    )

    store = CheckpointStore(tmp_path / "checkpoints")
    record = store.save_checkpoint(
        run_id="run-prev-2",
        label="task_failed",
        state_snapshot=previous_state.to_snapshot(),
        metadata={"reason": "resume for engine exploit"},
    )

    dispatcher = CTFTaskDispatcher(
        runtime=_CheckpointRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(target="http://ctf.local", goal="继续拿到flag")
    dispatcher._challenge_context = {
        "resumeContext": {
            "runId": "run-prev-2",
            "checkpointId": record["checkpoint_id"],
            "summary": "resume from engine checkpoint",
        }
    }
    dispatcher._setup_checkpoint_store(
        run_id="run-current-2",
        checkpoint_root=tmp_path / "checkpoints",
    )

    dispatcher._restore_context()

    strategy = dispatcher._select_primary_strategy(
        "web",
        target="http://ctf.local",
        page_features={
            "content": "",
            "html": "",
            "endpoints": ["/error?msg=test"],
            "raw_links": ["http://ctf.local/error?msg=test"],
            "forms": [],
        },
        hint=(
            "[control_decision]\n"
            "decisionKind=direct_execute\n"
            "nextAction=exploit_identified_engine\n"
            "driver=blackboard.identified_engine\n"
            "reason=identified engine present in blackboard"
        ),
    )

    assert strategy is not None
    assert strategy.kind == "ssti_exploit"
