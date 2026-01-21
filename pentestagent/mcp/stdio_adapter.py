#!/usr/bin/env python3
"""Generic stdio JSON-RPC adapter bridge to an HTTP API.

Configure via environment variables:
- `STDIO_TARGET` (default: "http://127.0.0.1:8888")
- `STDIO_TOOLS` (JSON list of tool descriptors, default: `[{"name":"http_api","description":"Generic HTTP proxy"}]`)

The adapter implements the minimal MCP/stdio surface required by
`pentestagent`'s `StdioTransport`:
- handle `initialize` and `notifications/initialized`
- respond to `tools/list`
- handle `tools/call` and forward to HTTP endpoints

`tools/call` arguments format (generic):
  {"path": "/api/foo", "method": "POST", "params": {...}, "body": {...} }

This file is intentionally small and dependency-light; it uses `requests`
when available and returns response JSON or text.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

try:
    import requests
except Exception:
    requests = None


TARGET = os.environ.get("STDIO_TARGET", "http://127.0.0.1:8888").rstrip("/")
_tools_env = os.environ.get("STDIO_TOOLS")
if _tools_env:
    try:
        TOOLS: List[Dict[str, str]] = json.loads(_tools_env)
    except Exception:
        TOOLS = [{"name": "http_api", "description": "Generic HTTP proxy"}]
else:
    TOOLS = [{"name": "http_api", "description": "Generic HTTP proxy"}]


def _send(resp: Dict[str, Any]) -> None:
    print(json.dumps(resp, separators=(",", ":")), flush=True)


def send_response(req_id: Any, result: Any = None, error: Any = None) -> None:
    resp: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        resp["error"] = {"code": -32000, "message": str(error)}
    else:
        resp["result"] = result if result is not None else {}
    _send(resp)


def handle_tools_list(req_id: Any) -> None:
    send_response(req_id, {"tools": TOOLS})


def _http_forward(path: str, method: str = "POST", params: Dict[str, Any] | None = None, body: Any | None = None) -> Any:
    if requests is None:
        raise RuntimeError("`requests` not installed in adapter process")
    url = path if path.startswith("http") else TARGET + (path if path.startswith("/") else "/" + path)
    method = (method or "POST").upper()
    if method == "GET":
        r = requests.get(url, params=params or {}, timeout=60)
    else:
        r = requests.request(method, url, json=body or {}, params=params or {}, timeout=300)
    try:
        return r.json()
    except Exception:
        return r.text


def handle_tools_call(req: Dict[str, Any]) -> None:
    req_id = req.get("id")
    params = req.get("params", {}) or {}
    name = params.get("name")
    arguments = params.get("arguments") or {}

    # Validate tool
    if not any(t.get("name") == name for t in TOOLS):
        send_response(req_id, error=f"unknown tool '{name}'")
        return

    path = arguments.get("path")
    if not path:
        send_response(req_id, error="missing 'path' in arguments")
        return

    method = arguments.get("method", "POST")
    body = arguments.get("body")
    qparams = arguments.get("params")

    try:
        content = _http_forward(path, method=method, params=qparams, body=body)
        send_response(req_id, {"content": content})
    except Exception as e:
        send_response(req_id, error=str(e))


def main() -> None:
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        method = req.get("method")
        req_id = req.get("id")

        if method == "initialize":
            send_response(req_id, {"capabilities": {}})
        elif method == "notifications/initialized":
            # ignore notification
            continue
        elif method == "tools/list":
            handle_tools_list(req_id)
        elif method == "tools/call":
            handle_tools_call(req)
        else:
            if req_id is not None:
                send_response(req_id, error=f"unsupported method '{method}'")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
