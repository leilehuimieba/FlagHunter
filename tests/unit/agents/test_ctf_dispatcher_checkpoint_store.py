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
    assert [event["event_type"] for event in events] == [
        "dispatcher_started",
        "checkpoint_written",
        "verification_decision",
        "artifact_registered",
        "task_finished",
        "checkpoint_written",
    ]
    assert latest is not None
    assert latest["metadata"]["success"] is True
    assert latest["metadata"]["flag"] == "flag{checkpoint_verified_ok}"
    assert events[1]["payload"]["label"] == "dispatcher_started"
    assert events[3]["payload"]["title"] == "ctf_flag"
    assert events[5]["payload"]["label"] == "task_finished"
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
