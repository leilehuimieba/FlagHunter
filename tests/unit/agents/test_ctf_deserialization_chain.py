"""端到端 + 单元：web 链经桥接可达 insecure_deserialization 真实探测并解题。

框架能力扩面：此前框架只有 PHP 反序列化（php_unserialize_magic_method），缺
Java / Python pickle 反序列化能力。本测试证明新增的 insecure_deserialization
策略 ①有真实探测实现（Python pickle 回灌 RCE / Java 检测沉淀 note），②经
chains/web.py 的 web_strategy_order 桥接在 web 链可达（reachability invariant
另由 test_chain_reachability_invariant 守护），③端到端能解出 flag。零回归由全量
unit 套件保证。
"""

from __future__ import annotations

import base64
import pickle
from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.chains.injection import GenericInjectionChainMixin
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.strategy_registry import StrategyContext, StrategyRegistry
from flaghunter.tools.notes import set_notes_file
import flaghunter.tools.notes as notes_module


class _PickleDeserRuntime:
    """提供一个用 Python pickle 做 session cookie 的 web 应用。

    seed cookie 是一个无害 pickle（``{"user":"guest"}``）；当请求携带**另一个**
    pickle（我们回灌的 RCE gadget）时，模拟后端反序列化并回显命令输出（含 flag +
    DESER_RCE_OK 标记），对应真实 pickle 反序列化 RCE 的"回显型"利用面。
    """

    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[tuple[str, str, str]] = []
        self.seed_cookie = base64.b64encode(pickle.dumps({"user": "guest"})).decode("ascii")

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "Pickle App"}
        if action == "get_content":
            return {
                "content": "Session app. The session cookie is a python pickle blob.",
                "html": "<html><body><h1>Pickle App</h1><p>pickle-backed sessions</p></body></html>",
            }
        if action == "get_forms":
            return {"forms": []}
        if action == "get_cookies":
            return {"cookie_string": f"session={self.seed_cookie}"}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        url = str(kwargs.get("url") or "")
        headers = kwargs.get("headers") or {}
        cookie = str(headers.get("Cookie") or "")
        self.requests.append((action, url, cookie))
        if "session=" in cookie:
            value = cookie.split("session=", 1)[1].split(";")[0]
            try:
                decoded = base64.b64decode(value + "=" * (-len(value) % 4))
            except Exception:
                decoded = b""
            # injected RCE pickle (≠ baseline) → reflect simulated command output
            if decoded[:1] == b"\x80" and value != self.seed_cookie:
                return {
                    "status_code": 200,
                    "body": "flag{pickle_rce_ok}\nuid=0(root) gid=0(root)\nDESER_RCE_OK",
                }
        return {"status_code": 200, "body": "guest dashboard"}

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
async def test_web_chain_solves_python_pickle_deserialization(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    _reset_notes(tmp_path, "notes_pickle.json")

    runtime = _PickleDeserRuntime()
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
    assert result.flag == "flag{pickle_rce_ok}"
    assert "web" in result.chain_used
    # an injected pickle cookie (≠ the baseline session) was sent
    assert any(
        "session=" in cookie and runtime.seed_cookie not in cookie
        for _, _, cookie in runtime.requests
    )
    _cleanup_notes()


# ---------------------------------------------------------------------------
# Unit: blob classification + precondition
# ---------------------------------------------------------------------------


def test_detect_serialized_blob_classifies_java_and_python():
    detect = GenericInjectionChainMixin._detect_serialized_blob
    python_blob = base64.b64encode(pickle.dumps({"a": 1})).decode("ascii")
    assert detect(python_blob) == ("python", "base64")
    # Java serialized stream magic \xac\xed → base64 "rO0…"
    java_blob = base64.b64encode(b"\xac\xed\x00\x05sr\x00\x11java.util.").decode("ascii")
    assert detect(java_blob) == ("java", "base64")
    assert detect("rO0ABXNyABFqYXZhLnV0aWwu") == ("java", "base64")
    # plain text / short strings are not blobs
    assert detect("hello world this is not a blob") is None
    assert detect("gA") is None


def test_deserialization_precondition_detects_carrier_and_clue():
    precondition_true_carrier = StrategyContext(
        target="http://ctf.local/",
        page_features={"cookies": f"session={base64.b64encode(pickle.dumps([1, 2, 3])).decode()}"},
        hint="",
        services=None,
    )
    precondition_true_clue = StrategyContext(
        target="http://ctf.local/",
        page_features={"content": "this app uses pickle.loads on the cookie"},
        hint="",
        services=None,
    )
    precondition_false = StrategyContext(
        target="http://ctf.local/",
        page_features={"cookies": "session=abc123; theme=dark", "content": "ordinary site"},
        hint="",
        services=None,
    )
    strategy = StrategyRegistry.build_default().get("insecure_deserialization")
    assert strategy is not None
    assert strategy.is_applicable(precondition_true_carrier) is True
    assert strategy.is_applicable(precondition_true_clue) is True
    assert strategy.is_applicable(precondition_false) is False
