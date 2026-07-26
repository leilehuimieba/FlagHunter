"""Second-order SQLi：cyberpunk 型 ceiling 的确定性守护。

框架能力扩面（对标 cyberpunk-class ceiling）：注入值不被"存储它的那条查询"使用，
而是被持久化（注册用户名 / 订单备注 / 评论），随后在另一个 trigger 端点被原样拼进
*另一条* 查询。sqlmap 和所有一阶策略只探测 store 请求、看到值被安全回显，于是判定
"不可注入"——完全够不着这个被延迟的 sink。本测试用一个内存 store→trigger 后端
（真实两步：注册持久化用户名 + home 端点把存储用户名重新拼进 2 列查询）证明新增策略
``second_order_sqli``：

  ① 纯识别器 ``_recognize_second_order_sqli`` 从泄漏源码识别二阶形态
     （INSERT 持久化请求字段 + 后续拼接 DB-fetch 变量的延迟查询），
  ② 执行器在 store 字段种入 UNION payload，扫列数×回显位置用 sentinel 确认延迟
     oracle，再在确认布局上遍历 flag 仓库，从 trigger 响应取回 flag，
  ③ 纯 payload 合成器 ``_second_order_union_value`` 免空格、带 nonce（避免 store 端
     UNIQUE 冲突）、以 ``#`` 注释掉延迟查询的尾部，
  ④ 对一阶（直接用 $_GET 拼接、无 DB 复用）源码不误报。

gadget 仅打本进程内存后端，绝不外连。reachability 由
test_chain_reachability_invariant 守护；零回归由全量 unit 套件保证。
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.exploit_replay_memory import _recognize_second_order_sqli
from flaghunter.agents.pa_agent.sqli_executor import _second_order_union_value
from flaghunter.agents.pa_agent.strategy_registry import StrategyContext, StrategyRegistry
from flaghunter.tools.notes import set_notes_file

_FLAG = "flag{s3c0nd_0rd3r_st0r3d_1nj3ct10n}"

# Leaked source: register.php persists $_POST['username']; home.php re-queries the
# stored username by concatenating a DB-fetched value into a second query — the
# defining second-order shape (store then deferred reuse).
_SOURCE = """<?php
// register.php
$username = $_POST['username'];
$password = $_POST['password'];
$db->query("insert into users(username, password) values('$username', '$password')");
header("Location: home.php");

// home.php
session_start();
$uname = $_SESSION['username'];
$row = $db->query("select id, username from users where id=" . $_SESSION['uid'])->fetch_assoc();
$sql = "select username, secret from members where username='" . $row['username'] . "'";
$res = $db->query($sql)->fetch_assoc();
echo "profile secret: " . $res['secret'];
"""


def _split_top_level(select_list: str) -> list[str]:
    """Split a UNION select-list on top-level commas (ignoring commas in parens)."""
    parts: list[str] = []
    depth = 0
    current = ""
    for ch in select_list:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return [p.strip() for p in parts]


class _SecondOrderRuntime:
    """A store→trigger backend: register persists a username; home re-queries it.

    ``home.php`` emulates ``SELECT username, secret FROM members WHERE
    username='<stored>'`` (two columns). A stored UNION payload of matching
    width executes there: a hex sentinel column proves the deferred oracle; a
    ``(select … from flag)`` column returns the flag. The store request itself
    never executes the payload — first-order probing sees only a safe echo.
    """

    def __init__(self):
        self.store_field = "username"
        self._current_username: str | None = None
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[str] = []

    def _home(self) -> str:
        username = self._current_username
        if username is None:
            return "<html><body>please register</body></html>"
        norm = re.sub(r"\s+", " ", username.replace("/**/", " ")).strip()
        low = norm.lower()
        if "union" not in low or "select" not in low:
            return f"<html><body>welcome back {username}</body></html>"
        match = re.search(r"union\s+select\s+(.*?)#", norm, re.IGNORECASE)
        if not match:
            match = re.search(r"union\s+select\s+(.*)$", norm, re.IGNORECASE)
        if not match:
            return "<html><body>query error</body></html>"
        columns = _split_top_level(match.group(1))
        if len(columns) != 2:  # base query: SELECT username, secret ... (2 cols)
            return "<html><body>query error: column count mismatch</body></html>"
        for col in columns:
            hex_match = re.fullmatch(r"0x([0-9a-fA-F]+)", col)
            if hex_match:
                try:
                    decoded = bytes.fromhex(hex_match.group(1)).decode("latin-1")
                except ValueError:
                    decoded = ""
                if decoded:
                    return f"<html><body>profile secret: {decoded}</body></html>"
            if "flag" in col.lower():
                return f"<html><body>profile secret: {_FLAG}</body></html>"
        return "<html><body>query error</body></html>"

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "cyberpunk"}
        if action == "get_content":
            return {"content": "cyberpunk order portal", "html": "<html><body>register</body></html>"}
        if action == "get_forms":
            return {"forms": []}
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        url = str(kwargs.get("url") or "")
        self.requests.append(url)
        path = urlparse(url).path
        data = kwargs.get("data") or {}
        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        if path.endswith("register.php"):
            username = data.get(self.store_field)
            if username is None:
                username = (query.get(self.store_field) or [None])[0]
            if username is not None:
                self._current_username = str(username)
            return {"status_code": 200, "body": "<html><body>registered, redirecting to home.php</body></html>"}
        if path.endswith("home.php"):
            return {"status_code": 200, "body": self._home()}
        return {"status_code": 200, "body": "<html><body>cyberpunk order portal</body></html>"}

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


_PAGE_FEATURES = {"forms": [], "raw_links": [], "content": "cyberpunk order portal"}


# ---------------------------------------------------------------------------
# Behavioral: store UNION payload → trigger deferred query → verified flag
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_second_order_sqli_recovers_flag_end_to_end(monkeypatch, tmp_path):
    _reset_notes(tmp_path, "notes_second_order_vuln.json")
    runtime = _SecondOrderRuntime()
    dispatcher = _make_dispatcher(monkeypatch, runtime)
    dispatcher.state = CTFState(target="http://ctf.local/register.php", goal="拿到flag")
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        _SOURCE,
        metadata={"path": "/tmp/cyberpunk/src.php", "file_name": "src.php"},
    )

    outcome = await dispatcher._execute_web_chain(
        "http://ctf.local/register.php", _PAGE_FEATURES, ""
    )

    assert outcome.flag == _FLAG
    # The exploit is a two-request store→trigger cycle: both endpoints were hit.
    assert any("register.php" in url for url in runtime.requests)
    assert any("home.php" in url for url in runtime.requests)
    assert any(
        "ctf_second_order_sqli_confirmed" in line for line in dispatcher._notes_log
    ), "expected the deferred UNION oracle to be recorded"
    assert any(
        "ctf_second_order_sqli_extract" in line for line in dispatcher._notes_log
    ), "expected the second-order extraction to be verified"
    _cleanup_notes()


# ---------------------------------------------------------------------------
# Unit: stored-payload synthesizer is WAF-lean, nonce-unique, comment-terminated
# ---------------------------------------------------------------------------
def test_second_order_union_value_shape():
    value = _second_order_union_value("fh2o0007", "0xdead", 2, 1, "/**/")
    assert value == "fh2o0007'/**/union/**/select/**/0xdead,2#"
    assert value.endswith("#")  # comments out the deferred query's tail
    assert " " not in value  # WAF-lean when the /**/ separator is used
    # a distinct nonce yields a distinct stored row (avoids UNIQUE collisions)
    other = _second_order_union_value("fh2o0008", "0xdead", 2, 1, "/**/")
    assert other != value
    # the injected expression can sit at any echo position
    assert _second_order_union_value("n", "X", 3, 2, " ") == "n' union select 1,X,3#"


# ---------------------------------------------------------------------------
# Unit: recognizer identifies the store→reuse shape, rejects first-order
# ---------------------------------------------------------------------------
def test_recognizer_extracts_second_order_shape():
    recognized = _recognize_second_order_sqli(_SOURCE)
    assert recognized is not None
    assert recognized["store_field"] == "username"
    assert recognized["trigger_path"] == "home.php"
    assert recognized["store_method"] == "POST"


def test_recognizer_rejects_first_order_direct_concat():
    first_order = """<?php
    $id = $_GET['id'];
    $res = $db->query("select * from products where id='" . $id . "'");
    echo $res;
    """
    # no INSERT persistence + no DB-fetch reuse → not second-order
    assert _recognize_second_order_sqli(first_order) is None


def test_recognizer_rejects_store_without_deferred_reuse():
    store_only = """<?php
    $name = $_POST['username'];
    $db->query("insert into guests(name) values('$name')");
    echo "thanks for signing the guestbook";
    """
    # persists a field but never re-queries a DB-fetched value → not second-order
    assert _recognize_second_order_sqli(store_only) is None


# ---------------------------------------------------------------------------
# Unit: strategy is registered, reachable in the web order, extras-gated
# ---------------------------------------------------------------------------
def test_second_order_strategy_registered_and_extras_gated():
    from flaghunter.agents.pa_agent.chains.web import WEB_STRATEGY_ORDER

    assert "second_order_sqli" in WEB_STRATEGY_ORDER
    strategy = StrategyRegistry.build_default().get("second_order_sqli")
    assert strategy is not None
    assert strategy.chain_name == "sqli"

    gated_on = StrategyContext(
        target="http://ctf.local/register.php",
        page_features={},
        hint="",
        services=None,
        extras={"second_order_sqli_exploit_info": {"store_field": "username"}},
    )
    gated_off = StrategyContext(
        target="http://ctf.local/register.php",
        page_features={},
        hint="",
        services=None,
    )
    assert strategy.is_applicable(gated_on) is True
    assert strategy.is_applicable(gated_off) is False
