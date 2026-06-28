"""端到端 + 单元：web 链经桥接可达 idor_sequential / open_redirect 真实探测并确认原语。

框架能力扩面（gap 驱动闭环）：标注层此前把 IDOR（WSTG-ATHZ-04）与开放重定向
（WSTG-CLNT-04）列为未编目 web gap。本测试证明新增的两条策略 ①有真实探测实现
（IDOR 枚举顺序对象 id 比对不同记录；开放重定向注入良性站外 canary 验重定向 sink），
②经 chains/web.py 的 WEB_STRATEGY_ORDER 桥接在 web 链可达（reachability invariant
另由 test_chain_reachability_invariant 守护），③对脆弱应用确认原语并沉淀 note，
④对安全应用不误报。两者均诚实定位为访问控制 / 客户端重定向原语（非 flag 读取）。
开放重定向 canary 一律用良性不可解析的 ``.invalid`` 域，绝不外连。
零回归由全量 unit 套件保证。
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from flaghunter.agents.pa_agent.chains.injection import GenericInjectionChainMixin
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.strategy_registry import StrategyContext, StrategyRegistry
from flaghunter.tools.notes import set_notes_file
import flaghunter.tools.notes as notes_module


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
_IDOR_OBJECTS = {
    "1": "<html>User Alice role admin note alpha eyes-only record</html>",
    "2": "<html>User Bob role staff note beta eyes-only record</html>",
    "3": "<html>User Carol role guest note gamma eyes-only record</html>",
}


class _IdorRuntime:
    """An app whose ``/profile?id=N`` directly selects a record by id.

    ``guarded=False`` returns a distinct record per id (IDOR present);
    ``guarded=True`` returns an identical access-denied page for every id
    (proper authorization → must not false-positive).
    """

    def __init__(self, guarded: bool = False):
        self.guarded = guarded
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[str] = []

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "Account"}
        if action == "get_content":
            return {
                "content": "Your account profile and order history.",
                "html": "<html><body><form method=GET action=/profile>"
                "<input name=id type=text></form></body></html>",
            }
        if action == "get_forms":
            return {
                "forms": [
                    {"method": "GET", "action": "/profile", "inputs": [{"name": "id", "type": "text"}]}
                ]
            }
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        url = str(kwargs.get("url") or "")
        self.requests.append(url)
        params = parse_qs(urlparse(url).query, keep_blank_values=True)
        id_value = (params.get("id") or [""])[0]
        if not id_value.isdigit():
            return {"status_code": 200, "body": "<html><body>no results</body></html>"}
        if self.guarded:
            return {"status_code": 200, "body": "<html><body>Access denied</body></html>"}
        return {"status_code": 200, "body": _IDOR_OBJECTS.get(id_value, "<html>unknown</html>")}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _OpenRedirectRuntime:
    """An app whose ``?next=`` value drives a client-side redirect sink.

    ``guarded=False`` reflects the value into a ``<meta refresh>`` sink (open
    redirect); ``guarded=True`` validates/strips it (no sink → no FP).
    """

    def __init__(self, guarded: bool = False):
        self.guarded = guarded
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[str] = []

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "Login"}
        if action == "get_content":
            return {
                "content": "Please log in to continue.",
                "html": "<html><body><form method=GET action=/login>"
                "<input name=next type=text></form></body></html>",
            }
        if action == "get_forms":
            return {
                "forms": [
                    {"method": "GET", "action": "/login", "inputs": [{"name": "next", "type": "text"}]}
                ]
            }
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        url = str(kwargs.get("url") or "")
        self.requests.append(url)
        params = parse_qs(urlparse(url).query, keep_blank_values=True)
        value = (params.get("next") or params.get("redirect") or [""])[0]
        if value and not self.guarded:
            return {
                "status_code": 200,
                "body": f'<html><head><meta http-equiv="refresh" content="0; url={value}">'
                "</head><body>redirecting</body></html>",
            }
        return {"status_code": 200, "body": "<html><body>welcome</body></html>"}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


def _reset_notes(tmp_path, name: str) -> None:
    set_notes_file(tmp_path / name)
    notes_module._notes.clear()


def _cleanup_notes() -> None:
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


def _make_dispatcher(monkeypatch, runtime) -> CTFTaskDispatcher:
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    return CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )


# ---------------------------------------------------------------------------
# IDOR — end-to-end
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_web_chain_confirms_idor_on_enumerable_app(monkeypatch, tmp_path):
    _reset_notes(tmp_path, "notes_idor_vuln.json")
    runtime = _IdorRuntime(guarded=False)
    dispatcher = _make_dispatcher(monkeypatch, runtime)

    await dispatcher.run(target="http://ctf.local/", goal="找漏洞", type="web", hint="")

    # sequential object ids were actually enumerated
    assert any("id=2" in url for url in runtime.requests)
    assert any("ctf_idor_confirmed" in line for line in dispatcher._notes_log), (
        "expected an IDOR confirmation to be recorded"
    )
    _cleanup_notes()


@pytest.mark.asyncio
async def test_idor_does_not_false_positive_on_guarded_app(monkeypatch, tmp_path):
    _reset_notes(tmp_path, "notes_idor_safe.json")
    runtime = _IdorRuntime(guarded=True)
    dispatcher = _make_dispatcher(monkeypatch, runtime)

    await dispatcher.run(target="http://ctf.local/", goal="找漏洞", type="web", hint="")

    assert any("id=2" in url for url in runtime.requests)  # probe still ran
    assert not any("ctf_idor_confirmed" in line for line in dispatcher._notes_log)
    _cleanup_notes()


# ---------------------------------------------------------------------------
# Open redirect — end-to-end
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_web_chain_confirms_open_redirect_on_reflecting_app(monkeypatch, tmp_path):
    _reset_notes(tmp_path, "notes_oredir_vuln.json")
    runtime = _OpenRedirectRuntime(guarded=False)
    dispatcher = _make_dispatcher(monkeypatch, runtime)

    await dispatcher.run(target="http://ctf.local/", goal="找漏洞", type="web", hint="")

    # the off-site canary was injected and only ever points at an .invalid sink
    assert any("oob-fhor7dr3ct.example.invalid" in url for url in runtime.requests)
    assert all(".invalid" in url for url in runtime.requests if "oob-fhor7dr3ct" in url)
    assert any("ctf_open_redirect_confirmed" in line for line in dispatcher._notes_log), (
        "expected an open-redirect confirmation to be recorded"
    )
    _cleanup_notes()


@pytest.mark.asyncio
async def test_open_redirect_does_not_false_positive_on_guarded_app(monkeypatch, tmp_path):
    _reset_notes(tmp_path, "notes_oredir_safe.json")
    runtime = _OpenRedirectRuntime(guarded=True)
    dispatcher = _make_dispatcher(monkeypatch, runtime)

    await dispatcher.run(target="http://ctf.local/", goal="找漏洞", type="web", hint="")

    assert any("oob-fhor7dr3ct.example.invalid" in url for url in runtime.requests)
    assert not any("ctf_open_redirect_confirmed" in line for line in dispatcher._notes_log)
    _cleanup_notes()


# ---------------------------------------------------------------------------
# IDOR — unit
# ---------------------------------------------------------------------------
def test_idor_id_series_around_base_positive_only():
    cls = GenericInjectionChainMixin
    assert cls._idor_id_series(5) == [5, 4, 6, 7, 1, 2, 3]
    assert cls._idor_id_series(1) == [1, 2, 3]  # neighbours <=0 dropped


def test_enumerate_idor_ids_query_and_path():
    cls = GenericInjectionChainMixin
    q = dict(cls._enumerate_idor_ids("http://h/profile?id=10&tab=x"))
    assert q["9"].endswith("id=9&tab=x") or "id=9" in q["9"]
    assert "tab=x" in q["11"]  # other params preserved
    p = dict(cls._enumerate_idor_ids("http://h/user/10/view"))
    assert "/user/9/view" in p["9"] and "/user/11/view" in p["11"]


def test_normalize_idor_body_masks_echoed_id():
    cls = GenericInjectionChainMixin
    # two error templates differing ONLY by the echoed id must normalize equal
    a = cls._normalize_idor_body("User 41 not found", "41")
    b = cls._normalize_idor_body("User 42 not found", "42")
    assert a == b
    # genuinely different object data stays distinct
    c = cls._normalize_idor_body("Alice admin", "1")
    d = cls._normalize_idor_body("Bob staff", "2")
    assert c != d


def test_idor_object_like_rejects_errors_and_denials():
    cls = GenericInjectionChainMixin
    assert cls._idor_object_like(200, "User Alice role admin private note alpha record body") is True
    assert cls._idor_object_like(404, "User Alice role admin private note alpha record body") is False
    assert cls._idor_object_like(200, "Access denied for this resource page body") is False
    assert cls._idor_object_like(200, "tiny") is False  # too short to be an object


def test_idor_precondition_detects_surface_and_rejects_plain():
    surface = StrategyContext(
        target="http://ctf.local/",
        page_features={"raw_links": ["http://ctf.local/profile?id=7"]},
        hint="",
        services=None,
    )
    plain = StrategyContext(
        target="http://ctf.local/",
        page_features={"content": "a static landing page", "forms": [], "raw_links": []},
        hint="",
        services=None,
    )
    strategy = StrategyRegistry.build_default().get("idor_sequential")
    assert strategy is not None
    assert strategy.is_applicable(surface) is True
    assert strategy.is_applicable(plain) is False


# ---------------------------------------------------------------------------
# Open redirect — unit
# ---------------------------------------------------------------------------
def test_open_redirect_canary_is_benign_invalid_domain():
    canary = GenericInjectionChainMixin._open_redirect_canary()
    assert canary.endswith(".invalid/") and "oob-" in canary


def test_inject_open_redirect_sets_canary_on_redirect_params():
    cls = GenericInjectionChainMixin
    out = cls._inject_open_redirect("http://h/login?next=/home&x=1")
    params = parse_qs(urlparse(out).query)
    assert params["next"] == [cls._open_redirect_canary()]
    assert params["x"] == ["1"]  # non-redirect params untouched
    # no redirect param present → a redirect param is added
    added = parse_qs(urlparse(cls._inject_open_redirect("http://h/p?x=1")).query)
    assert added["redirect"] == [cls._open_redirect_canary()]


def test_open_redirect_confirmed_detects_sinks_and_ignores_safe():
    cls = GenericInjectionChainMixin
    canary = cls._open_redirect_canary()
    host = "oob-fhor7dr3ct.example.invalid"
    # client-side meta-refresh sink
    body = f'<meta http-equiv="refresh" content="0; url={canary}">'
    assert cls._open_redirect_confirmed(body, None, None) == "client-side-sink"
    # server Location header
    assert cls._open_redirect_confirmed("", {"Location": canary}, None) == "location-header"
    # redirect hop
    assert cls._open_redirect_confirmed("", None, [{"location": canary}]) == "redirect-chain"
    # canary present but NOT in a redirect sink (plain echo) → not confirmed
    assert cls._open_redirect_confirmed(f"see {host}", None, None) == ""
    # safe app stripped the canary
    assert cls._open_redirect_confirmed("<html>welcome</html>", {}, []) == ""


def test_open_redirect_precondition_detects_surface_and_rejects_plain():
    surface = StrategyContext(
        target="http://ctf.local/",
        page_features={"raw_links": ["http://ctf.local/login?next=/dashboard"]},
        hint="",
        services=None,
    )
    plain = StrategyContext(
        target="http://ctf.local/",
        page_features={"content": "a static landing page", "forms": [], "raw_links": []},
        hint="",
        services=None,
    )
    strategy = StrategyRegistry.build_default().get("open_redirect")
    assert strategy is not None
    assert strategy.is_applicable(surface) is True
    assert strategy.is_applicable(plain) is False
