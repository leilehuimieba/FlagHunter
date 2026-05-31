from __future__ import annotations

from types import SimpleNamespace

import pytest

import pentestagent.tools.notes as notes_module
from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from pentestagent.agents.pa_agent.ctf_state import CTFState
from pentestagent.harness.artifact_registry import ArtifactRegistry
from pentestagent.harness.session_ledger import SessionLedger
from pentestagent.tools.notes import set_notes_file


class _ArtifactRegistryRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])

    async def browser_action(self, action: str, **kwargs):
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


@pytest.mark.asyncio
async def test_dispatcher_registers_artifact_note_into_artifact_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_artifact_registry.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._setup_session_ledger(
        run_id="run-artifact-note",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-artifact-note",
        registry_root=tmp_path / "artifacts",
    )

    await dispatcher._store_note(
        key="ctf_backup_candidate",
        value="found backup/source candidate",
        category="artifact",
        url="http://ctf.local/www.zip",
        strategy_kind="backup_source_leak",
    )

    records = ArtifactRegistry(tmp_path / "artifacts").list_artifacts("run-artifact-note")
    events = SessionLedger(tmp_path / "ledgers").read_events("run-artifact-note")

    assert len(dispatcher.state.artifacts) == 1
    assert dispatcher.state.artifacts[0].name == "ctf_backup_candidate"
    assert dispatcher.state.artifacts[0].location == "http://ctf.local/www.zip"

    assert len(records) == 1
    assert records[0]["run_id"] == "run-artifact-note"
    assert records[0]["kind"] == "artifact"
    assert records[0]["title"] == "ctf_backup_candidate"
    assert records[0]["location"] == "http://ctf.local/www.zip"
    assert records[0]["producer"] == "backup_source_leak"
    assert records[0]["metadata"]["category"] == "backup_candidate"
    assert records[0]["metadata"]["note_category"] == "artifact"
    assert records[0]["metadata"]["content"] == "found backup/source candidate"
    assert records[0]["metadata"]["strategy_kind"] == "backup_source_leak"
    assert [event["event_type"] for event in events] == ["artifact_registered"]
    assert events[0]["payload"]["kind"] == "artifact"
    assert events[0]["payload"]["title"] == "ctf_backup_candidate"


@pytest.mark.asyncio
async def test_dispatcher_registers_artifact_forensics_note_with_truthful_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_artifact_forensics.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(runtime=_ArtifactRegistryRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._setup_session_ledger(
        run_id="run-artifact-forensics-note",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-artifact-forensics-note",
        registry_root=tmp_path / "artifacts",
    )

    await dispatcher._store_note(
        key="ctf_artifact_forensics",
        value='{"url":"http://ctf.local/challenge.zip","kind":"zip"}',
        category="artifact",
        url="http://ctf.local/challenge.zip",
        strategy_kind="artifact_forensics",
    )

    records = ArtifactRegistry(tmp_path / "artifacts").list_artifacts("run-artifact-forensics-note")
    events = SessionLedger(tmp_path / "ledgers").read_events("run-artifact-forensics-note")

    assert len(records) == 1
    assert records[0]["title"] == "ctf_artifact_forensics"
    assert records[0]["producer"] == "artifact_forensics"
    assert records[0]["metadata"]["category"] == "artifact_forensics_summary"
    assert records[0]["metadata"]["note_category"] == "artifact"
    assert records[0]["metadata"]["strategy_kind"] == "artifact_forensics"
    assert [event["event_type"] for event in events] == ["artifact_registered"]
    assert events[0]["payload"]["producer"] == "artifact_forensics"
