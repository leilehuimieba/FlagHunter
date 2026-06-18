"""端到端：web 链经桥接可达 graphql/nosql 真实探测并解题。

配套 docs/dev/基准_CTF能力与可达性 §4.1 缺口闭合：graphql_introspection /
nosql_injection 此前注册了但无真实 handler、且不可达。本测试证明二者现在
①有真实探测实现，②经 chains/web.py 的 web_strategy_order 桥接在 web 链可达，
③端到端能解出 flag。零回归由全量 unit 套件保证。
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.tools.notes import set_notes_file
import flaghunter.tools.notes as notes_module


class _GraphQLIntrospectionRuntime:
    """提供一个含 GraphQL 端点的 web 页面；内省暴露 secretFlag 字段，跟进查询取 flag。"""

    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[tuple[str, str]] = []

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "API Playground"}
        if action == "get_content":
            return {
                "content": "API Playground. GraphQL endpoint available at /graphql for queries.",
                "html": "<html><body><h1>API Playground</h1>"
                "<p>Our GraphQL API is at <a href=\"/graphql\">/graphql</a></p></body></html>",
            }
        if action == "get_forms":
            return {"forms": []}
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        url = str(kwargs.get("url") or "")
        self.requests.append((action, url))
        if "/graphql" in url:
            query = ""
            json_body = kwargs.get("json")
            if isinstance(json_body, dict):
                query = str(json_body.get("query") or "")
            if not query:
                query = (parse_qs(urlparse(url).query).get("query") or [""])[0]
            if "__schema" in query:
                return {
                    "status_code": 200,
                    "body": '{"data":{"__schema":{"queryType":{"name":"Query"},'
                    '"types":[{"name":"Query","fields":[{"name":"user"},{"name":"secretFlag"}]}]}}}',
                }
            if "secretFlag" in query:
                return {
                    "status_code": 200,
                    "body": '{"data":{"secretFlag":"flag{graphql_introspection_ok}"}}',
                }
        return {"status_code": 404, "body": "not found"}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _NoSQLInjectionRuntime:
    """提供一个 MongoDB 后端线索的 web 页面；/login 对算子注入返回登录成功 + flag。"""

    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[tuple[str, str]] = []

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "Members"}
        if action == "get_content":
            return {
                "content": "Members area. Backend powered by mongodb / mongoose. "
                "Sign in at the members API.",
                "html": "<html><body><h1>Members</h1>"
                "<p>mongoose-backed members API</p></body></html>",
            }
        if action == "get_forms":
            return {"forms": []}
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        url = str(kwargs.get("url") or "")
        self.requests.append((action, url))
        if "/login" in url:
            json_body = kwargs.get("json")
            data = kwargs.get("data")
            injected = False
            if isinstance(json_body, dict):
                injected = any(isinstance(value, dict) for value in json_body.values())
            if isinstance(data, dict):
                injected = injected or any("[$" in str(key) for key in data)
            if injected:
                return {
                    "status_code": 200,
                    "body": "Welcome admin! flag{nosql_bypass_ok}",
                    "headers": {"set-cookie": "session=abc"},
                }
            return {"status_code": 401, "body": "invalid credentials"}
        return {"status_code": 404, "body": "not found"}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


def _reset_notes(tmp_path, name: str) -> None:
    set_notes_file(tmp_path / name)
    notes_module._notes.clear()


def _cleanup_notes() -> None:
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_web_chain_solves_graphql_introspection(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    _reset_notes(tmp_path, "notes_graphql.json")

    runtime = _GraphQLIntrospectionRuntime()
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="web",
        hint="",
    )

    assert result.success is True
    assert result.flag == "flag{graphql_introspection_ok}"
    assert "web" in result.chain_used
    assert any("/graphql" in url for _, url in runtime.requests)
    _cleanup_notes()


@pytest.mark.asyncio
async def test_web_chain_solves_nosql_injection(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    _reset_notes(tmp_path, "notes_nosql.json")

    runtime = _NoSQLInjectionRuntime()
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="web",
        hint="",
    )

    assert result.success is True
    assert result.flag == "flag{nosql_bypass_ok}"
    assert "web" in result.chain_used
    assert any("/login" in url for _, url in runtime.requests)
    _cleanup_notes()
