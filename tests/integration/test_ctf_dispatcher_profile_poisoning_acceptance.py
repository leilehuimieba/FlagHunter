from __future__ import annotations

import base64
import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.runtime import LocalRuntime
from flaghunter.tools.notes import set_notes_file


FLAG_VALUE = "flag{profile_photo_poisoning_ok}"


def _build_source_zip() -> bytes:
    files = {
        "www/profile.php": """<?php
$profile = unserialize($profile);
$photo = base64_encode(file_get_contents($profile['photo']));
?>""",
        "www/update.php": """<?php
$profile['phone'] = $_POST['phone'];
$profile['email'] = $_POST['email'];
$profile['nickname'] = $_POST['nickname'];
$profile['photo'] = 'upload/' . md5($file['name']);
$user->update_profile($username, serialize($profile));
?>""",
        "www/class.php": """<?php
class mysql {
    public function filter($string) {
        $escape = array('\\'', '\\\\');
        $escape = '/' . implode('|', $escape) . '/';
        $string = preg_replace($escape, '_', $string);
        $safe = array('select', 'insert', 'update', 'delete', 'where');
        $safe = '/' . implode('|', $safe) . '/i';
        return preg_replace($safe, 'hacker', $string);
    }
}
?>""",
    }
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return mem.getvalue()


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
def profile_poisoning_server():
    source_zip = _build_source_zip()
    state = {
        "users": {},
        "sessions": {},
        "poisoned": False,
        "requests": [],
    }

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            pass

        def _cookie_sid(self) -> str:
            cookie = self.headers.get("Cookie", "")
            for chunk in cookie.split(";"):
                chunk = chunk.strip()
                if chunk.startswith("sid="):
                    return chunk.split("=", 1)[1]
            return ""

        def do_GET(self):  # noqa: N802
            state["requests"].append(("GET", self.path, dict(self.headers)))
            if self.path in {"/", "/index.php"}:
                body = """
                <html><body>
                  <form action="/index.php" method="post">
                    <input name="username" />
                    <input name="password" />
                  </form>
                  <a href="/register.php">register</a>
                </body></html>
                """.encode("utf-8")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path == "/profile.php":
                sid = self._cookie_sid()
                if sid not in state["sessions"]:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Login First")
                    return
                if state["poisoned"]:
                    config_blob = f"<?php $flag='{FLAG_VALUE}'; ?>".encode("utf-8")
                else:
                    config_blob = b"HELLOPIA"
                encoded = base64.b64encode(config_blob).decode("ascii")
                html = (
                    "<html><body>"
                    f"<img src=\"data:image/gif;base64,{encoded}\">"
                    "</body></html>"
                ).encode("utf-8")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(html)
                return

            if self.path == "/www.zip":
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.end_headers()
                self.wfile.write(source_zip)
                return

            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            state["requests"].append(
                ("POST", self.path, dict(self.headers), raw.decode("latin-1", errors="ignore"))
            )

            if self.path == "/register.php":
                fields = parse_qs(raw.decode("utf-8"))
                username = (fields.get("username") or [""])[0]
                password = (fields.get("password") or [""])[0]
                state["users"][username] = password
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Register OK!<a href=\"index.php\">Please Login</a>")
                return

            if self.path == "/index.php":
                fields = parse_qs(raw.decode("utf-8"))
                username = (fields.get("username") or [""])[0]
                password = (fields.get("password") or [""])[0]
                if state["users"].get(username) == password:
                    sid = f"sid-{username}"
                    state["sessions"][sid] = username
                    self.send_response(200)
                    self.send_header("Set-Cookie", f"sid={sid}; Path=/")
                    self.end_headers()
                    self.wfile.write(b"login ok")
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Invalid user name or password")
                return

            if self.path == "/update.php":
                sid = self._cookie_sid()
                if sid not in state["sessions"]:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Login First")
                    return
                body = raw.decode("latin-1", errors="ignore")
                if (
                    "name=\"nickname[]\"" in body
                    and "config.php" in body
                    and "wherewherewhere" in body
                ):
                    state["poisoned"] = True
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Update Profile Success!<a href=\"profile.php\">Your Profile</a>")
                return

            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {
        "base_url": f"http://127.0.0.1:{server.server_port}",
        "state": state,
    }
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


@pytest.mark.asyncio
async def test_ctf_dispatcher_acceptance_solves_profile_photo_poisoning_chain(
    tmp_path: Path,
    monkeypatch,
    isolated_notes,
    profile_poisoning_server,
):
    monkeypatch.chdir(tmp_path)

    runtime = LocalRuntime()
    await runtime.start()
    try:
        dispatcher = CTFTaskDispatcher(
            runtime=runtime,
            progress_callback=None,
            verification_callback=lambda flag: "yes",
        )

        result = await dispatcher.run(
            target=profile_poisoning_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        assert result.success is True
        assert result.flag == FLAG_VALUE
        assert "web" in result.chain_used
        assert profile_poisoning_server["state"]["poisoned"] is True
    finally:
        await runtime.stop()
