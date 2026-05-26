"""Acceptance coverage for backup/source-leak style web CTF chains."""

from __future__ import annotations

import io
import threading
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

import pentestagent.tools.notes as notes_module
from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from pentestagent.runtime.runtime import LocalRuntime
from pentestagent.tools.notes import get_all_notes_sync, set_notes_file


FLAG_VALUE = "Syc{backup_source_leak_ok}"


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
def backup_php_server():
    recorded: list[dict] = []
    archive_bytes = _build_backup_zip()

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
                    """
                    <html><body>
                      <h1>I have a cat!</h1>
                      <p>因为每次猫猫都在我键盘上乱跳，所以我有一个良好的备份网站的习惯</p>
                      <script src="index.js"></script>
                    </body></html>
                    """.encode("utf-8")
                )
                return

            if parsed.path == "/www.zip":
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(len(archive_bytes)))
                self.end_headers()
                self.wfile.write(archive_bytes)
                return

            if parsed.path == "/robots.txt":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"User-agent: *\nDisallow:\n")
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


def _build_backup_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "index.php",
            "<?php include 'class.php'; $select=$_GET['select']; $res=unserialize(@$select); ?>",
        )
        zf.writestr(
            "class.php",
            (
                "<?php include 'flag.php'; "
                "class Name { function __destruct(){ global $flag; echo $flag; } } ?>"
            ),
        )
        zf.writestr("flag.php", f"<?php $flag = '{FLAG_VALUE}'; ?>")
    return buf.getvalue()


def _playwright_missing_error() -> dict[str, str]:
    return {
        "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
    }


@pytest.mark.asyncio
async def test_ctf_dispatcher_acceptance_does_not_stop_on_source_only_backup_flag(
    tmp_path: Path, monkeypatch, isolated_notes, backup_php_server
):
    monkeypatch.chdir(tmp_path)

    runtime = LocalRuntime()
    await runtime.start()
    try:
        async def _browser_missing(action: str, **kwargs):
            return _playwright_missing_error()

        monkeypatch.setattr(runtime, "browser_action", _browser_missing)

        dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)
        result = await dispatcher.run(
            target=backup_php_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        assert result.success is False
        assert result.flag is None
        assert result.chain_used == ["web"]
        assert "source-only candidate flag" in result.reason

        requests = backup_php_server["requests"]
        assert requests[0]["path"] == "/"
        assert any(entry["path"] == "/www.zip" for entry in requests)

        notes = get_all_notes_sync()
        assert "ctf_backup_candidate" in notes
        assert "ctf_backup_analysis" in notes
        assert "ctf_flag_candidate" in notes
        assert FLAG_VALUE in notes["ctf_flag_candidate"]["content"]
    finally:
        await runtime.stop()
