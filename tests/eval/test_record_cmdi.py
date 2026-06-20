"""Record→replay round-trip for the command-injection (RCE) chain.

Mirrors ``test_record.py`` but for ``generic_param_cmdi``: a GET ping form whose
``ip`` parameter is shell-injectable. Guards that the recorded fixture drives the
real ``CTFTaskDispatcher`` web chain to the same flag deterministically, and that
the committed on-disk fixture is faithful (real recon probes + a non-empty cmdi
proxy rule), not a hollow stub.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.eval.record import RecordingRuntime
from flaghunter.eval.replay import ReplayFixture, load_fixture, run_replay
from flaghunter.tools.notes import set_notes_file

FLAG_VALUE = "flag{cmdi_param_rce_ok}"
TARGET = "http://ctf.local/"


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


class _FakeCmdiRuntime:
    """Network-diagnostics page with a GET ping form vulnerable to command injection."""

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
            return {"url": TARGET, "title": "Network Diagnostics"}
        if action == "get_content":
            return {
                "content": "Network Diagnostics Tool. Ping a host to check connectivity.",
                "html": (
                    "<html><body><h1>Network Diagnostics</h1>"
                    "<form action=\"http://ctf.local/ping.php\" method=\"get\">"
                    "<input name=\"ip\" type=\"text\" value=\"127.0.0.1\" />"
                    "<input type=\"submit\" value=\"Ping\" />"
                    "</form></body></html>"
                ),
            }
        if action == "get_forms":
            return {
                "forms": [
                    {
                        "action": "http://ctf.local/ping.php",
                        "method": "get",
                        "inputs": [{"name": "ip", "type": "text"}],
                    }
                ]
            }
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected browser action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        url = str(kwargs.get("url") or "")
        # The cmdi probe injects `;cat /flag /flag.txt 2>/dev/null;id` into ip.
        # Mirror a real shell-exec page leaking uid + flag for that payload only.
        if "ping.php" in url and "cat" in url and "flag" in url:
            return {
                "status_code": 200,
                "body": (
                    "PING 127.0.0.1 (127.0.0.1): 56 data bytes\n"
                    "64 bytes from 127.0.0.1: icmp_seq=0 ttl=64 time=0.041 ms\n"
                    "uid=33(www-data) gid=33(www-data) groups=33(www-data)\n"
                    f"{FLAG_VALUE}\n"
                ),
            }
        return {"status_code": 404, "body": "not found"}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


@pytest.mark.asyncio
async def test_recorded_cmdi_fixture_replays_same_flag(isolated_notes):
    runtime = RecordingRuntime(_FakeCmdiRuntime())
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(target=TARGET, goal="拿到flag", type="web", hint="")

    assert result.success is True
    assert result.flag == FLAG_VALUE
    assert any(call["channel"] == "browser" for call in runtime.calls)
    assert any(call["channel"] == "proxy" for call in runtime.calls)

    fixture_data = runtime.dump_fixture(
        name="recorded_cmdi",
        target=TARGET,
        goal="拿到flag",
        type="web",
        hint="",
        expected_flag=FLAG_VALUE,
    )
    fixture = ReplayFixture.from_dict(json.loads(json.dumps(fixture_data)))
    replay_result = await run_replay(fixture)

    # The recon surface is real (a parseable ping form), not an empty shell.
    assert fixture.browser["get_forms"]["forms"][0]["action"].endswith("/ping.php")
    assert fixture.proxy_rules
    assert any("cat" in (rule.get("when", {}).get("url_contains") or "") for rule in fixture.proxy_rules)
    assert replay_result.success is True
    assert replay_result.actual_flag == FLAG_VALUE
    assert replay_result.reproduced is True


@pytest.mark.asyncio
async def test_committed_cmdi_fixture_is_faithful_and_reproduces():
    """The on-disk golden fixture must reproduce and not be a hollow stub."""
    fixture = load_fixture("cmdi_param_rce")

    # Non-empty recon probes (browser diagnose path) + a real cmdi proxy rule.
    assert fixture.browser.get("get_forms", {}).get("forms")
    assert fixture.proxy_rules
    assert any("cat" in (rule.get("when", {}).get("url_contains") or "") for rule in fixture.proxy_rules)

    result = await run_replay(fixture)
    assert result.success is True
    assert result.reproduced is True
    assert result.actual_flag == "flag{cmdi_param_rce_ok}"
