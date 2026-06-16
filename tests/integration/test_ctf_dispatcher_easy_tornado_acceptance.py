"""Acceptance coverage for easy_tornado-style hint -> render SSTI -> hash reconstruction chains."""

from __future__ import annotations

import hashlib
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


FLAG_VALUE = "flag{easy_tornado_acceptance_ok}"
COOKIE_SECRET = "f8c6ad0b-c3f2-42b8-b0dc-3e6d3d3c8a25"
REAL_FLAG_PATH = "/fllllllllllllag"


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


def _calc_filehash(filename: str) -> str:
    inner = hashlib.md5(filename.encode()).hexdigest()
    return hashlib.md5((COOKIE_SECRET + inner).encode()).hexdigest()


def _calc_filehash_sha256(filename: str) -> str:
    inner = hashlib.sha256(filename.encode()).hexdigest()
    return hashlib.sha256((COOKIE_SECRET + inner).encode()).hexdigest()


@pytest.fixture
def easy_tornado_server():
    recorded: list[dict] = []
    linked_files = {
        "/flag.txt": "flag in /fllllllllllllag",
        "/welcome.txt": "render",
        "/hints.txt": "md5(cookie_secret+md5(filename))",
        REAL_FLAG_PATH: FLAG_VALUE,
    }

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
                        "<h1>easy_tornado</h1>"
                        f"<a href='/file?filename=/flag.txt&filehash={_calc_filehash('/flag.txt')}'>/flag.txt</a>"
                        f"<a href='/file?filename=/welcome.txt&filehash={_calc_filehash('/welcome.txt')}'>/welcome.txt</a>"
                        f"<a href='/file?filename=/hints.txt&filehash={_calc_filehash('/hints.txt')}'>/hints.txt</a>"
                        "</body></html>"
                    ).encode("utf-8")
                )
                return

            if parsed.path == "/file":
                params = parse_qs(parsed.query)
                filename = params.get("filename", [""])[0]
                provided_hash = params.get("filehash", [""])[0]
                expected_hash = _calc_filehash(filename) if filename else ""
                if filename in linked_files and provided_hash == expected_hash:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(f"{filename}<br>{linked_files[filename]}".encode("utf-8"))
                    return

                self.send_response(302)
                self.send_header("Location", "/error?msg=Error")
                self.end_headers()
                return

            if parsed.path == "/error":
                params = parse_qs(parsed.query)
                msg = params.get("msg", ["Error"])[0]
                rendered = msg
                if msg == "{{7*7}}":
                    rendered = "49"
                elif msg == "{{handler.settings}}":
                    rendered = str({"cookie_secret": COOKIE_SECRET})
                elif msg in {
                    '{{handler.settings["cookie_secret"]}}',
                    '{{handler.settings.get("cookie_secret","")}}',
                }:
                    rendered = COOKIE_SECRET
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


@pytest.fixture
def easy_tornado_realistic_server():
    recorded: list[dict] = []
    linked_files = {
        "/flag.txt": "flag in /fllllllllllllag",
        "/welcome.txt": "render",
        "/hints.txt": "md5(cookie_secret+md5(filename))",
        REAL_FLAG_PATH: FLAG_VALUE,
    }

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
                        "<h1>easy_tornado</h1>"
                        f"<a href='/file?filename=/flag.txt&filehash={_calc_filehash('/flag.txt')}'>/flag.txt</a>"
                        f"<a href='/file?filename=/welcome.txt&filehash={_calc_filehash('/welcome.txt')}'>/welcome.txt</a>"
                        f"<a href='/file?filename=/hints.txt&filehash={_calc_filehash('/hints.txt')}'>/hints.txt</a>"
                        "</body></html>"
                    ).encode("utf-8")
                )
                return

            if parsed.path == "/file":
                params = parse_qs(parsed.query)
                filename = params.get("filename", [""])[0]
                provided_hash = params.get("filehash", [""])[0]
                expected_hash = _calc_filehash(filename) if filename else ""
                if filename in linked_files and provided_hash == expected_hash:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(f"{filename}<br>{linked_files[filename]}".encode("utf-8"))
                    return

                self.send_response(302)
                self.send_header("Location", "/error?msg=Error")
                self.end_headers()
                return

            if parsed.path == "/error":
                params = parse_qs(parsed.query)
                msg = params.get("msg", ["Error"])[0]
                if msg == "{{7*7}}":
                    rendered = "ORZ"
                elif msg == "{{handler.settings}}":
                    rendered = str(
                        {
                            "autoreload": True,
                            "compiled_template_cache": False,
                            "cookie_secret": COOKIE_SECRET,
                        }
                    )
                elif msg in {
                    '{{handler.settings["cookie_secret"]}}',
                    '{{handler.settings.get("cookie_secret","")}}',
                }:
                    rendered = "ORZ"
                else:
                    rendered = msg
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    (
                        "<html>\n<head>\n<style>body{font-size: 30px;}</style>\n</head>\n"
                        f"<body>{rendered}</body>\n</html>\n"
                    ).encode("utf-8")
                )
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


@pytest.fixture
def easy_tornado_sha256_server():
    recorded: list[dict] = []
    linked_files = {
        "/flag.txt": "flag in /sha256_flag",
        "/welcome.txt": "render",
        "/hints.txt": "sha256(cookie_secret+sha256(filename))",
        "/sha256_flag": FLAG_VALUE,
    }

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
                        "<h1>easy_tornado_sha256</h1>"
                        f"<a href='/file?filename=/flag.txt&filehash={_calc_filehash_sha256('/flag.txt')}'>/flag.txt</a>"
                        f"<a href='/file?filename=/welcome.txt&filehash={_calc_filehash_sha256('/welcome.txt')}'>/welcome.txt</a>"
                        f"<a href='/file?filename=/hints.txt&filehash={_calc_filehash_sha256('/hints.txt')}'>/hints.txt</a>"
                        "</body></html>"
                    ).encode("utf-8")
                )
                return

            if parsed.path == "/file":
                params = parse_qs(parsed.query)
                filename = params.get("filename", [""])[0]
                provided_hash = params.get("filehash", [""])[0]
                expected_hash = _calc_filehash_sha256(filename) if filename else ""
                if filename in linked_files and provided_hash == expected_hash:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(f"{filename}<br>{linked_files[filename]}".encode("utf-8"))
                    return

                self.send_response(302)
                self.send_header("Location", "/error?msg=Error")
                self.end_headers()
                return

            if parsed.path == "/error":
                params = parse_qs(parsed.query)
                msg = params.get("msg", ["Error"])[0]
                rendered = msg
                if msg == "{{7*7}}":
                    rendered = "49"
                elif msg == "{{handler.settings}}":
                    rendered = str({"cookie_secret": COOKIE_SECRET})
                elif msg in {
                    '{{handler.settings["cookie_secret"]}}',
                    '{{handler.settings.get("cookie_secret","")}}',
                }:
                    rendered = COOKIE_SECRET
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
async def test_ctf_dispatcher_acceptance_solves_easy_tornado_chain(
    tmp_path: Path, monkeypatch, isolated_notes, easy_tornado_server
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
            exploitation_mode="conservative",
        )
        result = await dispatcher.run(
            target=easy_tornado_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        assert result.success is True
        assert result.flag == FLAG_VALUE
        assert result.chain_used == ["web"]

        observed_kinds = {item.kind for item in dispatcher.state.observations}
        assert "file_read_response" in observed_kinds
        assert "file_read_redirect" in observed_kinds
        assert "render_ssti_response" in observed_kinds
        assert "cookie_secret_leaked" in observed_kinds
        assert "hash_reconstruction_response" in observed_kinds
        assert any(item.value == FLAG_VALUE for item in dispatcher.state.verified_flags)

        requests = easy_tornado_server["requests"]
        assert requests[0]["path"] == "/"
        assert any(
            entry["path"] == "/file"
            and parse_qs(entry["query"]).get("filename", [""])[0] == "/flag.txt"
            for entry in requests
        )
        assert any(
            entry["path"] == "/error"
            and parse_qs(entry["query"]).get("msg", [""])[0]
            in {"{{handler.settings}}", '{{handler.settings["cookie_secret"]}}'}
            for entry in requests
        )
        assert any(
            entry["path"] == "/file"
            and parse_qs(entry["query"]).get("filename", [""])[0] == REAL_FLAG_PATH
            for entry in requests
        )
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_ctf_dispatcher_acceptance_skips_identify_when_ssti_probe_has_no_hit(
    tmp_path: Path, monkeypatch, isolated_notes, easy_tornado_realistic_server
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
            exploitation_mode="conservative",
        )
        result = await dispatcher.run(
            target=easy_tornado_realistic_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        assert result.success is False
        assert result.flag is None
        assert dispatcher.state is not None
        assert not any(
            obs.kind == "ssti_probe_hit"
            for obs in dispatcher.state.observations
        )
        assert not any(
            obs.kind == "ssti_identify_attempted"
            for obs in dispatcher.state.observations
        )
        requests = easy_tornado_realistic_server["requests"]
        attempted_probe_payloads = {
            parse_qs(entry["query"]).get("msg", [""])[0]
            for entry in requests
            if entry["path"] == "/error"
        }
        assert "{{7*7}}" in attempted_probe_payloads
        assert "{{handler.settings}}" not in attempted_probe_payloads
        assert '{{handler.settings["cookie_secret"]}}' not in attempted_probe_payloads
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_ctf_dispatcher_acceptance_solves_sha256_hash_reconstruction_chain(
    tmp_path: Path, monkeypatch, isolated_notes, easy_tornado_sha256_server
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
            target=easy_tornado_sha256_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        assert result.success is True
        assert result.flag == FLAG_VALUE
        assert dispatcher.state is not None
        assert any(
            obs.kind == "hash_reconstruction_response"
            and (obs.metadata or {}).get("hash_format") == "sha256"
            for obs in dispatcher.state.observations
        )
        assert any(
            entry["path"] == "/file"
            and parse_qs(entry["query"]).get("filename", [""])[0] == "/sha256_flag"
            for entry in easy_tornado_sha256_server["requests"]
        )
    finally:
        await runtime.stop()
