"""
vhost_discovery — 虚拟主机(vhost)爆破:对同一 IP 改 Host 头探测隐藏站点。

一台 Web 服务器常按 Host 头路由到多个虚拟主机(staging.、admin.、internal. ...)。
直接访问 IP 只能看到默认站点,而带不同 Host 头请求可能命中未公开的内部应用。
本工具先取默认/伪随机 Host 的基线,再用词表逐个替换 Host 头,通过响应
(状态码 / 长度 / <title>)与基线的差异判断有效 vhost。

纯 httpx 实现,不依赖外部 gobuster/ffuf 二进制。
ATT&CK: T1595.003 (Active Scanning: Wordlist Scanning), T1590 (Gather Victim Network Information)。
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


_DEFAULT_WORDLIST: tuple[str, ...] = (
    "www", "admin", "api", "dev", "staging", "stage", "test", "testing",
    "internal", "intranet", "portal", "dashboard", "beta", "demo", "uat",
    "app", "apps", "mail", "webmail", "vpn", "git", "gitlab", "jenkins",
    "ci", "registry", "docker", "kibana", "grafana", "prometheus", "backup",
    "old", "new", "secret", "private", "corp", "manage", "console", "monitor",
)

# Pseudo-random label used to fingerprint the "unknown vhost" baseline.
_BASELINE_LABEL = "fhvh-nonexistent-zzq"

_LEN_NOISE = 48
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


async def _send(url: str, host: str, *, timeout: int = 10) -> dict[str, Any]:
    """GET `url` with an overridden Host header; module-level for monkeypatching."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, verify=False) as client:
        resp = await client.get(url, headers={"Host": host})
    body = resp.text or ""
    return {"status": resp.status_code, "body": body, "length": len(body)}


def _title(body: str) -> str:
    m = _TITLE_RE.search(body or "")
    return (m.group(1).strip() if m else "")[:120]


def _base_host_and_url(target: str) -> tuple[str, str]:
    """Return (ip_or_host, url) from an IP, host, or full URL target."""
    if "://" in target:
        parsed = urlparse(target)
        return parsed.hostname or target, target
    return target, f"http://{target}"


def _differs(baseline: dict[str, Any], probe: dict[str, Any]) -> str | None:
    if probe.get("status") != baseline.get("status"):
        return "status-change"
    if abs(int(probe.get("length", 0)) - int(baseline.get("length", 0))) > _LEN_NOISE:
        return "length-change"
    if _title(probe.get("body", "")) != _title(baseline.get("body", "")):
        return "title-change"
    return None


async def _discover(target: str, base_domain: str, wordlist: list[str], timeout: int) -> dict[str, Any]:
    host_or_ip, url = _base_host_and_url(target)
    domain = base_domain.lstrip(".") if base_domain else host_or_ip

    baseline = await _send(url, f"{_BASELINE_LABEL}.{domain}", timeout=timeout)

    found: list[dict[str, Any]] = []
    for label in wordlist:
        vhost = f"{label}.{domain}"
        try:
            probe = await _send(url, vhost, timeout=timeout)
        except Exception:
            continue
        signal = _differs(baseline, probe)
        if signal:
            found.append(
                {
                    "vhost": vhost,
                    "signal": signal,
                    "status": probe.get("status"),
                    "length": probe.get("length"),
                    "title": _title(probe.get("body", "")),
                }
            )

    return {
        "target": target,
        "base_domain": domain,
        "tested": len(wordlist),
        "baseline_status": baseline.get("status"),
        "baseline_length": baseline.get("length"),
        "found": found,
        "total_found": len(found),
    }


@register_tool(
    name="vhost_discovery",
    description=(
        "Brute-force virtual hosts by sending wordlist Host headers to one IP and "
        "diffing responses (status/length/title) against an unknown-vhost baseline. "
        "Surfaces hidden internal sites (admin., staging., internal. ...)."
    ),
    schema=ToolSchema(
        properties={
            "target": {"type": "string", "description": "IP, host, or URL to probe"},
            "base_domain": {"type": "string", "description": "Domain to prepend labels to, e.g. example.com"},
            "wordlist": {"type": "array", "description": "Optional override list of subdomain labels"},
            "timeout": {"type": "integer", "description": "Per-request timeout (s)", "default": 10},
        },
        required=["target", "base_domain"],
    ),
    category="recon",
    technique_ids=["T1595.003", "T1590"],
)
async def vhost_discovery(arguments: dict, runtime: "Runtime") -> str:
    target = arguments.get("target")
    base_domain = arguments.get("base_domain")
    if not target:
        return "Error: target is required"
    if not base_domain:
        return "Error: base_domain is required"
    raw_wordlist = arguments.get("wordlist")
    wordlist = [str(w) for w in raw_wordlist] if raw_wordlist else list(_DEFAULT_WORDLIST)
    timeout = int(arguments.get("timeout", 10))

    try:
        result = await _discover(target, base_domain, wordlist, timeout)
    except Exception as exc:
        return json.dumps({"target": target, "error": str(exc), "found": []}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)
