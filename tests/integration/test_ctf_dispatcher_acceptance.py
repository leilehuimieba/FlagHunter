"""Acceptance coverage for the deterministic /ctf dispatcher.

This eval pack is intentionally small. It guards the three behaviors that would
most damage trust in the new SQLi CTF flow if they regressed:

1. browserless HTTP fallback can still solve a simple auth-form SQLi challenge
2. optional tooling (sqlmap / web_search / browser) does not block the shortest
   successful path when http_request is enough
3. when core recon deps are missing, the dispatcher reports that honestly
   instead of pretending it merely failed to find a flag
"""

from __future__ import annotations

import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

import pentestagent.tools.notes as notes_module
from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from pentestagent.runtime.runtime import LocalRuntime
from pentestagent.tools.notes import get_all_notes_sync, set_notes_file
from pentestagent.tools.tool_guard import ToolStatus


FLAG_VALUE = "flag{acceptance_dispatcher_sqli_ok}"


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
def easy_sqli_server():
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
                      <h1>EasySQL</h1>
                      <form action="/check.php" method="GET">
                        <input type="text" name="username" />
                        <input type="text" name="password" />
                      </form>
                    </body></html>
                    """
                )
                return

            if parsed.path == "/check.php":
                params = parse_qs(parsed.query)
                username = params.get("username", [""])[0]
                if username == "1' or 1=1#":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(
                        f"Login Success! {FLAG_VALUE}".encode("utf-8")
                    )
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("NO,Wrong username password！！！".encode("utf-8"))
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
async def test_ctf_dispatcher_acceptance_solves_auth_form_sqli_via_http_fallback(
    tmp_path: Path, monkeypatch, isolated_notes, easy_sqli_server
):
    monkeypatch.chdir(tmp_path)

    runtime = LocalRuntime()
    await runtime.start()
    try:
        async def _browser_missing(action: str, **kwargs):
            return _playwright_missing_error()

        monkeypatch.setattr(runtime, "browser_action", _browser_missing)

        dispatcher = CTFTaskDispatcher(
            runtime=runtime,
            progress_callback=None,
            verification_callback=lambda flag: "yes",
        )
        result = await dispatcher.run(
            target=easy_sqli_server["base_url"],
            goal="拿到flag",
            type="sqli",
            hint="",
        )

        assert result.success is True
        assert result.flag == FLAG_VALUE
        assert result.chain_used == ["sqli"]
        assert result.reason == "auth form SQLi bypass"

        requests = easy_sqli_server["requests"]
        assert requests[0]["path"] == "/"
        assert any(
            entry["path"] == "/check.php"
            and "username=ctf_probe_user" in entry["query"]
            for entry in requests
        )
        assert any(
            entry["path"] == "/check.php"
            and "username=1%27+or+1%3D1%23" in entry["query"]
            for entry in requests
        )

        notes = get_all_notes_sync()
        assert "ctf_sqli_auth_bypass" in notes
        assert "ctf_flag" in notes
        assert FLAG_VALUE in notes["ctf_flag"]["content"]
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_ctf_dispatcher_acceptance_shortest_path_not_blocked_by_optional_tools(
    tmp_path: Path, monkeypatch, isolated_notes, easy_sqli_server
):
    monkeypatch.chdir(tmp_path)

    runtime = LocalRuntime()
    await runtime.start()
    try:
        async def _browser_missing(action: str, **kwargs):
            return _playwright_missing_error()

        monkeypatch.setattr(runtime, "browser_action", _browser_missing)

        def _check_with_optional_tools_missing(self, tool_name: str):
            normalized = str(tool_name or "").strip().lower()
            if normalized in {"sqlmap", "web_search", "browser"}:
                return ToolStatus(available=False, path=None, version=None)
            if normalized == "http_request":
                return ToolStatus(
                    available=True,
                    path="runtime.proxy_action",
                    version="httpx",
                )
            if normalized == "terminal":
                return ToolStatus(
                    available=True,
                    path="runtime.execute_command",
                    version=None,
                )
            return ToolStatus(available=True, path=f"synthetic:{normalized}", version=None)

        monkeypatch.setattr(
            "pentestagent.tools.tool_guard.ToolGuard.check",
            _check_with_optional_tools_missing,
        )

        dispatcher = CTFTaskDispatcher(
            runtime=runtime,
            progress_callback=None,
            verification_callback=lambda flag: "yes",
        )
        result = await dispatcher.run(
            target=easy_sqli_server["base_url"],
            goal="拿到flag",
            type="sqli",
            hint="",
        )

        assert result.success is True
        assert result.flag == FLAG_VALUE
        assert result.missing_tools == []
        assert result.reason == "auth form SQLi bypass"
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_ctf_dispatcher_acceptance_reports_missing_core_recon_dependencies(
    tmp_path: Path, monkeypatch, isolated_notes
):
    monkeypatch.chdir(tmp_path)

    runtime = LocalRuntime()
    await runtime.start()
    try:
        async def _browser_missing(action: str, **kwargs):
            return _playwright_missing_error()

        async def _http_missing(action: str, **kwargs):
            return {"error": "httpx not installed. Install with: pip install httpx"}

        monkeypatch.setattr(runtime, "browser_action", _browser_missing)
        monkeypatch.setattr(runtime, "proxy_action", _http_missing)

        dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)
        result = await dispatcher.run(
            target="http://ctf.local/",
            goal="拿到flag",
            type="sqli",
            hint="",
        )

        assert result.success is False
        assert sorted(result.missing_tools) == ["browser", "http_request"]
        assert "侦察依赖缺失" in result.reason

        notes = get_all_notes_sync()
        assert "tool_missing_ctf_chain" in notes
        assert "browser" in notes["tool_missing_ctf_chain"]["content"]
        assert "http_request" in notes["tool_missing_ctf_chain"]["content"]
    finally:
        await runtime.stop()
