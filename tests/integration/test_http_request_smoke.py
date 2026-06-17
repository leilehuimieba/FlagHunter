"""Integration smoke coverage for the http_request tool."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.runtime import LocalRuntime
from flaghunter.tools import ToolExecutor
from flaghunter.tools.notes import get_all_notes_sync, set_notes_file
from flaghunter.tools.registry import get_tool

import flaghunter.tools.http_request  # noqa: F401


SID_VALUE = "smoke-admin-sid"
FLAG_VALUE = "flag{http_request_smoke_cookie_flow}"


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
def easy_login_like_server():
    recorded: list[dict] = []

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            pass

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            recorded.append(
                {
                    "method": "POST",
                    "path": self.path,
                    "body": body,
                    "headers": dict(self.headers),
                }
            )

            if self.path == "/login":
                fields = parse_qs(body)
                if fields.get("username") == ["demo"] and fields.get("password") == [
                    "pw"
                ]:
                    self.send_response(200)
                    self.send_header("Set-Cookie", f"sid={SID_VALUE}; Path=/")
                    self.end_headers()
                    self.wfile.write(b"login ok")
                    return

                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"bad login")
                return

            if self.path == "/visit":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"visit queued")
                return

            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")

        def do_GET(self):  # noqa: N802
            recorded.append(
                {
                    "method": "GET",
                    "path": self.path,
                    "body": "",
                    "headers": dict(self.headers),
                }
            )

            if self.path == "/admin":
                cookie = self.headers.get("Cookie", "")
                if f"sid={SID_VALUE}" in cookie:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(f"welcome admin\n{FLAG_VALUE}\n".encode("utf-8"))
                    return

                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"forbidden")
                return

            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield {
        "base_url": f"http://127.0.0.1:{server.server_port}",
        "requests": recorded,
    }

    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


@pytest.mark.asyncio
async def test_http_request_smoke_login_visit_admin_cookie_flow(
    tmp_path: Path, monkeypatch, isolated_notes, easy_login_like_server
):
    monkeypatch.chdir(tmp_path)

    runtime = LocalRuntime()
    await runtime.start()
    try:
        tool = get_tool("http_request")
        assert tool is not None

        executor = ToolExecutor(runtime=runtime, timeout=10)
        base_url = easy_login_like_server["base_url"]

        login = await executor.execute(
            tool,
            {
                "method": "POST",
                "url": f"{base_url}/login",
                "data": {"username": "demo", "password": "pw"},
                "timeout": 5,
            },
        )
        assert login.success is True
        assert "Status Code: 200" in (login.result or "")
        assert f"sid={SID_VALUE}" in (login.result or "")

        visit = await executor.execute(
            tool,
            {
                "method": "POST",
                "url": f"{base_url}/visit",
                "data": {"path": "/profile/demo"},
                "timeout": 5,
            },
        )
        assert visit.success is True
        assert "visit queued" in (visit.result or "")

        admin = await executor.execute(
            tool,
            {
                "method": "GET",
                "url": f"{base_url}/admin",
                "headers": {"Cookie": f"sid={SID_VALUE}"},
                "timeout": 5,
            },
        )
        assert admin.success is True
        assert FLAG_VALUE in (admin.result or "")

        requests = easy_login_like_server["requests"]
        assert [entry["path"] for entry in requests[:3]] == [
            "/login",
            "/visit",
            "/admin",
        ]
        assert "username=demo" in requests[0]["body"]
        assert "password=pw" in requests[0]["body"]
        assert requests[2]["headers"].get("Cookie") == f"sid={SID_VALUE}"

        notes = get_all_notes_sync()
        assert any(
            note.get("content") == FLAG_VALUE
            and (note.get("metadata") or {}).get("source_tool") == "http_request"
            for note in notes.values()
        )
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_proxy_action_persists_session_cookie_between_requests(
    tmp_path: Path, monkeypatch, isolated_notes, easy_login_like_server
):
    monkeypatch.chdir(tmp_path)

    runtime = LocalRuntime()
    await runtime.start()
    try:
        tool = get_tool("http_request")
        assert tool is not None

        executor = ToolExecutor(runtime=runtime, timeout=10)
        base_url = easy_login_like_server["base_url"]

        login = await executor.execute(
            tool,
            {
                "method": "POST",
                "url": f"{base_url}/login",
                "data": {"username": "demo", "password": "pw"},
                "timeout": 5,
            },
        )
        assert login.success is True
        assert f"sid={SID_VALUE}" in (login.result or "")

        admin = await executor.execute(
            tool,
            {
                "method": "GET",
                "url": f"{base_url}/admin",
                "timeout": 5,
            },
        )
        assert admin.success is True
        assert FLAG_VALUE in (admin.result or "")

        requests = easy_login_like_server["requests"]
        assert [entry["path"] for entry in requests[:2]] == ["/login", "/admin"]
        assert requests[1]["headers"].get("Cookie") == f"sid={SID_VALUE}"
    finally:
        await runtime.stop()
