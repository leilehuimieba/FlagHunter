"""Recon Bundle — 快速侦察批量工具

将多个侦察工具（httpx_probe、browser snapshot、dirscan）合并为一次调用，
减少 Agent loop 中侦察阶段的 iteration 消耗。

典型收益：原来 5-8 次工具调用 → 1 次 recon_bundle 调用。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ...tools.registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


@register_tool(
    name="recon_bundle",
    description=(
        "Fast reconnaissance bundle: runs httpx_probe + browser snapshot + dirscan "
        "in a single call and returns a unified summary. Use this instead of calling "
        "each recon tool separately to save iterations."
    ),
    schema=ToolSchema(
        properties={
            "target": {
                "type": "string",
                "description": "Target URL to recon, e.g. http://target.com:81",
            },
            "skip_dirscan": {
                "type": "boolean",
                "description": "Skip directory enumeration if true (default: false)",
                "default": False,
            },
            "skip_browser": {
                "type": "boolean",
                "description": "Skip browser snapshot if true (default: false)",
                "default": False,
            },
        },
        required=["target"],
    ),
    category="recon",
)
async def recon_bundle(arguments: dict, runtime: "Runtime") -> str:
    target = arguments.get("target", "").strip()
    skip_dirscan = arguments.get("skip_dirscan", False)
    skip_browser = arguments.get("skip_browser", False)

    if not target:
        return json.dumps({"error": "target is required"}, ensure_ascii=False)

    # Ensure URL has scheme
    url = target
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"

    results: dict = {
        "target": target,
        "url": url,
        "httpx": {},
        "browser": {},
        "dirscan": {},
    }

    # ── 1. httpx_probe ──
    try:
        from ..httpx_probe import _run_httpx, _build_base_args
        httpx_data = _run_httpx([url], _build_base_args())
        if httpx_data:
            results["httpx"] = httpx_data[0] if httpx_data else {}
        else:
            results["httpx"] = {"status": "httpx not installed"}
    except Exception as e:
        results["httpx"] = {"error": str(e)}

    # ── 2. browser snapshot ──
    if not skip_browser and hasattr(runtime, "browser_action"):
        try:
            nav = await runtime.browser_action("navigate", url=url, timeout=10)
            content = await runtime.browser_action("get_content", timeout=10)
            forms = await runtime.browser_action("get_forms", timeout=10)
            links = await runtime.browser_action("get_links", timeout=10)
            cookies = await runtime.browser_action("get_cookies", timeout=10)

            results["browser"] = {
                "navigated": isinstance(nav, dict) and not nav.get("error"),
                "title": nav.get("title", "") if isinstance(nav, dict) else "",
                "content_preview": (
                    (content.get("content", "")[:2000] + "...")
                    if isinstance(content, dict) and len(content.get("content", "")) > 2000
                    else (content.get("content", "") if isinstance(content, dict) else "")
                ),
                "forms": forms.get("forms", []) if isinstance(forms, dict) else [],
                "links_count": len(links.get("links", [])) if isinstance(links, dict) else 0,
                "cookies": cookies.get("cookie_string", "") if isinstance(cookies, dict) else "",
            }
        except Exception as e:
            results["browser"] = {"error": str(e)}
    else:
        results["browser"] = {"skipped": True}

    # ── 3. dirscan ──
    if not skip_dirscan:
        try:
            from ..dirscan import run_dirscan
            dirscan_result = await run_dirscan(url=url, runtime=runtime)
            results["dirscan"] = {
                "total": dirscan_result.get("total", 0),
                "found": dirscan_result.get("found", []),
                "sample": dirscan_result.get("found", [])[:20],
            }
        except Exception as e:
            results["dirscan"] = {"error": str(e)}
    else:
        results["dirscan"] = {"skipped": True}

    return json.dumps(results, ensure_ascii=False, indent=2)
