#!/usr/bin/env python3
"""Small stdio JSON-RPC bridge for HexStrike HTTP API.

This adapter implements the minimal MCP stdio JSON-RPC surface
expected by `pentestagent`'s `StdioTransport`:

- Responds to `initialize` with a simple result
- Accepts `notifications/initialized` (notification)
- Implements `tools/list` returning one proxy tool: `http_api`
- Implements `tools/call` for the `http_api` tool and forwards
  requests to the HexStrike HTTP API (configured via env var
  `HEXSTRIKE_SERVER`, default `http://127.0.0.1:8888`).

Usage (mcp_servers.json):
  {
    "mcpServers": {
      "hexstrike-local": {
        "command": "python3",
        "args": ["-u", "third_party/hexstrike/hexstrike_stdio_adapter.py"],
        "description": "StdIO adapter bridge to HexStrike HTTP API"
      }
    }
  }
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

try:
    import requests
except Exception:
    requests = None


BASE = os.environ.get("HEXSTRIKE_SERVER", "http://127.0.0.1:8888").rstrip("/")


def send_response(req_id: Any, result: Any = None, error: Any = None) -> None:
    resp: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        resp["error"] = {"code": -32000, "message": str(error)}
    else:
        resp["result"] = result if result is not None else {}
    print(json.dumps(resp, separators=(",", ":")), flush=True)


def handle_tools_list(req_id: Any) -> None:
    tools = [{"name": "http_api", "description": "Proxy to HexStrike HTTP API"}]
    send_response(req_id, {"tools": tools})


def forward_http(path: str, method: str = "POST", params: Dict[str, Any] | None = None, body: Any | None = None) -> Any:
    if requests is None:
        raise RuntimeError("requests library is not available in adapter process")
    url = path if path.startswith("http") else BASE + (path if path.startswith("/") else "/" + path)
    method = (method or "POST").upper()
    if method == "GET":
        r = requests.get(url, params=params or {}, timeout=60)
    else:
        r = requests.post(url, json=body or {}, params=params or {}, timeout=300)
    try:
        return r.json()
    except Exception:
        return r.text


def handle_tools_call(req: Dict[str, Any]) -> None:
    req_id = req.get("id")
    params = req.get("params", {}) or {}
    name = params.get("name")
    arguments = params.get("arguments") or {}

    if name != "http_api":
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
        content = forward_http(path, method=method, params=qparams, body=body)
        # Manager expects: result -> {"content": ...}
        send_response(req_id, {"content": content})
    except Exception as e:
        send_response(req_id, error=str(e))


def main() -> None:
    # Read newline-delimited JSON-RPC messages from stdin.
    # Keep process alive until stdin is closed.
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
            # ignore invalid json
            continue

        method = req.get("method")
        # Notifications have no id
        req_id = req.get("id")

        if method == "initialize":
            send_response(req_id, {"capabilities": {}})
        elif method == "notifications/initialized":
            # notification — no response
            continue
        elif method == "tools/list":
            handle_tools_list(req_id)
        elif method == "tools/call":
            handle_tools_call(req)
        else:
            # unknown method
            if req_id is not None:
                send_response(req_id, error=f"unsupported method '{method}'")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
