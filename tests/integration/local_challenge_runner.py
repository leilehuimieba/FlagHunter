from __future__ import annotations

from pathlib import Path

from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from tests.integration.local_challenge_catalog import (
    LocalChallengeSample,
    get_local_challenge_sample,
    build_challenge_context,
)


class _EvalCommandResult:
    def __init__(self, exit_code: int, stdout: str = "", stderr: str = ""):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class _EasyLoginLocalAssetRuntime:
    def __init__(self, *, enable_local_pivot: bool):
        self.environment = type("Env", (), {"available_tools": []})()
        self.enable_local_pivot = enable_local_pivot
        self.requests: list[tuple[str, str, dict]] = []
        self.commands: list[str] = []

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://127.0.0.1:3000/", "title": "easy_login"}
        if action == "get_content":
            return {
                "content": "easy_login Login Portal Playground /login /visit /admin",
                "html": """
                <html>
                  <body>
                    <form action="/" method="get">
                      <input name="username" />
                      <input name="password" type="password" />
                    </form>
                    <a href="/login">login</a>
                    <a href="/admin">admin</a>
                    <a href="/visit">visit</a>
                  </body>
                </html>
                """,
            }
        if action == "get_forms":
            return {
                "forms": [
                    {
                        "action": "http://127.0.0.1:3000/",
                        "method": "get",
                        "inputs": [
                            {"name": "username", "type": "text"},
                            {"name": "password", "type": "password"},
                        ],
                    }
                ]
            }
        return {"error": f"unexpected browser action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        self.requests.append((action, kwargs.get("url", ""), dict(kwargs)))
        url = str(kwargs.get("url") or "")
        if action == "get" and url == "http://127.0.0.1:3000/app.js":
            return {
                "status_code": 200,
                "body": "const loginPath='/login'; const visitPath='/visit'; const adminPath='/admin';",
            }
        if action == "request" and url == "http://127.0.0.1:3000/login":
            return {
                "status_code": 200,
                "headers": {"set-cookie": "sid=admin-eval-sid; Path=/; HttpOnly"},
                "body": "login ok",
            }
        if action == "request" and url == "http://127.0.0.1:3000/admin":
            cookies = str(kwargs.get("headers", {}).get("Cookie") or "")
            if "sid=admin-eval-sid" in cookies:
                return {"status_code": 200, "body": "welcome admin\nflag{dummy_flag_for_testing}"}
            return {"status_code": 403, "body": "forbidden"}
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 300):
        self.commands.append(command)
        if self.enable_local_pivot and "docker compose -f" in command and "logs --no-color --tail 200" in command:
            return _EvalCommandResult(0, stdout="Admin password set to: super-secret-admin-pass")
        return _EvalCommandResult(1, stderr=f"unexpected command: {command}")


class _EasyLoginRuntimeOnlyFallbackRuntime:
    def __init__(self):
        self.environment = type("Env", (), {"available_tools": []})()
        self.requests: list[tuple[str, str, dict]] = []
        self.commands: list[str] = []
        self.internal_probe_started = False
        self.internal_probe_visited = False

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://127.0.0.1:3000/", "title": "easy_login"}
        if action == "get_content":
            return {
                "content": "easy_login Login Portal Playground /login /visit /admin",
                "html": """
                <html>
                  <body>
                    <form action="/" method="get">
                      <input name="username" />
                      <input name="password" type="password" />
                    </form>
                    <a href="/login">login</a>
                    <a href="/admin">admin</a>
                    <a href="/visit">visit</a>
                  </body>
                </html>
                """,
            }
        if action == "get_forms":
            return {
                "forms": [
                    {
                        "action": "http://127.0.0.1:3000/",
                        "method": "get",
                        "inputs": [
                            {"name": "username", "type": "text"},
                            {"name": "password", "type": "password"},
                        ],
                    }
                ]
            }
        return {"error": f"unexpected browser action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        self.requests.append((action, kwargs.get("url", ""), dict(kwargs)))
        url = str(kwargs.get("url") or "")
        method = str(kwargs.get("method") or "").upper()
        if action == "get" and url == "http://127.0.0.1:3000/app.js":
            return {
                "status_code": 200,
                "body": "const loginPath='/login'; const visitPath='/visit'; const adminPath='/admin';",
            }
        if action == "request" and method == "POST" and url == "http://127.0.0.1:3000/visit":
            visit_target = str((kwargs.get("json") or {}).get("url") or "")
            if visit_target.startswith("http://127.0.0.1:7777/"):
                self.internal_probe_visited = True
                return {"status_code": 200, "body": '{"ok":true}'}
            return {"status_code": 200, "body": '{"ok":true}'}
        if action == "request" and method == "GET" and url == "http://127.0.0.1:3000/admin":
            cookies = str(kwargs.get("headers", {}).get("Cookie") or "")
            if "sid=admin-eval-sid" in cookies:
                return {"status_code": 200, "body": "welcome admin\nflag{dummy_flag_for_testing}"}
            return {"status_code": 403, "body": "forbidden"}
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 300):
        self.commands.append(command)
        if 'docker ps --format "{{.Names}}|{{.Ports}}"' in command:
            return _EvalCommandResult(0, stdout="easy_login_app|0.0.0.0:3000->3000/tcp\n")
        if "docker cp " in command and "flaghunter_visit_collector.js" in command:
            return _EvalCommandResult(0, stdout="")
        if (
            "docker exec easy_login_app sh -lc" in command
            and "node /tmp/flaghunter_visit_collector.js" in command
        ):
            self.internal_probe_started = True
            return _EvalCommandResult(0, stdout="")
        if (
            "docker exec easy_login_app sh -lc" in command
            and "cat /tmp/flaghunter_visit_collector.log" in command
        ):
            if self.internal_probe_visited:
                return _EvalCommandResult(
                    0,
                    stdout="/\n/c?sid=sid%3Dadmin-eval-sid\n/favicon.ico\n",
                )
            return _EvalCommandResult(1, stderr="probe log empty")
        if "docker exec easy_login_app sh -lc" in command and "flaghunter_visit_collector.pid" in command:
            return _EvalCommandResult(0, stdout="")
        return _EvalCommandResult(1, stderr=f"unexpected command: {command}")


class _SourceOnlyHonestyRuntime:
    def __init__(self):
        self.environment = type("Env", (), {"available_tools": []})()
        self.requests: list[tuple[str, str, dict]] = []
        self.commands: list[str] = []

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://127.0.0.1:3000/", "title": "candidate sample"}
        if action == "get_content":
            return {
                "content": "candidate sample runtime unavailable",
                "html": "<html><body><h1>candidate sample runtime unavailable</h1></body></html>",
            }
        if action == "get_forms":
            return {"forms": []}
        return {"error": f"unexpected browser action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        self.requests.append((action, kwargs.get("url", ""), dict(kwargs)))
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 300):
        self.commands.append(command)
        return _EvalCommandResult(1, stderr=f"unexpected command: {command}")


async def run_active_local_challenge_sample(
    sample: LocalChallengeSample,
    *,
    variant: str,
    monkeypatch,
    tmp_dir: Path | None = None,
):
    normalized_variant = str(variant or "").strip().lower()
    if normalized_variant not in sample.supported_variants:
        raise ValueError(
            f"unsupported variant '{variant}' for sample '{sample.key}'"
        )

    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    enable_local_pivot = normalized_variant in {"directory", "zip"}
    if sample.key == "easy_login":
        if normalized_variant == "runtime_only":
            runtime = _EasyLoginRuntimeOnlyFallbackRuntime()
        else:
            runtime = _EasyLoginLocalAssetRuntime(enable_local_pivot=enable_local_pivot)
    elif sample.key == "backup_node_app":
        runtime = _SourceOnlyHonestyRuntime()
    else:
        raise NotImplementedError(f"active runner not implemented for sample: {sample.key}")
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    run_kwargs = {
        "target": sample.target,
        "goal": sample.minimal_prompt,
        "type": sample.mode_subtype,
    }
    if normalized_variant in {"directory", "zip"}:
        run_kwargs["challenge_context"] = build_challenge_context(
            sample,
            variant=normalized_variant,
            tmp_dir=tmp_dir,
        )
    else:
        run_kwargs["hint"] = ""

    return await dispatcher.run(**run_kwargs)


async def run_catalog_local_challenge_eval_case(
    case: dict[str, str],
    *,
    monkeypatch,
    tmp_dir: Path | None = None,
):
    sample = get_local_challenge_sample(case["sample_key"])
    return await run_active_local_challenge_sample(
        sample,
        variant=case["variant"],
        monkeypatch=monkeypatch,
        tmp_dir=tmp_dir,
    )
