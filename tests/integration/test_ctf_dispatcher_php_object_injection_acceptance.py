"""Acceptance coverage for source-leak -> PHP object injection escalation."""

from __future__ import annotations

import io
import threading
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

import pentestagent.tools.notes as notes_module
from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from pentestagent.runtime.runtime import LocalRuntime
from pentestagent.tools.notes import get_all_notes_sync, set_notes_file


DECOY_FLAG = "Syc{dog_dog_dog_dog}"
RUNTIME_FLAG = "flag{php_object_injection_runtime_ok}"


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
def php_object_injection_server():
    recorded: list[dict] = []
    archive_bytes = _build_php_source_zip()

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
                    "params": params,
                    "headers": dict(self.headers),
                }
            )

            if parsed.path == "/":
                if "select" in params:
                    payload = params["select"][0]
                    if (
                        'O:4:"Name":3:' in payload or 'O:4:"Name":4:' in payload
                    ) and "admin" in payload and "i:100" in payload:
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(
                            f"<html><body>{RUNTIME_FLAG}</body></html>".encode("utf-8")
                        )
                        return

                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(
                        b"<html><body></br>hello my friend~~</br>sorry i can't give you the flag!</body></html>"
                    )
                    return

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


def _build_php_source_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "index.php",
            (
                "<html><body><?php include 'class.php'; "
                "$select = $_GET['select']; $res=unserialize(@$select); ?></body></html>"
            ),
        )
        zf.writestr(
            "class.php",
            (
                "<?php include 'flag.php'; error_reporting(0); "
                "class Name{"
                "private $username='nonono';"
                "private $password='yesyes';"
                "function __wakeup(){ $this->username='guest'; }"
                "function __destruct(){"
                "if ($this->password != 100) { die(); }"
                "if ($this->username === 'admin') { global $flag; echo $flag; }"
                "else { die(); }"
                "}"
                "}"
                "?>"
            ),
        )
        zf.writestr("flag.php", f"<?php $flag = '{DECOY_FLAG}'; ?>")
    return buf.getvalue()


def _playwright_missing_error() -> dict[str, str]:
    return {
        "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
    }


@pytest.mark.asyncio
async def test_ctf_dispatcher_acceptance_escalates_past_source_flag_to_runtime_flag(
    tmp_path: Path, monkeypatch, isolated_notes, php_object_injection_server
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
            target=php_object_injection_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        assert result.success is True
        assert result.flag == RUNTIME_FLAG
        assert result.chain_used == ["web"]
        assert "php unserialize runtime exploit" in result.reason
        assert dispatcher.state is not None
        assert any(
            record.value == DECOY_FLAG for record in dispatcher.state.candidate_flags
        )
        assert any(
            record.value == RUNTIME_FLAG for record in dispatcher.state.verified_flags
        )

        notes = get_all_notes_sync()
        assert "ctf_flag_candidate" in notes
        assert DECOY_FLAG in notes["ctf_flag_candidate"]["content"]
        assert "ctf_php_unserialize_exploit" in notes
        assert "ctf_flag" in notes
        assert RUNTIME_FLAG in notes["ctf_flag"]["content"]

        requests = php_object_injection_server["requests"]
        assert any(entry["path"] == "/www.zip" for entry in requests)
        assert any(
            entry["path"] == "/"
            and "select" in entry["params"]
            and ("O:4:\"Name\":3:" in entry["params"]["select"][0] or "O:4:\"Name\":4:" in entry["params"]["select"][0])
            for entry in requests
        )
    finally:
        await runtime.stop()
