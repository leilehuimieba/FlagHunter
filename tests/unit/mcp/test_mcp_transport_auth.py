"""A-08 — MCP network transport requires a bearer token when enforced (F-04).

The streamable-HTTP transport gated /mcp only on ``Mcp-Session-Id`` (a
correlation value, not an identity), and the SSE server bound 0.0.0.0 by
default. These tests prove the new middleware enforces a bearer token on every
/mcp request (including ``initialize``) when enforcement is on, and stays a
pass-through for the default loopback/no-token case.
"""

from __future__ import annotations

import json

import pytest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from flaghunter.mcp.server import mcp_transport_streamable_http as tr


class _StubRouter:
    """Minimal MCPRouter stand-in: echoes a result for any request with an id."""

    async def handle(self, msg):
        if isinstance(msg, dict) and "id" in msg:
            return {"jsonrpc": "2.0", "id": msg["id"], "result": {"ok": True}}
        return None


async def _client(app: web.Application) -> TestClient:
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


def _init_body():
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}


@pytest.mark.asyncio
async def test_unenforced_transport_is_pass_through():
    app = tr.create_streamable_http_app(_StubRouter())
    client = await _client(app)
    try:
        resp = await client.post("/mcp", json=_init_body())
        assert resp.status == 200
        assert resp.headers.get("Mcp-Session-Id")  # init assigns a session
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_enforced_transport_rejects_initialize_without_token():
    app = tr.create_streamable_http_app(
        _StubRouter(), auth_token="s3cret", enforce_auth=True
    )
    client = await _client(app)
    try:
        resp = await client.post("/mcp", json=_init_body())
        assert resp.status == 401
        assert resp.headers.get("WWW-Authenticate") == "Bearer"
        payload = json.loads(await resp.text())
        assert payload["error"]["code"] == -32001
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_enforced_transport_accepts_valid_bearer():
    app = tr.create_streamable_http_app(
        _StubRouter(), auth_token="s3cret", enforce_auth=True
    )
    client = await _client(app)
    try:
        resp = await client.post(
            "/mcp", json=_init_body(), headers={"Authorization": "Bearer s3cret"}
        )
        assert resp.status == 200
        assert resp.headers.get("Mcp-Session-Id")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_session_id_is_not_an_identity():
    # A valid session-id-shaped header does NOT authorize when a token is required.
    app = tr.create_streamable_http_app(
        _StubRouter(), auth_token="s3cret", enforce_auth=True
    )
    client = await _client(app)
    try:
        resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={"Mcp-Session-Id": "11111111-2222-3333-4444-555555555555"},
        )
        assert resp.status == 401
    finally:
        await client.close()


def test_mcp_sse_default_bind_is_loopback(monkeypatch):
    # F-04: the SSE server must default to loopback, not 0.0.0.0.
    import importlib
    import sys

    main_module = importlib.import_module("flaghunter.interface.main")

    monkeypatch.setattr(sys, "argv", ["flaghunter", "mcp_server", "--type", "sse"])
    _parser, args = main_module.parse_arguments()
    assert args.host == "127.0.0.1"


@pytest.mark.asyncio
async def test_enforced_get_and_delete_also_gated():
    app = tr.create_streamable_http_app(
        _StubRouter(), auth_token="s3cret", enforce_auth=True
    )
    client = await _client(app)
    try:
        assert (await client.get("/mcp")).status == 401
        assert (await client.delete("/mcp")).status == 401
    finally:
        await client.close()
