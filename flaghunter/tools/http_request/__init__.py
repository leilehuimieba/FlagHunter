"""Minimal structured HTTP request tool for FlagHunter."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


def _normalize_headers(headers: Any) -> dict[str, str]:
    """Return a string-to-string header mapping."""
    if not isinstance(headers, dict):
        return {}
    return {str(k): str(v) for k, v in headers.items()}


def _format_http_result(method: str, url: str, result: dict) -> str:
    """Format structured HTTP output for agent consumption and flag scanning."""
    if "error" in result:
        return f"HTTP request error: {result['error']}"

    response_headers = result.get("headers") or {}
    if isinstance(response_headers, dict) and response_headers:
        header_block = "\n".join(
            f"{str(key)}: {str(value)}"
            for key, value in sorted(response_headers.items(), key=lambda item: item[0])
        )
    else:
        header_block = "(none)"

    body = result.get("body", "")
    if body is None:
        body = ""
    elif not isinstance(body, str):
        try:
            body = json.dumps(body, ensure_ascii=False, indent=2)
        except Exception:
            body = str(body)

    return (
        f"HTTP {method} {url}\n"
        f"Status Code: {result.get('status_code', 'unknown')}\n"
        f"Response Headers:\n{header_block}\n\n"
        f"Body:\n{body}"
    )


@register_tool(
    name="http_request",
    description=(
        "Send a minimal structured HTTP GET/POST request via the runtime proxy "
        "layer. Useful for /login, /visit, and cookie-backed /admin flows."
    ),
    schema=ToolSchema(
        properties={
            "method": {
                "type": "string",
                "enum": ["GET", "POST"],
                "description": "HTTP method to use",
            },
            "url": {
                "type": "string",
                "description": "Absolute target URL",
            },
            "headers": {
                "type": "object",
                "description": "Request headers, for example {'Cookie': 'sid=...'}",
            },
            "data": {
                "description": (
                    "Form/request body as an object or pre-encoded string. "
                    "Prefer this for application/x-www-form-urlencoded POSTs."
                ),
            },
            "form": {
                "description": "Alias of data for ergonomic form POSTs.",
            },
            "json": {
                "type": "object",
                "description": "JSON body object to serialize and send",
            },
            "files": {
                "type": "object",
                "description": (
                    "Multipart file mapping. Example: "
                    "{'photo': {'filename': 'a.txt', 'content': 'hello', 'content_type': 'text/plain'}} "
                    "or {'photo': {'path': '/tmp/a.txt'}}."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 30)",
                "default": 30,
            },
        },
        required=["method", "url"],
    ),
    category="web",
)
async def http_request(arguments: dict, runtime: "Runtime") -> str:
    """
    Send a minimal structured HTTP request.

    Args:
        arguments: Request arguments
        runtime: Runtime exposing proxy_action()

    Returns:
        Formatted response string
    """
    if runtime is None or not hasattr(runtime, "proxy_action"):
        return "HTTP request error: runtime does not support proxy_action()"

    method = str(arguments.get("method", "GET")).upper()
    if method not in {"GET", "POST"}:
        return f"HTTP request error: unsupported method '{method}'"

    url = str(arguments.get("url", "")).strip()
    if not url:
        return "HTTP request error: url is required"

    timeout = arguments.get("timeout", 30)
    headers = _normalize_headers(arguments.get("headers", {}))

    has_data = "data" in arguments
    has_form = "form" in arguments
    if has_data and has_form and arguments.get("data") != arguments.get("form"):
        return "HTTP request error: use either 'data' or 'form', not both"

    data = arguments.get("data")
    if has_form:
        data = arguments.get("form")

    json_body = arguments.get("json")
    files = arguments.get("files")
    if data is not None and json_body is not None:
        return "HTTP request error: use either 'data/form' or 'json', not both"
    if files is not None and json_body is not None:
        return "HTTP request error: use either 'files' or 'json', not both"

    result = await runtime.proxy_action(
        "request",
        method=method,
        url=url,
        headers=headers,
        data=data,
        files=files,
        json=json_body,
        timeout=timeout,
    )

    return _format_http_result(method, url, result)
