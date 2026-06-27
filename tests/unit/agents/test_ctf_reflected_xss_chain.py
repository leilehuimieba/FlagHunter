"""端到端 + 单元：web 链经桥接可达 reflected_xss 真实探测并确认客户端注入原语。

框架能力扩面：此前框架只有存储型/admin-bot XSS（xss_admin_bot_sid，WSTG-INPV-02），
缺反射型 XSS（WSTG-INPV-01）。本测试证明新增的 reflected_xss 策略 ①有真实探测实现
（注入带唯一 marker 的 canary，确认未转义回显），②经 chains/web.py 的
WEB_STRATEGY_ORDER 桥接在 web 链可达（reachability invariant 另由
test_chain_reachability_invariant 守护），③对会回显的应用确认漏洞并沉淀 note，
④对正确转义的应用不误报。反射型 XSS 诚实定位为客户端注入原语（取 flag 走 admin-bot
链），故端到端断言落在「确认 + note + 真实发出未转义 canary」而非 flag。
零回归由全量 unit 套件保证。
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from flaghunter.agents.pa_agent.chains.injection import GenericInjectionChainMixin
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.strategy_registry import StrategyContext, StrategyRegistry
from flaghunter.tools.notes import set_notes_file
import flaghunter.tools.notes as notes_module


class _ReflectingRuntime:
    """一个把 GET 查询参数原样（``escape=False``）或实体编码（``escape=True``）回显的应用。

    ``escape=False`` 模拟存在反射型 XSS 的脆弱应用（canary 未转义回显）；
    ``escape=True`` 模拟正确做输出编码的安全应用（用于反向证明不误报）。
    """

    def __init__(self, escape: bool = False):
        self.escape = escape
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[tuple[str, str, str]] = []

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "Search"}
        if action == "get_content":
            return {
                "content": "Site search. Use the search box to find items.",
                "html": "<html><body><form method=GET action=/search>"
                "<input name=q type=text></form></body></html>",
            }
        if action == "get_forms":
            return {
                "forms": [
                    {
                        "method": "GET",
                        "action": "/search",
                        "inputs": [{"name": "q", "type": "text"}],
                    }
                ]
            }
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        method = str(kwargs.get("method") or "GET").upper()
        url = str(kwargs.get("url") or "")
        self.requests.append((method, url, str(kwargs.get("data") or "")))
        if method != "GET":
            return {"status_code": 200, "body": "<html><body>no results</body></html>"}
        params = parse_qs(urlparse(url).query, keep_blank_values=True)
        reflected = " ".join(value for values in params.values() for value in values)
        if not reflected:
            return {"status_code": 200, "body": "<html><body>no results</body></html>"}
        if self.escape:
            reflected = (
                reflected.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )
        return {"status_code": 200, "body": f"<html><body>Results for: {reflected}</body></html>"}

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


@pytest.mark.asyncio
async def test_web_chain_confirms_reflected_xss_on_vulnerable_app(monkeypatch, tmp_path):
    _reset_notes(tmp_path, "notes_rxss_vuln.json")
    runtime = _ReflectingRuntime(escape=False)
    dispatcher = _make_dispatcher(monkeypatch, runtime)

    await dispatcher.run(target="http://ctf.local/", goal="找漏洞", type="web", hint="")

    # an XSS canary carrying raw HTML markup was actually sent to a reflectable
    # parameter (percent-encoded in the URL; decode to see the raw markup)
    assert any(
        "<script>" in unquote(url) and "fhx55r3fl" in url for _, url, _ in runtime.requests
    ), "expected a reflected-XSS canary in a sent request"
    # the unescaped reflection was confirmed and recorded
    assert any(
        "ctf_reflected_xss_confirmed" in line for line in dispatcher._notes_log
    ), "expected a reflected-XSS confirmation to be recorded"
    _cleanup_notes()


@pytest.mark.asyncio
async def test_reflected_xss_does_not_false_positive_on_escaping_app(monkeypatch, tmp_path):
    _reset_notes(tmp_path, "notes_rxss_safe.json")
    runtime = _ReflectingRuntime(escape=True)
    dispatcher = _make_dispatcher(monkeypatch, runtime)

    await dispatcher.run(target="http://ctf.local/", goal="找漏洞", type="web", hint="")

    # the probe ran (canary sent) but the app encoded output → no confirmation
    assert any("fhx55r3fl" in url for _, url, _ in runtime.requests)
    assert not any(
        "ctf_reflected_xss_confirmed" in line for line in dispatcher._notes_log
    )
    _cleanup_notes()


# ---------------------------------------------------------------------------
# Unit: payload shape + reflection detector + precondition
# ---------------------------------------------------------------------------


def test_build_reflected_xss_payloads_are_dangerous_canaries():
    payloads = GenericInjectionChainMixin._build_reflected_xss_payloads()
    assert payloads, "expected at least one reflected-XSS payload"
    marker = GenericInjectionChainMixin._REFLECTED_XSS_MARKER
    for payload in payloads:
        assert marker in payload
        assert "<" in payload  # carries raw HTML-significant characters


def test_reflected_xss_detector_requires_unescaped_reflection():
    cls = GenericInjectionChainMixin
    marker = cls._REFLECTED_XSS_MARKER
    assert cls._reflected_xss_reflected_unescaped(f"x <script>{marker}() y") is True
    assert cls._reflected_xss_reflected_unescaped(f"<img src=x onerror={marker}()>") is True
    # entity-encoded reflection must NOT count as a hit
    assert cls._reflected_xss_reflected_unescaped(f"&lt;script&gt;{marker}()&lt;/script&gt;") is False
    # marker absent → no hit
    assert cls._reflected_xss_reflected_unescaped("<script>other()</script>") is False


def test_reflected_xss_precondition_detects_surface_and_rejects_plain():
    surface_form = StrategyContext(
        target="http://ctf.local/",
        page_features={
            "forms": [
                {"method": "GET", "action": "/search", "inputs": [{"name": "q", "type": "text"}]}
            ]
        },
        hint="",
        services=None,
    )
    surface_search_hint = StrategyContext(
        target="http://ctf.local/",
        page_features={"content": "Use the search box to find products", "forms": []},
        hint="",
        services=None,
    )
    plain = StrategyContext(
        target="http://ctf.local/",
        page_features={"content": "a static landing page", "forms": [], "endpoints": []},
        hint="",
        services=None,
    )
    strategy = StrategyRegistry.build_default().get("reflected_xss")
    assert strategy is not None
    assert strategy.is_applicable(surface_form) is True
    assert strategy.is_applicable(surface_search_hint) is True
    assert strategy.is_applicable(plain) is False
