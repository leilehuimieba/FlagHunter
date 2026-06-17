"""Web search tool for PentestAgent."""

import asyncio
import json
import os
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

import httpx

from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


async def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """Return raw Tavily search results for internal knowledge helpers."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY environment variable not set")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "include_answer": True,
                "include_raw_content": False,
                "max_results": max_results,
            },
        )
        response.raise_for_status()
        data = response.json()
    return data.get("results", []) or []


def _normalize_opencli_results(data: object) -> list[dict]:
    """Normalize OpenCLI JSON output into Tavily-like result dicts."""
    items = data if isinstance(data, list) else (data or {}).get("results", [])
    if not isinstance(items, list):
        return []

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("snippet") or item.get("description", ""),
            }
        )
    return normalized


def _get_opencli_executable() -> str:
    """Resolve the OpenCLI executable path reliably on Windows/POSIX."""
    for candidate in ("opencli.cmd", "opencli", "opencli.exe"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return "opencli"


def _list_connected_opencli_profiles() -> list[str]:
    """Return currently connected OpenCLI Browser Bridge profile ids."""
    try:
        result = subprocess.run(
            [_get_opencli_executable(), "profile", "list"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except Exception:
        return []

    if result.returncode != 0 or not result.stdout.strip():
        return []

    profiles: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if "— connected" not in stripped:
            continue
        match = re.match(r"^([A-Za-z0-9_-]+)\b", stripped)
        if match:
            profiles.append(match.group(1))
    return profiles


async def _run_opencli_search(provider: str, query: str, max_results: int) -> list[dict]:
    """Run one OpenCLI search provider and return normalized results."""
    cmd = [
        _get_opencli_executable(),
        provider,
        "search",
        query,
        "--limit",
        str(max_results),
        "-f", "json",   # opencli uses -f json, not --json
    ]

    configured_profile = os.getenv("OPENCLI_PROFILE", "").strip()
    candidate_profiles: list[str] = []
    if configured_profile:
        candidate_profiles.append(configured_profile)
    for profile in _list_connected_opencli_profiles():
        if profile not in candidate_profiles:
            candidate_profiles.append(profile)

    if not candidate_profiles:
        candidate_profiles = [""]

    for profile in candidate_profiles:
        env = os.environ.copy()
        if profile:
            env["OPENCLI_PROFILE"] = profile

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,   # fast-fail: Brave API is the real fallback
                env=env,
            )
        except Exception:
            continue

        if result.returncode != 0 or not result.stdout.strip():
            continue

        try:
            normalized = _normalize_opencli_results(json.loads(result.stdout))
            if normalized:
                return normalized
        except Exception:
            continue

    return []


async def _brave_search(query: str, max_results: int = 5) -> list[dict]:
    """Brave Search API — 有 key 时比 opencli 更快更稳定。"""
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if not api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"Accept": "application/json", "X-Subscription-Token": api_key},
                params={"q": query, "count": max_results, "search_lang": "zh-hans"},
            )
            resp.raise_for_status()
            data = resp.json()
        items = data.get("web", {}).get("results", [])
        return [
            {
                "title":   item.get("title", ""),
                "url":     item.get("url", ""),
                "content": item.get("description", ""),
            }
            for item in items
        ]
    except Exception:
        return []


async def _opencli_search(query: str, max_results: int = 5) -> list[dict]:
    """通过 opencli 搜索，无需 API key；优先 google，再回退 duckduckgo。"""
    results = await _run_opencli_search("google", query, max_results)
    if results:
        return results

    return await _run_opencli_search("duckduckgo", query, max_results)


@register_tool(
    name="web_search",
    description="Search the web for new security research, CVEs, exploits, bypass techniques, and documentation.",
    schema=ToolSchema(
        properties={
            "query": {
                "type": "string",
                "description": "Search query (be specific - include CVE numbers, tool names, versions)",
            }
        },
        required=["query"],
    ),
    category="research",
)
async def web_search(arguments: dict, runtime: "Runtime") -> str:
    """
    Search the web using Tavily API, then fall back to OpenCLI search.

    Args:
        arguments: Dictionary with 'query'
        runtime: The runtime environment

    Returns:
        Search results formatted for the LLM
    """
    query = arguments.get("query", "").strip()
    if not query:
        return "Error: No search query provided"

    # Priority: Tavily (richest) → Brave (fast, has key) → opencli (free, local browser)
    for _fn in (tavily_search, _brave_search, _opencli_search):
        try:
            results = await _fn(query, max_results=5)  # type: ignore[arg-type]
            if results:
                return _format_results(query, {"results": results})
        except Exception:
            continue

    return (
        "Error: All search backends failed.\n"
        "Configured: "
        + ("Tavily ✓ " if os.getenv("TAVILY_API_KEY") else "Tavily ✗ ")
        + ("Brave ✓ " if os.getenv("BRAVE_SEARCH_API_KEY") else "Brave ✗ ")
        + "opencli (always available if installed)"
    )


def _format_results(query: str, data: dict) -> str:
    """
    Format Tavily results for LLM consumption.

    Returns a lean format with summary + titles + URLs only.
    Content snippets are excluded to prevent LLM from regurgitating
    noisy web scrapes in its response.
    """
    parts = [f"Search: {query}\n"]

    # Include synthesized answer if available (this is the valuable part)
    if answer := data.get("answer"):
        parts.append(f"Summary:\n{answer}\n")

    # Include sources as title + URL only (no content snippets)
    results = data.get("results", [])
    if results:
        parts.append("Sources:")
        for i, result in enumerate(results, 1):
            title = result.get("title", "Untitled")
            url = result.get("url", "")
            parts.append(f"  [{i}] {title}")
            parts.append(f"      {url}")
    else:
        parts.append("No results found")

    return "\n".join(parts)
