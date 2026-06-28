"""
api_spec_discovery — 发现并解析 Swagger / OpenAPI 规范文档(纯 Python httpx)。

许多应用会在固定路径暴露机器可读的 API 规范(/swagger.json、/openapi.json、
/v2/api-docs ...)。一旦拿到规范,整张 API 攻击面(endpoints + methods + 参数)
就直接暴露,远胜目录爆破猜测。本工具逐个探测常见规范路径,解析出 endpoint 清单。

JSON 规范始终解析;YAML 规范仅在 PyYAML 可用时尽力解析,否则诚实跳过。
纯 httpx 实现,不依赖外部二进制。
ATT&CK: T1595 (Active Scanning), T1593 (Search Open Websites/Domains)。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx

from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


_DEFAULT_PATHS: tuple[str, ...] = (
    "/swagger.json",
    "/openapi.json",
    "/v2/api-docs",
    "/v3/api-docs",
    "/api-docs",
    "/api/swagger.json",
    "/api/openapi.json",
    "/swagger/v1/swagger.json",
    "/swagger/v1/swagger.yaml",
    "/openapi.yaml",
    "/swagger.yaml",
)


async def _send(url: str, *, timeout: int = 10) -> dict[str, Any]:
    """Fetch a URL; module-level so tests can monkeypatch it."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
        resp = await client.get(url)
    return {
        "status": resp.status_code,
        "body": resp.text or "",
        "content_type": resp.headers.get("content-type", ""),
    }


def _parse_spec(body: str, content_type: str) -> dict[str, Any] | None:
    """Parse a body as an OpenAPI/Swagger spec. Returns None if not a spec."""
    doc: Any = None
    text = body.strip()
    if not text:
        return None
    # Try JSON first (covers .json and most api-docs endpoints).
    try:
        doc = json.loads(text)
    except (ValueError, TypeError):
        doc = None
    # YAML best-effort, only if it looks like yaml and PyYAML is present.
    if doc is None:
        try:
            import yaml  # type: ignore

            doc = yaml.safe_load(text)
        except Exception:
            return None
    if not isinstance(doc, dict):
        return None
    if "swagger" not in doc and "openapi" not in doc and "paths" not in doc:
        return None
    return doc


def _extract_endpoints(doc: dict[str, Any]) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    paths = doc.get("paths")
    if not isinstance(paths, dict):
        return endpoints
    http_methods = {"get", "post", "put", "delete", "patch", "head", "options"}
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        methods = sorted(m.upper() for m in item if m.lower() in http_methods)
        params: list[str] = []
        for m in item.values():
            if isinstance(m, dict):
                for p in m.get("parameters", []) or []:
                    if isinstance(p, dict) and p.get("name"):
                        params.append(str(p["name"]))
        for p in item.get("parameters", []) or []:
            if isinstance(p, dict) and p.get("name"):
                params.append(str(p["name"]))
        endpoints.append(
            {
                "path": path,
                "methods": methods,
                "params": sorted(set(params)),
            }
        )
    return endpoints


async def _discover(base_url: str, paths: list[str], timeout: int) -> dict[str, Any]:
    base = base_url.rstrip("/")
    specs: list[dict[str, Any]] = []
    for rel in paths:
        url = base + (rel if rel.startswith("/") else "/" + rel)
        try:
            resp = await _send(url, timeout=timeout)
        except Exception:
            continue
        if resp.get("status") != 200:
            continue
        doc = _parse_spec(resp.get("body", ""), resp.get("content_type", ""))
        if doc is None:
            continue
        info = doc.get("info", {}) if isinstance(doc.get("info"), dict) else {}
        endpoints = _extract_endpoints(doc)
        specs.append(
            {
                "url": url,
                "version": doc.get("openapi") or doc.get("swagger") or "unknown",
                "title": info.get("title", ""),
                "endpoint_count": len(endpoints),
                "endpoints": endpoints,
            }
        )

    total_endpoints = sum(s["endpoint_count"] for s in specs)
    return {
        "base_url": base_url,
        "tested": len(paths),
        "specs_found": len(specs),
        "total_endpoints": total_endpoints,
        "specs": specs,
    }


@register_tool(
    name="api_spec_discovery",
    description=(
        "Discover and parse Swagger/OpenAPI specs at common paths "
        "(/swagger.json, /openapi.json, /v2/api-docs, ...). Enumerates the full "
        "API attack surface: endpoints, HTTP methods and parameters."
    ),
    schema=ToolSchema(
        properties={
            "base_url": {"type": "string", "description": "Base URL, e.g. http://host:port"},
            "paths": {"type": "array", "description": "Optional override list of spec paths to probe"},
            "timeout": {"type": "integer", "description": "Per-request timeout (s)", "default": 10},
        },
        required=["base_url"],
    ),
    category="recon",
    technique_ids=["T1595", "T1593"],
)
async def api_spec_discovery(arguments: dict, runtime: "Runtime") -> str:
    base_url = arguments.get("base_url")
    if not base_url:
        return "Error: base_url is required"
    raw_paths = arguments.get("paths")
    paths = [str(p) for p in raw_paths] if raw_paths else list(_DEFAULT_PATHS)
    timeout = int(arguments.get("timeout", 10))

    try:
        result = await _discover(base_url, paths, timeout)
    except Exception as exc:
        return json.dumps({"base_url": base_url, "error": str(exc), "specs": []}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)
