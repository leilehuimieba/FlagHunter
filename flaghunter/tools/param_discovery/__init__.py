"""
param_discovery — arjun 风格的 HTTP 隐藏参数挖掘(纯 Python httpx)。

对一个端点先取基线响应,再逐个注入候选参数名(带唯一 sentinel 值),
通过"sentinel 回显 / 状态码变化 / 响应体长度变化"判断该参数是否被服务端
真实消费,从而发现文档/表单里看不到的隐藏参数 —— 这些参数往往是注入链
(SQLi / 命令注入 / SSRF)真正够得着的入口。

纯 httpx 实现,不依赖外部 arjun/ffuf 二进制。结果仅供授权目标的侦察使用。
ATT&CK: T1595.003 (Active Scanning: Wordlist Scanning), T1592 (Gather Victim Host Info)。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


# Unique, unlikely-to-collide probe value so reflection is unambiguous.
_SENTINEL = "fhparam9z7q"

# Small built-in wordlist of commonly-consumed parameter names. Overridable via
# the `wordlist` argument. Kept intentionally compact for a deterministic probe.
_DEFAULT_WORDLIST: tuple[str, ...] = (
    "id", "page", "user", "username", "name", "q", "query", "search", "s",
    "file", "filename", "path", "dir", "url", "uri", "redirect", "next",
    "callback", "return", "lang", "locale", "view", "action", "cmd", "exec",
    "debug", "test", "admin", "token", "key", "api_key", "format", "type",
    "category", "cat", "sort", "order", "limit", "offset", "start", "count",
    "email", "password", "code", "ref", "source", "target", "host", "port",
    "data", "json", "xml", "template", "include", "module", "func", "method",
)

# Length delta (bytes) below which we treat two responses as "same size".
_LEN_NOISE = 24


async def _send(
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    """Issue a single HTTP request and return a normalised result dict.

    Isolated at module level so tests can monkeypatch it with canned responses
    instead of touching the network.
    """
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
        resp = await client.request(method, url, params=params, data=data)
    body = resp.text or ""
    return {"status": resp.status_code, "body": body, "length": len(body)}


def _split_url(url: str) -> tuple[str, list[tuple[str, str]]]:
    parsed = urlparse(url)
    base = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, "", ""))
    existing = parse_qsl(parsed.query, keep_blank_values=True)
    return base, existing


def _build_get_url(base: str, existing: list[tuple[str, str]], name: str) -> str:
    pairs = list(existing) + [(name, _SENTINEL)]
    query = urlencode(pairs)
    return f"{base}?{query}" if query else base


def _classify(baseline: dict[str, Any], probe: dict[str, Any]) -> str | None:
    """Return the signal label for an interesting parameter, or None."""
    if _SENTINEL in probe.get("body", ""):
        return "reflected"
    if probe.get("status") != baseline.get("status"):
        return "status-change"
    if abs(int(probe.get("length", 0)) - int(baseline.get("length", 0))) > _LEN_NOISE:
        return "length-change"
    return None


async def _discover(
    url: str,
    method: str,
    wordlist: list[str],
    timeout: int,
) -> dict[str, Any]:
    method = (method or "get").upper()
    base, existing = _split_url(url)

    if method == "POST":
        baseline = await _send("POST", base, data=dict(existing), timeout=timeout)
    else:
        baseline_url = f"{base}?{urlencode(existing)}" if existing else base
        baseline = await _send("GET", baseline_url, timeout=timeout)

    found: list[dict[str, Any]] = []
    for name in wordlist:
        try:
            if method == "POST":
                payload = dict(existing)
                payload[name] = _SENTINEL
                probe = await _send("POST", base, data=payload, timeout=timeout)
            else:
                probe = await _send("GET", _build_get_url(base, existing, name), timeout=timeout)
        except Exception:
            continue
        signal = _classify(baseline, probe)
        if signal:
            found.append(
                {
                    "param": name,
                    "signal": signal,
                    "status": probe.get("status"),
                    "length": probe.get("length"),
                }
            )

    return {
        "url": url,
        "method": method,
        "tested": len(wordlist),
        "baseline_status": baseline.get("status"),
        "baseline_length": baseline.get("length"),
        "found": found,
        "total_found": len(found),
    }


@register_tool(
    name="param_discovery",
    description=(
        "Discover hidden HTTP parameters (arjun-style) by probing a wordlist of "
        "candidate names and detecting reflection, status or response-length changes. "
        "Surfaces injection-reachable inputs not visible in forms/docs."
    ),
    schema=ToolSchema(
        properties={
            "url": {"type": "string", "description": "Target URL (may include an existing query string)"},
            "method": {"type": "string", "description": "HTTP method: get or post", "default": "get"},
            "wordlist": {"type": "array", "description": "Optional override list of parameter names"},
            "timeout": {"type": "integer", "description": "Per-request timeout (s)", "default": 10},
        },
        required=["url"],
    ),
    category="recon",
    technique_ids=["T1595.003", "T1592"],
)
async def param_discovery(arguments: dict, runtime: "Runtime") -> str:
    url = arguments.get("url")
    if not url:
        return "Error: url is required"
    method = arguments.get("method", "get")
    raw_wordlist = arguments.get("wordlist")
    wordlist = [str(w) for w in raw_wordlist] if raw_wordlist else list(_DEFAULT_WORDLIST)
    timeout = int(arguments.get("timeout", 10))

    try:
        result = await _discover(url, method, wordlist, timeout)
    except Exception as exc:  # network/DNS/etc — report honestly
        return json.dumps({"url": url, "error": str(exc), "found": []}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)
