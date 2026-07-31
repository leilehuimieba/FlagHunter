"""A-09 — Web Console CORS/Origin/CSRF middleware (F-05).

Exercises ``make_cors_middleware`` end-to-end via a real app instance:

  * a wildcard ``Access-Control-Allow-Origin: *`` is never emitted;
  * a trusted (loopback / allowlisted) Origin is echoed back, with credentials;
  * an untrusted Origin gets no CORS grant and cannot read cross-origin;
  * a state-changing request from an untrusted Origin is refused (403 CSRF gate),
    while a missing Origin (non-browser client) and safe methods pass.
"""

from __future__ import annotations

import pytest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from flaghunter.interface import web_server


def _cors_app(allowed_origins=frozenset()) -> web.Application:
    app = web.Application(
        middlewares=[web_server.make_cors_middleware(allowed_origins)]
    )

    async def api_status(_req):
        return web.json_response({"ok": True})

    async def api_mutate(_req):
        return web.json_response({"mutated": True})

    app.router.add_get("/api/status", api_status)
    app.router.add_post("/api/tasks", api_mutate)
    return app


async def _client(app) -> TestClient:
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


@pytest.mark.asyncio
async def test_never_emits_wildcard_origin():
    client = await _client(_cors_app())
    try:
        resp = await client.get(
            "/api/status", headers={"Origin": "https://evil.example"}
        )
        assert resp.status == 200
        assert resp.headers.get("Access-Control-Allow-Origin") != "*"
        # Untrusted origin gets no CORS grant at all.
        assert "Access-Control-Allow-Origin" not in resp.headers
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_loopback_origin_is_echoed_with_credentials():
    client = await _client(_cors_app())
    try:
        origin = "http://127.0.0.1:5173"
        resp = await client.get("/api/status", headers={"Origin": origin})
        assert resp.status == 200
        assert resp.headers.get("Access-Control-Allow-Origin") == origin
        assert resp.headers.get("Access-Control-Allow-Credentials") == "true"
        assert resp.headers.get("Vary") == "Origin"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_allowlisted_origin_is_echoed():
    from flaghunter.config.remote_access import resolve_allowed_origins

    allow = resolve_allowed_origins("https://console.example.com")
    client = await _client(_cors_app(allow))
    try:
        origin = "https://console.example.com"
        resp = await client.get("/api/status", headers={"Origin": origin})
        assert resp.headers.get("Access-Control-Allow-Origin") == origin
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_preflight_grants_only_trusted_origin():
    client = await _client(_cors_app())
    try:
        good = await client.options(
            "/api/tasks", headers={"Origin": "http://localhost:8080"}
        )
        assert good.headers.get("Access-Control-Allow-Origin") == "http://localhost:8080"
        assert "POST" in good.headers.get("Access-Control-Allow-Methods", "")

        bad = await client.options(
            "/api/tasks", headers={"Origin": "https://evil.example"}
        )
        # Preflight still answers 200, but without a CORS grant → browser blocks.
        assert "Access-Control-Allow-Origin" not in bad.headers
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_state_change_from_untrusted_origin_is_forbidden():
    client = await _client(_cors_app())
    try:
        resp = await client.post(
            "/api/tasks", headers={"Origin": "https://evil.example"}
        )
        assert resp.status == 403
        assert (await resp.json())["error"] == "forbidden"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_state_change_without_origin_or_from_loopback_passes():
    client = await _client(_cors_app())
    try:
        # No Origin (curl / MCP client) → not a browser CSRF, allowed.
        r1 = await client.post("/api/tasks")
        assert r1.status == 200
        # Loopback origin (the console itself) → allowed.
        r2 = await client.post(
            "/api/tasks", headers={"Origin": "http://127.0.0.1:8080"}
        )
        assert r2.status == 200
    finally:
        await client.close()
