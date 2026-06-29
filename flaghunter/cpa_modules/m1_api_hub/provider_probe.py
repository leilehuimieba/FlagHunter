"""Provider 池存活探针 + 报告渲染(provider 管理需求 #5/#6)。

#5 反馈"哪个 API 不可用":列出每个 provider 的 LIVE/DOWN + 原因。
#6 手动刷新存活:对每个 enabled provider 发一次最小探针请求(带其 UA headers)。

只读:不改 ProviderManager 状态,不依赖运行中的 FailoverMonitor;独立加载 .env 的
CPA_PROVIDER_* 池即可在 CLI 里跑(``flaghunter providers --refresh``)。
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from .config_schema import ProviderConfig, load_all_providers_from_env


def _base_row(p: ProviderConfig) -> Dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "model": p.model,
        "api_base": p.api_base,
        "priority": p.priority,
        "tags": list(p.tags or []),
        "enabled": bool(p.enabled),
    }


def list_providers() -> List[Dict[str, Any]]:
    """列出池中所有 provider(按 priority 升序),不做存活探针。"""
    providers = sorted(load_all_providers_from_env(), key=lambda c: c.priority)
    return [_base_row(p) for p in providers]


async def _probe_one(p: ProviderConfig, *, timeout: int) -> Dict[str, Any]:
    row = _base_row(p)
    if not p.enabled:
        return {**row, "live": None, "detail": "disabled"}
    try:
        import litellm

        await litellm.acompletion(
            model=p.model,
            api_base=p.api_base,
            api_key=p.api_key,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=16,
            extra_headers=dict(p.headers) if p.headers else None,
            timeout=timeout,
        )
        return {**row, "live": True, "detail": "ok"}
    except Exception as exc:  # noqa: BLE001 — 探针把任何失败都记为 DOWN+原因
        return {**row, "live": False, "detail": f"{type(exc).__name__}: {str(exc)[:90]}"}


async def probe_providers(*, timeout: int = 15) -> List[Dict[str, Any]]:
    """对池中每个 provider 并发发一次最小探针,返回带 live/detail 的行(按 priority)。"""
    providers = sorted(load_all_providers_from_env(), key=lambda c: c.priority)
    rows = await asyncio.gather(*[_probe_one(p, timeout=timeout) for p in providers])
    return list(rows)


def format_providers_report(rows: List[Dict[str, Any]], *, refreshed: bool) -> str:
    """把 provider 行渲染成人读文本表。refreshed=True 时含 LIVE/DOWN 列。"""
    if not rows:
        return "(no providers configured — set CPA_PROVIDER_N_* in .env)"

    lines: List[str] = []
    title = "LLM Provider 池" + ("（已刷新存活）" if refreshed else "（配置，未探针；加 --refresh 测存活）")
    lines.append(title)
    lines.append("=" * len(title))

    def _status_cell(r: Dict[str, Any]) -> str:
        if not refreshed:
            return "enabled " if r["enabled"] else "disabled"
        live = r.get("live")
        if live is True:
            return "● LIVE  "
        if live is False:
            return "○ DOWN  "
        return "· (off) "

    for r in rows:
        head = f"  p{r['priority']:<2} {_status_cell(r)} {r['id']:<16} {r['model']}"
        lines.append(head)
        meta = f"        base={r['api_base']}  tags={','.join(r['tags']) or '-'}"
        lines.append(meta)
        if refreshed and r.get("live") is False:
            lines.append(f"        ✗ {r.get('detail')}")

    if refreshed:
        live_n = sum(1 for r in rows if r.get("live") is True)
        down = [r["id"] for r in rows if r.get("live") is False]
        lines.append("")
        lines.append(f"  存活 {live_n}/{sum(1 for r in rows if r['enabled'])} enabled" +
                     (f"；不可用: {', '.join(down)}" if down else "；全部可用"))
    return "\n".join(lines)
