"""Acceptance coverage for attachment-first misc/forensics CTF chains."""

from __future__ import annotations

import io
import threading
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.harness.artifact_registry import ArtifactRegistry
from flaghunter.runtime.runtime import LocalRuntime
from flaghunter.tools.notes import set_notes_file


FLAG_VALUE = "flag{misc_artifact_forensics_ok}"


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
def misc_artifact_server():
    recorded: list[dict] = []
    archive_bytes = _build_misc_artifact_zip()

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
                      <h1>Directory listing</h1>
                      <p>attachments: challenge.zip</p>
                      <a href="/challenge.zip">challenge.zip</a>
                    </body></html>
                    """
                )
                return

            if parsed.path == "/challenge.zip":
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


def _build_misc_artifact_zip() -> bytes:
    fragments = [
        "ZmxhZ3ttaXNj",
        "X2FydGlmYWN0",
        "X2ZvcmVuc2lj",
        "c19va30=",
    ]
    wal_text = "\n".join(
        f"2024-04-01 10:01:{idx:02d} sync-bot part:{idx+1:02d}:[{blob}]"
        for idx, blob in enumerate(fragments)
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("app.db", b"SQLite format 3\x00")
        zf.writestr("app.db-wal", wal_text.encode("utf-8"))
        zf.writestr("README.txt", b"recover me from wal fragments")
    return buf.getvalue()


def _playwright_missing_error() -> dict[str, str]:
    return {
        "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
    }


@pytest.mark.asyncio
async def test_ctf_dispatcher_acceptance_misc_attachment_artifact_forensics(
    tmp_path: Path, monkeypatch, isolated_notes, misc_artifact_server
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
            target=misc_artifact_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        assert result.success is True
        assert result.flag == FLAG_VALUE
        assert "misc" in result.chain_used
        assert dispatcher.state is not None
        assert dispatcher.state.detected_type == "misc"
        assert any(item.value == FLAG_VALUE for item in dispatcher.state.verified_flags)
        assert any(entry["path"] == "/challenge.zip" for entry in misc_artifact_server["requests"])
        records = ArtifactRegistry(tmp_path / "loot" / "artifact_registry").list_artifacts(
            dispatcher._artifact_run_id
        )
        forensics_record = next(
            record for record in records if record["title"] == "ctf_artifact_forensics"
        )
        assert forensics_record["producer"] == "artifact_forensics"
        assert forensics_record["metadata"]["category"] == "artifact_forensics_summary"
        assert forensics_record["metadata"]["note_category"] == "artifact"
    finally:
        await runtime.stop()
