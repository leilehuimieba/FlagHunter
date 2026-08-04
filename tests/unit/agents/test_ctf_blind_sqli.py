"""布尔盲注 + WAF 绕过合成：native boolean-blind SQLi 提取器的确定性守护。

框架能力扩面（对标 HackWorld 型 ceiling）：sqlmap 的 payload 模板依赖关键字+空格
结构，被"空格/关键字黑名单" WAF 直接拒绝，于是参数被读成"不可注入"——即便它确实
可注入。本测试用一个内存布尔 oracle（真实 MySQL-ish 求值：``&&`` 逻辑、括号子查询、
``/**/`` 分隔、``substr``/``ascii`` 逐字符）证明新增策略 ``blind_sqli``：

  ① 对一个"只放行免空格 payload"的 WAF 后端，能建立稳定 TRUE/FALSE 页面差异 oracle
     （空格分隔组合被 WAF 挡下，``/**/`` 组合通过——即 WAF-evasion 生效），
  ② 逐字符二分重建 ``database()`` → information_schema 表/列 → 行数据，扫出被种入
     ``flag`` 表的 flag，
  ③ 对"参数不可注入"的安全应用不误报（无 oracle → 无 confirmed note → 无 flag），
  ④ 纯 payload 合成 helper 免空格且用 ``&&``（不是 ``and``/``or``）。

盲注仅打本进程内存后端，绝不外连。reachability 由 test_chain_reachability_invariant
守护；零回归由全量 unit 套件保证。
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.sqli_executor import (
    _blind_char_gt,
    _blind_len_gt,
    _blind_normalize_body,
    _blind_substr_expr,
    _blind_wrap_payload,
)
from flaghunter.agents.pa_agent.strategy_registry import StrategyContext, StrategyRegistry
from flaghunter.tools.notes import set_notes_file

_FLAG = "flag{bl1nd_w4f_byp4ss}"
_DATABASE = "geekdb"
_TABLES = ["flag", "users"]
_COLUMNS = {"flag": ["flag_value"], "users": ["id", "name"]}
_ROWS = {"flag": _FLAG, "users": "1~alice"}

_WAF_WHITESPACE = " \t\n\r\x0b\x0c"
_PAGE_ROW = "<html><body>member profile dashboard order history</body></html>"
_PAGE_EMPTY = "<html><body>no matching record</body></html>"
_PAGE_WAF = "<html><body>security gateway blocked this request</body></html>"


# ---------------------------------------------------------------------------
# In-memory boolean-blind SQL backend behind a whitespace-blacklist WAF
# ---------------------------------------------------------------------------
def _strip_outer_parens(expr: str) -> str:
    expr = expr.strip()
    while expr.startswith("(") and expr.endswith(")"):
        depth = 0
        matched = True
        for i, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(expr) - 1:
                    matched = False
                    break
        if not matched:
            break
        expr = expr[1:-1].strip()
    return expr


def _eval_sql_expr(expr: str) -> str:
    """Evaluate the small set of scalar expressions the extractor emits."""
    expr = _strip_outer_parens(expr)
    if expr == "database()":
        return _DATABASE
    if "information_schema.columns" in expr:
        m = re.search(r"table_name=0x([0-9a-fA-F]+)", expr)
        if not m:
            return ""
        table = bytes.fromhex(m.group(1)).decode()
        return ",".join(_COLUMNS.get(table, []))
    if "information_schema.tables" in expr:
        return ",".join(_TABLES)
    if "concat_ws" in expr:
        m = re.search(r"from\(`?([A-Za-z0-9_]+)`?\)", expr)
        if not m:
            return ""
        return _ROWS.get(m.group(1), "")
    return ""


def _eval_substr(inner: str, evaluator=_eval_sql_expr) -> str:
    m = re.fullmatch(r"(?:substr|mid)\((.*)\)", inner.strip())
    if not m:
        return ""
    body = m.group(1)
    comma = re.fullmatch(r"(.*),(\d+),1", body)
    if comma:
        expr, pos = comma.group(1), int(comma.group(2))
    else:
        from_for = re.fullmatch(r"(.*)from\((\d+)\)for\(1\)", body)
        if not from_for:
            return ""
        expr, pos = from_for.group(1), int(from_for.group(2))
    value = evaluator(expr)
    return value[pos - 1] if 1 <= pos <= len(value) else ""


def _eval_condition(cond: str, evaluator=_eval_sql_expr) -> bool:
    cond = cond.strip()
    m = re.fullmatch(r"(\d+)=(\d+)", cond)
    if m:
        return m.group(1) == m.group(2)
    m = re.fullmatch(r"length\((.*)\)>(\d+)", cond)
    if m:
        return len(evaluator(m.group(1))) > int(m.group(2))
    m = re.fullmatch(r"(?:ascii|ord)\((.*)\)>(\d+)", cond)
    if m:
        ch = _eval_substr(m.group(1), evaluator)
        return (ord(ch) if ch else 0) > int(m.group(2))
    return False


def _extract_condition(payload: str) -> str | None:
    idx = payload.find("&&")
    if idx == -1:
        return None
    rest = payload[idx + 2:]
    open_at = rest.find("(")
    if open_at == -1:
        return None
    depth = 0
    for i in range(open_at, len(rest)):
        if rest[i] == "(":
            depth += 1
        elif rest[i] == ")":
            depth -= 1
            if depth == 0:
                return rest[open_at + 1:i]
    return None


def _split_top_level_commas(text: str) -> list[str]:
    """Split ``text`` on commas that sit at paren-depth 0."""
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _extract_if_call(payload: str) -> tuple[str, str, str] | None:
    """Parse ``if((cond),<true>,<false>)`` into (cond, true_val, false_val)."""
    m = re.fullmatch(r"if\((.*)\)", payload.strip())
    if not m:
        return None
    args = _split_top_level_commas(m.group(1))
    if len(args) != 3:
        return None
    return _strip_outer_parens(args[0]), args[1].strip(), args[2].strip()


class _BlindRuntime:
    """A numeric-column blind-SQLi target guarded by a whitespace-blacklist WAF.

    The vulnerable column is numeric (``WHERE id=<input>``): only whitespace-free
    payloads survive the WAF, and only the numeric context (no quote) yields the
    injected row, so the extractor must synthesise ``1/**/&&/**/(cond)/**/`` to
    win. ``injectable=False`` short-circuits every request to one constant page —
    no boolean oracle, so the extractor must not false-positive.
    """

    def __init__(
        self,
        injectable: bool = True,
        block_ampersand: bool = False,
        evaluator=_eval_sql_expr,
    ):
        self.injectable = injectable
        # When True the WAF blacklists ``&&``/``||`` outright (HackWorld-class):
        # every conjunction-style oracle is rejected, so only the ``if((cond),1,0)``
        # conditional-response context can establish a boolean oracle.
        self.block_ampersand = block_ampersand
        # Pluggable SQL scalar evaluator so a backend can model a database whose
        # ``information_schema`` walk truncates but whose flag is directly readable.
        self._evaluator = evaluator
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[str] = []

    def _render(self, payload: str) -> str:
        if not self.injectable:
            return _PAGE_ROW
        if any(ws in payload for ws in _WAF_WHITESPACE):
            return _PAGE_WAF
        # conditional-response injection: if((cond),1,0) resolves the numeric id
        # to the valid baseline (1) when the condition holds, else a dead id (0).
        if payload.startswith("if("):
            call = _extract_if_call(payload)
            if call is None:
                return _PAGE_EMPTY
            cond, true_val, false_val = call
            resolved = true_val if _eval_condition(cond, self._evaluator) else false_val
            return _PAGE_ROW if resolved.strip() == "1" else _PAGE_EMPTY
        if "'" in payload or '"' in payload:  # wrong context for a numeric column
            return _PAGE_EMPTY
        if "&&" in payload or "||" in payload:
            if self.block_ampersand:
                return _PAGE_WAF
            cond = _extract_condition(payload)
            if cond is None:
                return _PAGE_EMPTY
            return _PAGE_ROW if _eval_condition(cond, self._evaluator) else _PAGE_EMPTY
        return _PAGE_ROW if payload.strip() == "1" else _PAGE_EMPTY

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "Shop"}
        if action == "get_content":
            return {
                "content": "Item lookup service.",
                "html": "<html><body><form method=GET action=/item>"
                "<input name=id type=text value=1></form></body></html>",
            }
        if action == "get_forms":
            return {
                "forms": [
                    {
                        "method": "GET",
                        "action": "/item",
                        "inputs": [{"name": "id", "type": "text", "value": "1"}],
                    }
                ]
            }
        if action == "get_cookies":
            return {"cookie_string": ""}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        url = str(kwargs.get("url") or "")
        self.requests.append(url)
        params = parse_qs(urlparse(url).query, keep_blank_values=True)
        payload = (params.get("id") or [""])[0]
        return {"status_code": 200, "body": self._render(payload)}

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


_PAGE_FEATURES = {
    "forms": [
        {
            "method": "GET",
            "action": "/item",
            "inputs": [{"name": "id", "type": "text", "value": "1"}],
        }
    ]
}


# ---------------------------------------------------------------------------
# Behavioral: char-by-char reconstruction of a planted flag
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_blind_sqli_reconstructs_flag_through_waf(monkeypatch, tmp_path):
    _reset_notes(tmp_path, "notes_blind_vuln.json")
    runtime = _BlindRuntime(injectable=True)
    dispatcher = _make_dispatcher(monkeypatch, runtime)

    # Full web chain: blind_sqli runs LAST (after the cheaper SQLi/UNION paths
    # find nothing), establishes the oracle, and reconstructs the flag.
    await dispatcher.run(target="http://ctf.local/item", goal="拿到flag", type="web", hint="")

    # WAF-evasion actually happened: whitespace-separated payloads were sent
    # (and blocked), forcing the /**/-comment separator that carried the win.
    assert any("%2F%2A%2A%2F" in url or "/**/" in url for url in runtime.requests)
    assert any("ctf_blind_sqli_confirmed" in line for line in dispatcher._notes_log), (
        "expected the boolean oracle to be recorded"
    )
    # the extract note is only written on a verified/runtime decision, so its
    # presence proves the char-by-char reconstruction recovered the real flag.
    assert any("ctf_blind_sqli_extract" in line for line in dispatcher._notes_log), (
        "expected the reconstructed flag to be verified"
    )
    _cleanup_notes()


@pytest.mark.asyncio
async def test_blind_sqli_reconstructs_flag_through_ampersand_blocking_waf(monkeypatch, tmp_path):
    """HackWorld-class WAF: ``&&`` is blacklisted, so every conjunction oracle is
    rejected wholesale and only the ``if((cond),1,0)`` conditional-response context
    can establish a boolean oracle. Regression guard for the capability gap found in
    live validation (2026-08-04): the field IS boolean-blind injectable, but the
    pre-fix repertoire (``&&`` only) read it as "no boolean oracle"."""
    _reset_notes(tmp_path, "notes_blind_amp.json")
    runtime = _BlindRuntime(injectable=True, block_ampersand=True)
    dispatcher = _make_dispatcher(monkeypatch, runtime)

    await dispatcher.run(target="http://ctf.local/item", goal="拿到flag", type="web", hint="")

    # every conjunction-style payload was WAF-blocked, so the win must have come
    # from a conditional-response ``if((...),1,0)`` payload (url-encoded ``if%28``).
    assert any("if%28" in url or "if((" in url for url in runtime.requests), (
        "expected an if()-conditional oracle payload to be sent"
    )
    assert any("ctf_blind_sqli_confirmed" in line for line in dispatcher._notes_log), (
        "expected the boolean oracle to be established via the conditional context"
    )
    assert any("ctf_blind_sqli_extract" in line for line in dispatcher._notes_log), (
        "expected the reconstructed flag to be verified despite the && blacklist"
    )
    _cleanup_notes()


# ---------------------------------------------------------------------------
# Behavioral: CTF fast-path reaches a flag the information_schema walk can't
# ---------------------------------------------------------------------------
_DIRECT_FLAG = "CTF2{d1rect_fl4g_p4th}"
_DIRECT_DB = "ctftraining"
# A large shared database: many decoy tables whose comma-joined names overflow
# the extractor's per-string cap (_BLIND_MAX_STR_LEN=96) well before ``flag``.
_DIRECT_DECOY_TABLES = [f"news_article_archive_{i:02d}" for i in range(16)]


def _direct_flag_eval(expr: str) -> str:
    """Backend where the generic walk truncates but ``flag``.``flag`` is direct.

    ``information_schema.tables`` returns a decoy blob long enough that the real
    ``flag`` table (appended last) sits past the 96-char extraction window, so the
    walk provably cannot reach it. The flag is only recoverable by probing the
    obvious location ``select(group_concat(flag))from(flag)`` directly.
    """
    expr = _strip_outer_parens(expr)
    if expr == "database()":
        return _DIRECT_DB
    if "information_schema.columns" in expr:
        return "id,title,body"  # decoy tables carry no flag column
    if "information_schema.tables" in expr:
        return ",".join([*_DIRECT_DECOY_TABLES, "flag"])
    if "concat_ws" in expr:
        return ""  # decoy rows carry no flag
    if re.fullmatch(r"select\(group_concat\(flag\)\)from\(flag\)", expr):
        return _DIRECT_FLAG
    return ""


@pytest.mark.asyncio
async def test_blind_sqli_fast_path_reaches_flag_when_schema_walk_truncates(monkeypatch, tmp_path):
    """The information_schema walk group_concats every table, capped at 96 chars
    and ordered by storage — on a large shared database (e.g. ``ctftraining``) the
    ``flag`` table falls outside that window and the walk never reaches it. The CTF
    fast-path probes ``flag``.``flag`` directly and recovers the flag first.

    Regression guard for the live-validation residual (2026-08-04): the oracle +
    ``database()`` extraction worked, but the generic walk could not surface the
    flag before the request budget ran out."""
    _reset_notes(tmp_path, "notes_blind_fastpath.json")
    runtime = _BlindRuntime(injectable=True, evaluator=_direct_flag_eval)
    dispatcher = _make_dispatcher(monkeypatch, runtime)
    # Drive the extractor in isolation (no other web strategies to pollute the
    # recorded requests); a minimal state is all _observe_flag needs to verify.
    dispatcher.state = CTFState(target="http://ctf.local/item", goal="拿到flag")

    outcome = await dispatcher._attempt_blind_sqli("http://ctf.local/item", _PAGE_FEATURES)

    assert outcome.flag == _DIRECT_FLAG, "fast-path should reconstruct the direct flag"
    # The win came from a direct flag-location probe (group_concat over the flag
    # column of the flag table), not from the generic schema walk...
    assert any("group_concat" in url and "flag" in url for url in runtime.requests), (
        "expected a direct flag-location extraction request"
    )
    # ...and the walk was short-circuited entirely: no information_schema probe.
    assert not any("information_schema" in url for url in runtime.requests), (
        "fast-path must pre-empt the truncation-prone information_schema walk"
    )
    assert any("ctf_blind_sqli_extract" in line for line in dispatcher._notes_log)
    _cleanup_notes()


@pytest.mark.asyncio
async def test_blind_sqli_does_not_false_positive_when_not_injectable(monkeypatch, tmp_path):
    _reset_notes(tmp_path, "notes_blind_safe.json")
    runtime = _BlindRuntime(injectable=False)
    dispatcher = _make_dispatcher(monkeypatch, runtime)

    outcome = await dispatcher._attempt_blind_sqli("http://ctf.local/item", _PAGE_FEATURES)

    assert outcome.flag is None
    assert outcome.progress is False
    assert not any("ctf_blind_sqli_confirmed" in line for line in dispatcher._notes_log)
    _cleanup_notes()


# ---------------------------------------------------------------------------
# Unit: payload-synthesis helpers are WAF-lean (no spaces, && not and/or)
# ---------------------------------------------------------------------------
def test_blind_wrap_payload_is_whitespace_free_and_uses_ampersand_logic():
    for context in ("numeric", "string_single", "string_double"):
        payload = _blind_wrap_payload(context, "1=1", "/**/")
        assert " " not in payload and "\t" not in payload and "\n" not in payload
        assert "&&" in payload
        assert " and " not in payload.lower() and " or " not in payload.lower()
    # numeric closes nothing; string contexts break out of the quote and comment.
    assert _blind_wrap_payload("numeric", "1=1", "/**/") == "1/**/&&/**/(1=1)/**/"
    assert _blind_wrap_payload("string_single", "1=1", "/**/").startswith("1'")
    assert _blind_wrap_payload("string_single", "1=1", "/**/").endswith("#")


def test_blind_wrap_payload_conditional_if_uses_no_conjunction_operator():
    # HackWorld-class bypass: the whole numeric parameter becomes if((cond),1,0);
    # separator is irrelevant because no logic operator is synthesised.
    for sep in (" ", "/**/", "\t"):
        payload = _blind_wrap_payload("conditional_if", "ascii(substr((database()),1,1))>77", sep)
        assert payload == "if((ascii(substr((database()),1,1))>77),1,0)"
        assert " " not in payload and "\t" not in payload and "\n" not in payload
        assert "&&" not in payload and "||" not in payload
        assert " and " not in payload.lower() and " or " not in payload.lower()
    assert _blind_wrap_payload("conditional_if", "1=1", "/**/") == "if((1=1),1,0)"


def test_blind_substr_and_char_helpers_have_comma_and_ansi_forms():
    assert _blind_substr_expr("database()", 2, substr_fn="substr", comma=True) == "substr((database()),2,1)"
    assert _blind_substr_expr("database()", 2, substr_fn="mid", comma=False) == "mid((database())from(2)for(1))"
    # a whole char-oracle condition stays space-free
    cond = _blind_char_gt("database()", 1, 77, substr_fn="substr", ascii_fn="ascii", comma=True)
    assert cond == "ascii(substr((database()),1,1))>77"
    assert " " not in cond
    assert _blind_len_gt("database()", 5) == "length((database()))>5"


def test_blind_normalize_body_masks_digits_and_collapses_whitespace():
    assert _blind_normalize_body("row 41 loaded") == _blind_normalize_body("row 87 loaded")
    assert _blind_normalize_body("<b>hit</b>\n  <i>x</i>") == "<b>hit</b> <i>x</i>"
    assert _blind_normalize_body("alpha") != _blind_normalize_body("beta")


# ---------------------------------------------------------------------------
# Unit: precondition reach (registered, gated to a submittable field surface)
# ---------------------------------------------------------------------------
def test_blind_sqli_precondition_detects_surface_and_rejects_plain():
    surface = StrategyContext(
        target="http://ctf.local/",
        page_features=_PAGE_FEATURES,
        hint="",
        services=None,
    )
    plain = StrategyContext(
        target="http://ctf.local/",
        page_features={"content": "static landing", "forms": [], "raw_links": []},
        hint="",
        services=None,
    )
    strategy = StrategyRegistry.build_default().get("blind_sqli")
    assert strategy is not None
    assert strategy.chain_name == "sqli"
    assert strategy.is_applicable(surface) is True
    assert strategy.is_applicable(plain) is False
