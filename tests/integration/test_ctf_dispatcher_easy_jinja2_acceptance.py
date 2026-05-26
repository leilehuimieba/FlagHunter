"""Acceptance coverage for Jinja2 SSTI probe -> identify -> exploit chain."""

from __future__ import annotations

import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

import pentestagent.tools.notes as notes_module
from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from pentestagent.runtime.runtime import LocalRuntime
from pentestagent.tools.notes import set_notes_file


FLAG_VALUE = "flag{easy_jinja2_acceptance_ok}"


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
def easy_jinja2_server():
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
                    (
                        "<html><body>"
                        "<h1>easy_jinja2</h1>"
                        "<a href='/error?msg=Error'>render</a>"
                        "</body></html>"
                    ).encode("utf-8")
                )
                return

            if parsed.path == "/error":
                params = parse_qs(parsed.query)
                msg = params.get("msg", ["Error"])[0]
                rendered = msg
                if msg == "{{7*7}}":
                    rendered = "49"
                elif msg == "{{handler.settings}}":
                    rendered = "ORZ"
                elif msg in {"{{config}}", "{{self._TemplateReference__context.config}}"}:
                    rendered = (
                        f"config dump: SECRET_KEY=dev; framework=flask; {FLAG_VALUE}"
                    )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<html><body>{rendered}</body></html>".encode("utf-8"))
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
async def test_ctf_dispatcher_acceptance_solves_easy_jinja2_chain(
    tmp_path: Path, monkeypatch, isolated_notes, easy_jinja2_server
):
    monkeypatch.chdir(tmp_path)

    runtime = LocalRuntime()
    await runtime.start()
    try:
        async def _browser_missing(action: str, **kwargs):
            if action == "diagnose":
                return {
                    "available": False,
                    "error": "rendered browser intentionally unavailable in acceptance stub",
                }
            return _playwright_missing_error()

        monkeypatch.setattr(runtime, "browser_action", _browser_missing)

        dispatcher = CTFTaskDispatcher(
            runtime=runtime,
            progress_callback=None,
            verification_callback=lambda flag: "yes",
        )
        result = await dispatcher.run(
            target=easy_jinja2_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        assert result.success is True
        assert result.flag == FLAG_VALUE
        assert result.chain_used == ["web"]
        assert dispatcher.state is not None
        assert any(
            obs.kind == "ssti_engine_identified" and obs.value == "jinja2"
            for obs in dispatcher.state.observations
        )

        requests = easy_jinja2_server["requests"]
        assert any(
            entry["path"] == "/error"
            and parse_qs(entry["query"]).get("msg", [""])[0] == "{{7*7}}"
            for entry in requests
        )
        assert any(
            entry["path"] == "/error"
            and parse_qs(entry["query"]).get("msg", [""])[0] in {"{{config}}", "{{self._TemplateReference__context.config}}"}
            for entry in requests
        )
    finally:
        await runtime.stop()
