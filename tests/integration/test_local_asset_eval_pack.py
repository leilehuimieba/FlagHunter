"""Minimal real eval pack for local challenge asset ingress.

Covers:
1. directory-only success baseline
2. zip-only success baseline
3. no-local-asset honesty baseline
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from tests.integration.easy_login_acceptance import extract_flag
from tests.integration.local_challenge_catalog import (
    build_challenge_context,
    get_local_challenge_sample,
)


pytestmark = pytest.mark.integration


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
                    <form action=\"/\" method=\"get\">
                      <input name=\"username\" />
                      <input name=\"password\" type=\"password\" />
                    </form>
                    <a href=\"/login\">login</a>
                    <a href=\"/admin\">admin</a>
                    <a href=\"/visit\">visit</a>
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


@pytest.fixture
def easy_login_dir() -> Path:
    path = get_local_challenge_sample("easy_login").challenge_path
    if not path.exists():
        pytest.skip("easy_login directory not available")
    return path


@pytest.mark.asyncio
async def test_eval_local_asset_directory_only_success(monkeypatch, easy_login_dir: Path):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    sample = get_local_challenge_sample("easy_login")
    runtime = _EasyLoginLocalAssetRuntime(enable_local_pivot=True)
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target=sample.target,
        goal=sample.minimal_prompt,
        type="web",
        challenge_context=build_challenge_context(sample, variant="directory"),
    )

    assert result.success is True
    assert result.flag == "flag{dummy_flag_for_testing}"
    assert extract_flag(result.flag) == "flag{dummy_flag_for_testing}"


@pytest.mark.asyncio
async def test_eval_local_asset_zip_only_success(monkeypatch, tmp_path: Path, easy_login_dir: Path):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    sample = get_local_challenge_sample("easy_login")
    runtime = _EasyLoginLocalAssetRuntime(enable_local_pivot=True)
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target=sample.target,
        goal=sample.minimal_prompt,
        type="web",
        challenge_context=build_challenge_context(sample, variant="zip", tmp_dir=tmp_path),
    )

    assert result.success is True
    assert result.flag == "flag{dummy_flag_for_testing}"


@pytest.mark.asyncio
async def test_eval_no_local_asset_is_honest_not_false_verified(monkeypatch):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    sample = get_local_challenge_sample("easy_login")
    runtime = _EasyLoginLocalAssetRuntime(enable_local_pivot=False)
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target=sample.target,
        goal=sample.minimal_prompt,
        type="web",
        hint="",
    )

    assert result.success is False
    assert result.flag is None
    assert result.reason
    assert dispatcher.state is not None
    assert dispatcher.state.verified_flags == []
    assert not extract_flag(result.reason)
