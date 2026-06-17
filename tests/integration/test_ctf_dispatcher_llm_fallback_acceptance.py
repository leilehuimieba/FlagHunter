"""Acceptance coverage for Phase 5.7 LLM-driven fallback on unknown web surfaces."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.runtime.runtime import LocalRuntime
from flaghunter.tools.notes import set_notes_file


FLAG_VALUE = "flag{llm_unknown_web_acceptance_ok}"


class _FakeLLM:
    def __init__(self, replies: list[dict]):
        self._replies = list(replies)
        self.calls: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        if not self._replies:
            return "{}"
        return json.dumps(self._replies.pop(0), ensure_ascii=False)


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


@pytest.fixture
def unknown_web_server():
    recorded: list[dict] = []

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            pass

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            recorded.append(
                {
                    "method": "GET",
                    "path": parsed.path,
                    "query": parsed.query,
                    "headers": dict(self.headers),
                }
            )

            if parsed.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"""
                    <html><body>
                      <h1>mystery portal</h1>
                      <p>no forms, no upload, no obvious backup, no standard challenge shape</p>
                      <a href="/about">about</a>
                    </body></html>
                    """
                )
                return

            if parsed.path == "/about":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"just a boring page")
                return

            if parsed.path == "/admin/secret.txt":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(FLAG_VALUE.encode("utf-8"))
                return

            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{server.server_port}"
    for _ in range(20):
        try:
            with urllib.request.urlopen(base_url, timeout=2):
                break
        except Exception:
            continue

    yield {"base_url": base_url, "requests": recorded}

    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


def _playwright_missing_error() -> dict[str, str]:
    return {
        "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
    }


@pytest.mark.asyncio
async def test_ctf_dispatcher_acceptance_unknown_web_uses_llm_fallback(
    tmp_path: Path, monkeypatch, isolated_notes, unknown_web_server
):
    monkeypatch.chdir(tmp_path)

    runtime = LocalRuntime()
    await runtime.start()
    try:
        async def _browser_missing(action: str, **kwargs):
            return _playwright_missing_error()

        monkeypatch.setattr(runtime, "browser_action", _browser_missing)

        llm = _FakeLLM(
            [
                {
                    "action_type": "http_request",
                    "tool_name": "http_request",
                    "rationale": "known strategies found no anchor; probe secret-looking admin text file directly",
                    "payload": {"method": "GET", "url": f"{unknown_web_server['base_url']}/admin/secret.txt"},
                    "expected_signal": "200 且 body 含 flag",
                    "next_if_fail": "switch chain",
                }
            ]
        )

        dispatcher = CTFTaskDispatcher(
            runtime=runtime,
            llm=llm,
            progress_callback=None,
            verification_callback=lambda flag: "yes",
        )
        result = await dispatcher.run(
            target=unknown_web_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        assert result.success is True
        assert result.flag == FLAG_VALUE
        assert dispatcher.state is not None
        assert dispatcher.state.llm_exploration_steps >= 1
        assert any(item.value == FLAG_VALUE for item in dispatcher.state.verified_flags)
        assert any(
            isinstance(item, dict)
            and item.get("type") == "llm_pre_action_reasoning"
            and item.get("approve") is True
            for item in dispatcher.state.pre_action_reasonings
        )
        assert any(
            item.kind == "llm_exploration_step"
            and item.metadata.get("verifier_decision") == "verified"
            for item in dispatcher.state.observations
        )
        assert any(entry["path"] == "/admin/secret.txt" for entry in unknown_web_server["requests"])
        assert llm.calls, "LLM fallback should be invoked on unknown web surfaces"
    finally:
        await runtime.stop()
