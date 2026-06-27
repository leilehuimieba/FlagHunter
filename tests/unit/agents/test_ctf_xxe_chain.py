"""端到端 + 单元：web 链经桥接可达 xxe_injection 真实探测并解题。

框架能力扩面：此前框架缺 XXE（XML 外部实体）能力。本测试证明新增的
xxe_injection 策略 ①有真实探测实现（POST 经典外部实体 DOCTYPE 读服务端文件），
②经 chains/web.py 的 WEB_STRATEGY_ORDER 桥接在 web 链可达（reachability
invariant 另由 test_chain_reachability_invariant 守护），③端到端能解出 flag。
零回归由全量 unit 套件保证。
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.chains.injection import GenericInjectionChainMixin
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.strategy_registry import StrategyContext, StrategyRegistry
from flaghunter.tools.notes import set_notes_file
import flaghunter.tools.notes as notes_module


class _XXERuntime:
    """一个解析 POST XML body 并解析外部实体的 web 应用。

    当请求体声明 ``<!ENTITY xxe SYSTEM "file:///...">`` 并引用 ``&xxe;`` 时，模拟
    解析器解析外部实体、把（模拟）文件系统中的内容回显进响应——对应经典回显型 XXE
    文件读取利用面。
    """

    FS = {
        "file:///flag": "flag{xxe_entity_read}",
        "file:///flag.txt": "flag{xxe_entity_read}",
        "file:///etc/passwd": "root:x:0:0:root:/root:/bin/bash",
    }

    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[tuple[str, str, str]] = []

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "XML API"}
        if action == "get_content":
            return {
                "content": "XML feed processor. POST application/xml to /api/parse to import a feed.",
                "html": "<html><body>POST <code>application/xml</code> to /api/parse</body></html>",
            }
        if action == "get_forms":
            return {"forms": []}
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        url = str(kwargs.get("url") or "")
        data = str(kwargs.get("data") or "")
        self.requests.append((action, url, data))
        match = re.search(r'<!ENTITY\s+\w+\s+SYSTEM\s+"([^"]+)"', data)
        if match and "&xxe;" in data:
            content = self.FS.get(match.group(1))
            if content is not None:
                return {"status_code": 200, "body": f"<data>{content}</data>"}
        return {"status_code": 200, "body": "<data></data>"}

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
async def test_web_chain_solves_xxe_external_entity(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    _reset_notes(tmp_path, "notes_xxe.json")

    runtime = _XXERuntime()
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
    assert result.flag == "flag{xxe_entity_read}"
    assert "web" in result.chain_used
    # a raw external-entity XML body was actually sent
    assert any(
        "<!ENTITY xxe SYSTEM" in data and "&xxe;" in data
        for _, _, data in runtime.requests
    )
    _cleanup_notes()


# ---------------------------------------------------------------------------
# Unit: payload shape + precondition
# ---------------------------------------------------------------------------


def test_build_xxe_payloads_are_external_entities():
    payloads = GenericInjectionChainMixin._build_xxe_payloads()
    assert payloads, "expected at least one XXE payload"
    uris = {uri for uri, _ in payloads}
    assert "file:///flag" in uris
    assert "file:///etc/passwd" in uris
    for uri, xml in payloads:
        assert "<!DOCTYPE" in xml
        assert f'<!ENTITY xxe SYSTEM "{uri}">' in xml
        assert "&xxe;" in xml


def test_xxe_precondition_detects_xml_surface_and_endpoints():
    precondition_content_clue = StrategyContext(
        target="http://ctf.local/",
        page_features={"content": "POST application/xml to import your feed"},
        hint="",
        services=None,
    )
    precondition_endpoint_clue = StrategyContext(
        target="http://ctf.local/",
        page_features={"endpoints": ["/soap/service"], "raw_links": []},
        hint="",
        services=None,
    )
    precondition_false = StrategyContext(
        target="http://ctf.local/",
        page_features={"content": "an ordinary json site", "endpoints": ["/login"]},
        hint="",
        services=None,
    )
    strategy = StrategyRegistry.build_default().get("xxe_injection")
    assert strategy is not None
    assert strategy.is_applicable(precondition_content_clue) is True
    assert strategy.is_applicable(precondition_endpoint_clue) is True
    assert strategy.is_applicable(precondition_false) is False
