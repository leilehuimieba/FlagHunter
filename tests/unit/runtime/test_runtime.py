"""Tests for pentestagent.runtime.runtime (CommandResult, detect_environment, LocalRuntime)."""

import asyncio
import base64
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
import pytest

from pentestagent.runtime.runtime import (
    CommandResult,
    EnvironmentInfo,
    LocalRuntime,
    ToolInfo,
    _normalize_httpx_files,
    _snapshot_httpx_cookies,
    _build_loopback_url_candidates,
    detect_environment,
)


# ---------------------------------------------------------------------------
# CommandResult
# ---------------------------------------------------------------------------

class TestCommandResult:
    def test_success_on_zero_exit_code(self):
        r = CommandResult(exit_code=0, stdout="ok", stderr="")
        assert r.success is True

    def test_failure_on_nonzero_exit_code(self):
        r = CommandResult(exit_code=1, stdout="", stderr="error")
        assert r.success is False

    def test_output_combines_stdout_and_stderr(self):
        r = CommandResult(exit_code=0, stdout="OUT", stderr="ERR")
        assert "OUT" in r.output
        assert "ERR" in r.output

    def test_output_only_stdout(self):
        r = CommandResult(exit_code=0, stdout="OUT", stderr="")
        assert r.output == "OUT"

    def test_output_only_stderr(self):
        r = CommandResult(exit_code=0, stdout="", stderr="ERR")
        assert r.output == "ERR"

    def test_output_empty_when_both_empty(self):
        r = CommandResult(exit_code=0, stdout="", stderr="")
        assert r.output == ""

    def test_negative_exit_code_is_failure(self):
        r = CommandResult(exit_code=-1, stdout="", stderr="timeout")
        assert r.success is False


# ---------------------------------------------------------------------------
# EnvironmentInfo
# ---------------------------------------------------------------------------

class TestEnvironmentInfo:
    def _make_env(self, tools=None):
        return EnvironmentInfo(
            os="Linux",
            os_version="5.15",
            shell="bash",
            architecture="x86_64",
            available_tools=tools or [],
        )

    def test_str_contains_os(self):
        env = self._make_env()
        assert "Linux" in str(env)

    def test_str_contains_shell(self):
        env = self._make_env()
        assert "bash" in str(env)

    def test_str_no_tools_shows_none(self):
        env = self._make_env(tools=[])
        assert "None" in str(env)

    def test_str_groups_tools_by_category(self):
        tools = [
            ToolInfo(name="nmap", path="/usr/bin/nmap", category="network_scan"),
            ToolInfo(name="curl", path="/usr/bin/curl", category="utilities"),
        ]
        env = self._make_env(tools=tools)
        s = str(env)
        assert "nmap" in s
        assert "curl" in s
        assert "network_scan" in s
        assert "utilities" in s


# ---------------------------------------------------------------------------
# detect_environment
# ---------------------------------------------------------------------------

class TestDetectEnvironment:
    def test_returns_environment_info(self):
        env = detect_environment()
        assert isinstance(env, EnvironmentInfo)

    def test_os_is_non_empty_string(self):
        env = detect_environment()
        assert isinstance(env.os, str)
        assert len(env.os) > 0

    def test_shell_is_non_empty_string(self):
        env = detect_environment()
        assert isinstance(env.shell, str)
        assert len(env.shell) > 0

    def test_available_tools_is_list(self):
        env = detect_environment()
        assert isinstance(env.available_tools, list)

    def test_tool_info_fields(self):
        env = detect_environment()
        for tool in env.available_tools:
            assert isinstance(tool.name, str)
            assert isinstance(tool.path, str)
            assert isinstance(tool.category, str)


# ---------------------------------------------------------------------------
# LocalRuntime — basic lifecycle
# ---------------------------------------------------------------------------

class TestLocalRuntimeLifecycle:
    @pytest.mark.asyncio
    async def test_start_sets_running(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runtime = LocalRuntime()
        await runtime.start()
        assert await runtime.is_running() is True
        await runtime.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runtime = LocalRuntime()
        await runtime.start()
        await runtime.stop()
        assert await runtime.is_running() is False

    @pytest.mark.asyncio
    async def test_get_status_returns_dict(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runtime = LocalRuntime()
        await runtime.start()
        status = await runtime.get_status()
        assert isinstance(status, dict)
        assert status["type"] == "local"
        assert status["running"] is True
        await runtime.stop()

    @pytest.mark.asyncio
    async def test_status_after_stop(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runtime = LocalRuntime()
        await runtime.start()
        await runtime.stop()
        status = await runtime.get_status()
        assert status["running"] is False


# ---------------------------------------------------------------------------
# LocalRuntime — execute_command
# ---------------------------------------------------------------------------

class TestLocalRuntimeExecuteCommand:
    @pytest.mark.asyncio
    async def test_echo_command(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runtime = LocalRuntime()
        await runtime.start()
        result = await runtime.execute_command("echo hello")
        assert result.success is True
        assert "hello" in result.stdout
        await runtime.stop()

    @pytest.mark.asyncio
    async def test_exit_code_propagated(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runtime = LocalRuntime()
        await runtime.start()
        result = await runtime.execute_command("exit 42", timeout=5)
        assert result.exit_code == 42
        await runtime.stop()

    @pytest.mark.asyncio
    async def test_stderr_captured(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runtime = LocalRuntime()
        await runtime.start()
        result = await runtime.execute_command("echo error >&2")
        assert "error" in result.stderr or "error" in result.stdout
        await runtime.stop()

    @pytest.mark.asyncio
    async def test_timeout_returns_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runtime = LocalRuntime()
        await runtime.start()
        result = await runtime.execute_command("sleep 60", timeout=1)
        assert result.exit_code != 0
        assert "timed out" in result.stderr.lower()
        await runtime.stop()

    @pytest.mark.asyncio
    async def test_command_result_type(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runtime = LocalRuntime()
        await runtime.start()
        result = await runtime.execute_command("echo test")
        assert isinstance(result, CommandResult)
        await runtime.stop()

    @pytest.mark.asyncio
    async def test_ansi_codes_stripped(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runtime = LocalRuntime()
        await runtime.start()
        result = await runtime.execute_command(r"printf '\033[1;32mGREEN\033[0m'")
        assert "\033[" not in result.stdout
        await runtime.stop()


class TestLoopbackUrlFallbackHelpers:
    def test_localhost_candidates_include_loopback_alias(self):
        candidates = _build_loopback_url_candidates("http://localhost:3000/demo")
        assert candidates[0] == "http://localhost:3000/demo"
        assert "http://127.0.0.1:3000/demo" in candidates

    def test_non_loopback_url_unchanged(self):
        url = "http://example.com:8080/demo"
        assert _build_loopback_url_candidates(url) == [url]


class TestRuntimeMultipartHelpers:
    def test_normalize_httpx_files_supports_inline_content(self):
        normalized = _normalize_httpx_files(
            {
                "photo": {
                    "filename": "avatar.txt",
                    "content": "hello-world",
                    "content_type": "text/plain",
                }
            }
        )

        assert normalized is not None
        assert "photo" in normalized
        filename, content, content_type = normalized["photo"]
        assert filename == "avatar.txt"
        assert content == b"hello-world"
        assert content_type == "text/plain"

    def test_normalize_httpx_files_supports_path_input(self, tmp_path):
        file_path = tmp_path / "avatar.txt"
        file_path.write_text("hello-path", encoding="utf-8")

        normalized = _normalize_httpx_files({"photo": {"path": str(file_path)}})

        assert normalized is not None
        assert normalized["photo"] == ("avatar.txt", b"hello-path")

    def test_snapshot_httpx_cookies_tolerates_duplicate_names(self):
        class _Cookie:
            def __init__(self, name, value):
                self.name = name
                self.value = value

        class _Cookies:
            def __init__(self):
                self.jar = [
                    _Cookie("csrftoken", "first"),
                    _Cookie("sessionid", "sess"),
                    _Cookie("csrftoken", "second"),
                ]

        snapshot = _snapshot_httpx_cookies(_Cookies())

        assert snapshot["sessionid"] == "sess"
        assert snapshot["csrftoken"] == "second"


class TestLocalRuntimeBrowserFallback:
    @pytest.mark.asyncio
    async def test_launch_browser_falls_back_to_system_executable(self, monkeypatch):
        runtime = LocalRuntime()

        class _FakeChromium:
            def __init__(self):
                self.calls = []

            async def launch(self, **kwargs):
                self.calls.append(dict(kwargs))
                if "executable_path" not in kwargs:
                    raise RuntimeError("Executable doesn't exist")
                return "fake-browser"

        fake_chromium = _FakeChromium()
        runtime._playwright = SimpleNamespace(chromium=fake_chromium)
        monkeypatch.setattr(
            LocalRuntime,
            "_candidate_browser_executables",
            staticmethod(
                lambda: [r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
            ),
        )

        browser = await runtime._launch_browser_with_fallbacks()

        assert browser == "fake-browser"
        assert runtime._browser_launch_source.startswith("system:")
        assert len(fake_chromium.calls) == 2
        assert "executable_path" in fake_chromium.calls[1]

    @pytest.mark.asyncio
    async def test_browser_diagnose_reports_launch_source(self, monkeypatch):
        runtime = LocalRuntime()

        async def _fake_ensure():
            runtime._page = object()
            runtime._browser_launch_source = "system:test-chrome"

        monkeypatch.setattr(runtime, "_ensure_browser", _fake_ensure)
        probe = await runtime._diagnose_browser()

        assert probe["available"] is True
        assert probe["launch_source"] == "system:test-chrome"


class TestLocalRuntimeProxyBinary:
    @pytest.mark.asyncio
    async def test_proxy_action_binary_returns_base64_body(self):
        payload = b"\x89PNG\r\n\x1a\nfakepng"

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):  # noqa: A003
                pass

            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        runtime = LocalRuntime()
        await runtime.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/img.png"
            result = await runtime.proxy_action("get", url=url, binary=True, timeout=10)

            assert result["status_code"] == 200
            assert result["content_type"].startswith("image/png")
            assert base64.b64decode(result["body_base64"]) == payload
            assert "body" not in result
        finally:
            await runtime.stop()
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    @pytest.mark.asyncio
    async def test_proxy_action_ignores_environment_proxy_for_loopback(self, monkeypatch):
        payload = b"ok-loopback"

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):  # noqa: A003
                pass

            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
        monkeypatch.setenv("https_proxy", "http://127.0.0.1:9")

        runtime = LocalRuntime()
        await runtime.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/hello.txt"
            result = await runtime.proxy_action("get", url=url, timeout=10)

            assert result["status_code"] == 200
            assert result["body"] == payload.decode("utf-8")
            assert result["final_url"] == url
        finally:
            await runtime.stop()
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


# ---------------------------------------------------------------------------
# SSHRuntime.proxy_action HTTP fetch (curl-on-Kali, mirrors LocalRuntime "get")
# ---------------------------------------------------------------------------
class TestSSHRuntimeProxyHttpFetch:
    @pytest.mark.asyncio
    async def test_get_parses_status_headers_body_and_set_cookie(self, monkeypatch):
        from pentestagent.runtime.ssh_runtime import SSHRuntime

        rt = SSHRuntime.__new__(SSHRuntime)
        rt._proxy_port = 8888
        sep = "__PA_SEP_9b1c4f__"
        # curl: <http_code>\n<sep>\n<headers>\n<sep>\n<body>
        headers = (
            "HTTP/1.1 200 OK\r\n"
            "Server: openresty\r\n"
            "Set-Cookie: XSRF-TOKEN=abc; path=/\r\n"
            "Set-Cookie: laravel_session=def; httponly\r\n"
            "X-Powered-By: PHP/5.6.40\r\n"
        )
        body = "<html><a href='/login'>Login</a></html>"
        stdout = f"200\n{sep}\n{headers}{sep}\n{body}"

        async def fake_exec(cmd, timeout=0):
            assert "curl" in cmd
            return CommandResult(exit_code=0, stdout=stdout, stderr="")

        monkeypatch.setattr(rt, "execute_command", fake_exec)
        res = await rt.proxy_action("get", url="http://t.local:80/", timeout=10)

        assert res["status_code"] == 200
        assert res["body"] == body
        assert "laravel_session=def" in res["headers"]["set-cookie"]
        assert "xsrf-token=abc" in res["headers"]["set-cookie"].lower()
        assert res["headers"]["x-powered-by"] == "PHP/5.6.40"

    @pytest.mark.asyncio
    async def test_missing_url_errors(self):
        from pentestagent.runtime.ssh_runtime import SSHRuntime

        rt = SSHRuntime.__new__(SSHRuntime)
        rt._proxy_port = 8888
        res = await rt.proxy_action("get")
        assert "error" in res
