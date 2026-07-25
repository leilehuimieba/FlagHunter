"""Acceptance coverage for path-segment SSTI (shrine class).

Guards the reachability fix: SSTI whose injection point lives in the URL path
(Flask ``/<route>/<path>``) rather than a query parameter, on a target that
also shadows ``config`` / ``self`` (as shrine does). Before the fix the probe
only injected into query params, never reached the path point, failed to record
``ssti_probe_hit``, and the agent spun through unrelated chains. This models a
route (``/temple/``) that is NOT in the common-route seed list, so the test
exercises the *discovered-link* path derivation, not a hardcoded guess.
"""

from __future__ import annotations

import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.runtime.runtime import LocalRuntime
from flaghunter.tools.notes import set_notes_file


FLAG_VALUE = "flag{shrine_path_ssti_ok}"
_ROUTE = "/shrine/"

# Faithful to the real shrine challenge: the index leaks the Flask source, which
# (a) advertises the template stack so SSTI is judged worth attempting and
# (b) reveals the injectable /shrine/<path> route.
_INDEX_SOURCE = (
    "<html><body><pre>"
    "from flask import Flask, render_template_string\n"
    "app = Flask(__name__)\n"
    "@app.route('/shrine/&lt;path:shrine&gt;')\n"
    "def shrine(shrine):\n"
    "    return render_template_string(safe_jinja(shrine))\n"
    "</pre><a href='/shrine/'>enter the shrine</a></body></html>"
)


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
def path_ssti_server():
    recorded: list[dict] = []

    def _render(payload: str) -> str:
        # Emulate shrine: strip parens, then shadow bare ``config``/``self``.
        stripped = payload.replace("(", "").replace(")", "")
        if stripped == "{{7*7}}":
            return "49"
        if stripped == "{{7*'7'}}":
            return "7777777"
        if stripped in {"{{config}}", "{{self._TemplateReference__context.config}}"}:
            # bare config/self are set to None -> no useful output
            return "None"
        if "url_for.__globals__" in stripped or "get_flashed_messages.__globals__" in stripped:
            if "['FLAG']" in stripped:
                return FLAG_VALUE
            return (
                "<Config {'SECRET_KEY': 'dev', 'DEBUG': False, "
                f"'FLAG': '{FLAG_VALUE}'}}>"
            )
        return stripped  # literal reflection for anything else

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            pass

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            recorded.append({"method": "GET", "path": parsed.path, "query": parsed.query})

            if parsed.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_INDEX_SOURCE.encode("utf-8"))
                return

            decoded_path = unquote(parsed.path)
            if decoded_path.startswith(_ROUTE) and len(decoded_path) > len(_ROUTE):
                payload = decoded_path[len(_ROUTE):]
                rendered = _render(payload)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<html><body>{rendered}</body></html>".encode("utf-8"))
                return

            # Every query surface (e.g. /error?msg=...) 404s: the only reachable
            # injection point is the path segment.
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
async def test_ctf_dispatcher_acceptance_solves_path_segment_ssti(
    tmp_path: Path, monkeypatch, isolated_notes, path_ssti_server
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
            target=path_ssti_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        assert result.success is True
        assert result.flag == FLAG_VALUE
        assert dispatcher.state is not None
        assert any(
            obs.kind == "ssti_engine_identified" and obs.value == "jinja2"
            for obs in dispatcher.state.observations
        )

        requests = path_ssti_server["requests"]
        # The {{7*7}} probe must have reached the PATH segment (not a query param).
        assert any(
            entry["path"].startswith(_ROUTE) and "7" in unquote(entry["path"])
            for entry in requests
        ), "no path-segment probe reached the injectable route"
        # The winning exploit went through a globals-based bypass on the path.
        assert any(
            entry["path"].startswith(_ROUTE)
            and "__globals__" in unquote(entry["path"])
            for entry in requests
        ), "no globals-based bypass payload reached the path"
    finally:
        await runtime.stop()
