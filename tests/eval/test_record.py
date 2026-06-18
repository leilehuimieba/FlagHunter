"""Recording runtime tests for eval fixture generation."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.eval.record import RecordingRuntime
from flaghunter.eval.replay import ReplayFixture, run_replay
from flaghunter.tools.notes import set_notes_file


FLAG_VALUE = "flag{record_replay_sqli_ok}"


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


class _FakeSQLiRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])

    async def browser_action(self, action: str, **kwargs):
        if action == "diagnose":
            return {
                "available": True,
                "rendered_dom": False,
                "supports_actions": [
                    "navigate",
                    "get_content",
                    "get_forms",
                    "get_cookies",
                ],
            }
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "EasySQL"}
        if action == "get_content":
            return {
                "content": "EasySQL username password login",
                "html": """
                <html><body>
                  <form action="http://ctf.local/check.php" method="get">
                    <input name="username" type="text" />
                    <input name="password" type="text" />
                  </form>
                </body></html>
                """,
            }
        if action == "get_forms":
            return {
                "forms": [
                    {
                        "action": "http://ctf.local/check.php",
                        "method": "get",
                        "inputs": [
                            {"name": "username", "type": "text"},
                            {"name": "password", "type": "text"},
                        ],
                    }
                ]
            }
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected browser action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        if action != "request":
            return {"status_code": 404, "body": "not found"}

        url = str(kwargs.get("url") or "")
        if "check.php" in url and "username=ctf_probe_user" in url:
            return {"status_code": 200, "body": "NO,Wrong username password!!!"}
        if "check.php" in url and "1%27+or+1%3D1%23" in url:
            return {
                "status_code": 200,
                "body": f"Login Success! {FLAG_VALUE}",
            }
        return {"status_code": 200, "body": "NO,Wrong username password!!!"}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


@pytest.mark.asyncio
async def test_recorded_fixture_replays_same_flag(isolated_notes):
    runtime = RecordingRuntime(_FakeSQLiRuntime())
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint="",
    )

    assert result.success is True
    assert result.flag == FLAG_VALUE
    assert any(call["channel"] == "browser" for call in runtime.calls)
    assert any(call["channel"] == "proxy" for call in runtime.calls)

    fixture_data = runtime.dump_fixture(
        name="recorded_sqli",
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint="",
        expected_flag=FLAG_VALUE,
    )
    fixture = ReplayFixture.from_dict(json.loads(json.dumps(fixture_data)))
    replay_result = await run_replay(fixture)

    assert fixture.browser["get_content"]["content"].startswith("EasySQL")
    assert fixture.proxy_rules
    assert replay_result.success is True
    assert replay_result.actual_flag == FLAG_VALUE
    assert replay_result.reproduced is True
