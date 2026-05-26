"""Acceptance coverage for hint-followup -> include/lfi secondary link consumption."""

from __future__ import annotations

import base64
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


FLAG_VALUE = "flag{include_acceptance_ok}"


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
def include_style_server():
    recorded: list[dict] = []
    source_blob = (
        "<?php\n"
        'echo "Can you find out the flag?";\n'
        f"//{FLAG_VALUE}\n"
    )
    encoded_source = base64.b64encode(source_blob.encode("utf-8")).decode("ascii")
    hint_html = '<meta charset="utf8">\n<a href="?file=flag.php">tips</a>'

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            pass

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query, keep_blank_values=True)
            recorded.append(
                {
                    "method": "GET",
                    "path": parsed.path,
                    "query": parsed.query,
                    "headers": dict(self.headers),
                }
            )

            if parsed.path in {"/", "/hints.txt", "/welcome.txt", "/flag.txt"} and "file" not in params:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(hint_html.encode("utf-8"))
                return

            if parsed.path == "/" and params.get("file", [""])[0] == "flag.php":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write('<meta charset="utf8">\nCan you find out the flag?'.encode("utf-8"))
                return

            if parsed.path == "/":
                file_value = params.get("file", [""])[0]
                if file_value in {
                    "php://filter/convert.base64-encode/resource=flag.php",
                    "php://filter/read=convert.base64-encode/resource=flag.php",
                }:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(f"<meta charset=\"utf8\">\\n{encoded_source}".encode("utf-8"))
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
async def test_ctf_dispatcher_acceptance_consumes_secondary_include_link_and_decodes_runtime_source(
    tmp_path: Path, monkeypatch, isolated_notes, include_style_server
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
            target=include_style_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        assert result.success is True
        assert result.flag == FLAG_VALUE
        assert dispatcher.state is not None
        assert any(
            item.kind == "derived_link" and item.value.endswith("/?file=flag.php")
            for item in dispatcher.state.observations
        )
        assert any(
            item.kind == "decoded_source_blob" and FLAG_VALUE in item.value
            for item in dispatcher.state.observations
        )
        assert any(
            entry["path"] == "/" and "file=flag.php" in entry["query"]
            for entry in include_style_server["requests"]
        )
        assert any(
            entry["path"] == "/" and "php%3A%2F%2Ffilter%2Fconvert.base64-encode%2Fresource%3Dflag.php" in entry["query"]
            for entry in include_style_server["requests"]
        )
    finally:
        await runtime.stop()
