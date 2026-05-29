from __future__ import annotations

from types import SimpleNamespace

import pytest

import pentestagent.tools.notes as notes_module
from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from pentestagent.agents.pa_agent.ctf_state import CTFState
from pentestagent.harness.checkpoint_store import CheckpointStore
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
        checkpoint_root=tmp_path / "checkpoints",
    )

    store = CheckpointStore(tmp_path / "checkpoints")
    checkpoints = store.list_checkpoints("run-checkpoint-dispatcher")
    latest = store.latest_checkpoint("run-checkpoint-dispatcher")

    assert result.success is True
    assert result.flag == "flag{checkpoint_verified_ok}"
    assert [item["label"] for item in checkpoints] == [
        "dispatcher_started",
        "task_finished",
    ]
    assert latest is not None
    assert latest["metadata"]["success"] is True
    assert latest["metadata"]["flag"] == "flag{checkpoint_verified_ok}"
    restored = CTFState.from_snapshot(latest["state"])
    assert restored.target == "http://ctf.local"
    assert restored.verified_flags[0].value == "flag{checkpoint_verified_ok}"
