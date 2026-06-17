from __future__ import annotations

from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher


pytestmark = pytest.mark.integration


class _CommandResult:
    def __init__(self, exit_code: int, stdout: str = "", stderr: str = ""):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class _DockerLoopbackFallbackRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.browser_calls: list[tuple[str, dict]] = []
        self.proxy_calls: list[tuple[str, dict]] = []
        self.commands: list[str] = []
        self.internal_probe_started = False
        self.internal_probe_visited = False
        self.admin_sid_used: str | None = None
        self.multiline_probe_log = False

    async def browser_action(self, action: str, **kwargs):
        self.browser_calls.append((action, dict(kwargs)))
        if action == "navigate":
            return {
                "url": "http://127.0.0.1:3000/",
                "requested_url": kwargs.get("url", ""),
                "title": "easy_login Dashboard",
            }
        if action == "get_content":
            return {
                "content": "easy_login Login Portal Playground /login /visit /admin",
                "html": """
                <html>
                  <body>
                    <form id="loginForm" action="/login" method="post">
                      <input id="username" name="username" />
                      <input id="password" name="password" type="password" />
                    </form>
                    <a href="/visit">visit</a>
                    <a href="/admin">admin</a>
                  </body>
                </html>
                """,
            }
        if action == "get_forms":
            return {
                "forms": [
                    {
                        "action": "http://127.0.0.1:3000/login",
                        "method": "post",
                        "inputs": [
                            {"name": "username", "type": "text"},
                            {"name": "password", "type": "password"},
                        ],
                    }
                ]
            }
        return {"error": f"unexpected browser action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        self.proxy_calls.append((action, dict(kwargs)))
        url = str(kwargs.get("url") or "")
        method = str(kwargs.get("method") or "").upper()

        if action == "get" and url == "http://127.0.0.1:3000/app.js":
            return {
                "status_code": 200,
                "body": "const loginPath='/login'; const visitPath='/visit'; const adminPath='/admin';",
            }

        if action == "request" and method == "POST" and url == "http://127.0.0.1:3000/visit":
            visit_target = str((kwargs.get("json") or {}).get("url") or "")
            if visit_target.startswith("http://127.0.0.1:7777"):
                self.internal_probe_visited = True
            return {"status_code": 200, "body": "visit ok"}

        if action == "request" and method == "GET" and url == "http://127.0.0.1:3000/admin":
            cookie = str(kwargs.get("headers", {}).get("Cookie") or "")
            self.admin_sid_used = cookie
            if "sid=container-admin-sid" in cookie:
                return {
                    "status_code": 200,
                    "body": "welcome admin\nflag{docker_loopback_fallback}",
                }
            return {"status_code": 403, "body": "forbidden"}

        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 300):
        self.commands.append(command)
        if "docker ps --format" in command:
            return _CommandResult(
                0,
                stdout="easy_login_app|0.0.0.0:3000->3000/tcp\n",
            )
        if (
            "docker exec easy_login_app sh -lc" in command
            and ("node -e" in command or "node /tmp/flaghunter_visit_collector.js" in command)
        ):
            self.internal_probe_started = True
            return _CommandResult(0, stdout="")
        if "docker cp " in command and "flaghunter_visit_collector.js" in command:
            return _CommandResult(0, stdout="")
        if (
            "docker exec easy_login_app sh -lc" in command
            and "cat /tmp/flaghunter_visit_collector.log" in command
        ):
            if self.internal_probe_visited:
                if self.multiline_probe_log:
                    return _CommandResult(
                        0,
                        stdout="/\n/c?sid=sid%3Dcontainer-admin-sid\n/favicon.ico\n",
                    )
                return _CommandResult(0, stdout="/c?sid=container-admin-sid\n")
            return _CommandResult(1, stderr="probe log empty")
        if "flaghunter_visit_collector" in command:
            return _CommandResult(0, stdout="")
        return _CommandResult(1, stderr=f"unexpected command: {command}")


@pytest.mark.asyncio
async def test_runtime_only_loopback_target_falls_back_to_container_local_probe(monkeypatch):
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    runtime = _DockerLoopbackFallbackRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="http://127.0.0.1:3000",
        goal="Analyze the running challenge only and recover the real flag without local assets.",
        type="web",
        challenge_context=None,
    )

    assert result.success is True
    assert result.flag == "flag{docker_loopback_fallback}"
    assert result.reason == "docker localhost visit fallback"
    assert runtime.internal_probe_started is True
    assert runtime.internal_probe_visited is True
    assert runtime.admin_sid_used == "sid=container-admin-sid"
    assert any("docker ps --format" in command for command in runtime.commands)
    assert any(
        "cat /tmp/flaghunter_visit_collector.log" in command for command in runtime.commands
    )


@pytest.mark.asyncio
async def test_loopback_container_fallback_survives_external_collector_bind_conflict(monkeypatch):
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    async def _port_conflict(self):
        raise OSError(10048, "address already in use")

    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher._CollectorServer.start",
        _port_conflict,
    )

    runtime = _DockerLoopbackFallbackRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="http://127.0.0.1:3000",
        goal="Analyze the running challenge only and recover the real flag without local assets.",
        type="web",
        challenge_context=None,
    )

    assert result.success is True
    assert result.flag == "flag{docker_loopback_fallback}"
    assert result.reason == "docker localhost visit fallback"


@pytest.mark.asyncio
async def test_loopback_container_fallback_ignores_favicon_noise_in_probe_log(monkeypatch):
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    runtime = _DockerLoopbackFallbackRuntime()
    runtime.multiline_probe_log = True
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="http://127.0.0.1:3000",
        goal="Analyze the running challenge only and recover the real flag without local assets.",
        type="web",
        challenge_context=None,
    )

    assert result.success is True
    assert result.flag == "flag{docker_loopback_fallback}"
    assert runtime.admin_sid_used == "sid=container-admin-sid"
