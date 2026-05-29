from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import pentestagent.tools.notes as notes_module
from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from pentestagent.tools.notes import get_all_notes_sync, set_notes_file
from tests.integration.local_challenge_catalog import (
    build_challenge_context,
    get_local_challenge_sample,
)


pytestmark = pytest.mark.integration


class _CommandResult:
    def __init__(self, exit_code: int, stdout: str = "", stderr: str = ""):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class _BackupNodeAppCandidateRuntime:
    def __init__(self):
        self.environment = type("Env", (), {"available_tools": []})()
        self.commands: list[str] = []
        self.requests: list[tuple[str, str]] = []

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://127.0.0.1:3000/", "title": "backup_node_app"}
        if action == "get_content":
            return {
                "content": "backup node app config panel",
                "html": "<html><body><h1>backup node app</h1></body></html>",
            }
        if action == "get_forms":
            return {"forms": []}
        return {"error": f"unexpected browser action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        self.requests.append((action, str(kwargs.get("url") or "")))
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 300):
        self.commands.append(command)
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return _CommandResult(
            completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@pytest.fixture
def isolated_notes(tmp_path: Path):
    notes_file = tmp_path / "notes.json"
    set_notes_file(notes_file)
    notes_module._notes.clear()
    notes_module._loaded_notes_file = None
    yield notes_file
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_backup_node_app_zip_candidate_eval_consumes_local_artifact_without_false_verified(
    monkeypatch,
    isolated_notes,
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    sample = get_local_challenge_sample("backup_node_app")
    runtime = _BackupNodeAppCandidateRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target=sample.target,
        goal=sample.minimal_prompt,
        type="auto",
        challenge_context=build_challenge_context(sample, variant="zip"),
    )

    assert result.success is False
    assert result.flag is None
    assert result.reason
    assert "misc" in result.chain_used
    assert runtime.commands, "expected local artifact analysis command to run"

    notes = get_all_notes_sync()
    assert "ctf_artifact_forensics" in notes

    assert dispatcher.state is not None
    assert dispatcher.state.verified_flags == []
    assert any(obs.kind == "artifact_forensics_summary" for obs in dispatcher.state.observations)
