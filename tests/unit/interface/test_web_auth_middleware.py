"""A-07 — Web Console API requires a bearer token on remote/enforced binds.

Exercises the aiohttp auth middleware end-to-end via a real app instance:

  * loopback + no token → API is open (local dev unchanged);
  * token configured → /api/* demands a valid bearer token (401 otherwise),
    while the static SPA shell stays reachable so it can prompt for one;
  * a non-loopback bind with no token is fail-closed at bootstrap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from flaghunter.interface import web_server


def _minimal_app(host: str, auth_token) -> web.Application:
    """A tiny app that mounts only the auth middleware + a couple of routes.

    Avoids booting the full console (handlers, task store) — the middleware is
    what A-07 adds, so we test it in isolation against representative routes.
    """
    app = web.Application(
        middlewares=[web_server.make_auth_middleware(host, auth_token)]
    )

    async def api_status(_req):
        return web.json_response({"ok": True})

    async def index(_req):
        return web.Response(text="<html>console</html>", content_type="text/html")

    app.router.add_get("/api/status", api_status)
    app.router.add_get("/", index)
    return app


async def _client(aiohttp_or_app) -> TestClient:
    client = TestClient(TestServer(aiohttp_or_app))
    await client.start_server()
    return client


@pytest.mark.asyncio
async def test_loopback_no_token_is_open():
    client = await _client(_minimal_app("127.0.0.1", None))
    try:
        resp = await client.get("/api/status")
        assert resp.status == 200
        assert (await resp.json())["ok"] is True
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_token_configured_rejects_missing_credential():
    client = await _client(_minimal_app("127.0.0.1", "s3cret"))
    try:
        resp = await client.get("/api/status")
        assert resp.status == 401
        assert resp.headers.get("WWW-Authenticate") == "Bearer"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_token_configured_accepts_valid_bearer():
    client = await _client(_minimal_app("127.0.0.1", "s3cret"))
    try:
        resp = await client.get(
            "/api/status", headers={"Authorization": "Bearer s3cret"}
        )
        assert resp.status == 200
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_token_configured_accepts_header_and_query_channels():
    client = await _client(_minimal_app("127.0.0.1", "s3cret"))
    try:
        r1 = await client.get("/api/status", headers={"X-FlagHunter-Token": "s3cret"})
        assert r1.status == 200
        # EventSource fallback: token via query string.
        r2 = await client.get("/api/status?token=s3cret")
        assert r2.status == 200
        r3 = await client.get("/api/status?token=wrong")
        assert r3.status == 401
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_static_shell_stays_open_even_when_enforced():
    client = await _client(_minimal_app("0.0.0.0", "s3cret"))
    try:
        # Non-/api path is reachable so the SPA can load and prompt for a token.
        resp = await client.get("/")
        assert resp.status == 200
        # But the API is still locked down.
        assert (await client.get("/api/status")).status == 401
    finally:
        await client.close()


def test_non_loopback_without_token_is_fail_closed(monkeypatch):
    from flaghunter.config import remote_access as ra

    monkeypatch.delenv(ra.WEB_AUTH_TOKEN_ENV, raising=False)
    monkeypatch.delenv(ra.MCP_AUTH_TOKEN_ENV, raising=False)
    monkeypatch.delenv(ra.SHARED_AUTH_TOKEN_ENV, raising=False)

    # Refuses to start before binding — never reaches web.run_app.
    with pytest.raises(ra.RemoteAuthConfigError):
        web_server.run_web_server(host="0.0.0.0", port=0, project_root=Path("."))
