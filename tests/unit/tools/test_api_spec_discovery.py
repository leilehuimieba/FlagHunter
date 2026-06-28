"""api_spec_discovery: fetches and parses OpenAPI/Swagger specs into an endpoint map."""

from __future__ import annotations

import json

import pytest

import flaghunter.tools.api_spec_discovery as asd
from flaghunter.tools.registry import get_tool

_OPENAPI = json.dumps(
    {
        "openapi": "3.0.1",
        "info": {"title": "Demo API", "version": "1.0"},
        "paths": {
            "/users/{id}": {
                "get": {"parameters": [{"name": "id", "in": "path"}]},
                "delete": {},
            },
            "/login": {"post": {"parameters": [{"name": "username"}, {"name": "password"}]}},
        },
    }
)


def test_tool_is_registered():
    tool = get_tool("api_spec_discovery")
    assert tool is not None
    assert tool.category == "recon"
    assert "T1595" in tool.technique_ids


@pytest.mark.asyncio
async def test_parses_spec_and_extracts_endpoints(monkeypatch):
    async def fake_send(url, *, timeout=10):
        if url == "http://t:8080/openapi.json":
            return {"status": 200, "body": _OPENAPI, "content_type": "application/json"}
        return {"status": 404, "body": "not found", "content_type": "text/html"}

    monkeypatch.setattr(asd, "_send", fake_send)
    out = json.loads(await asd.api_spec_discovery({"base_url": "http://t:8080"}, None))

    assert out["specs_found"] == 1
    spec = out["specs"][0]
    assert spec["title"] == "Demo API"
    assert spec["version"] == "3.0.1"
    paths = {e["path"]: e for e in spec["endpoints"]}
    assert set(paths["/users/{id}"]["methods"]) == {"GET", "DELETE"}
    assert "id" in paths["/users/{id}"]["params"]
    assert set(paths["/login"]["params"]) == {"username", "password"}
    assert out["total_endpoints"] == 2


@pytest.mark.asyncio
async def test_no_spec_present_returns_empty(monkeypatch):
    async def fake_send(url, *, timeout=10):
        return {"status": 404, "body": "<html>nope</html>", "content_type": "text/html"}

    monkeypatch.setattr(asd, "_send", fake_send)
    out = json.loads(await asd.api_spec_discovery({"base_url": "http://t"}, None))
    assert out["specs_found"] == 0
    assert out["specs"] == []


@pytest.mark.asyncio
async def test_non_spec_json_is_rejected(monkeypatch):
    async def fake_send(url, *, timeout=10):
        # 200 but a normal JSON payload, not a spec
        return {"status": 200, "body": json.dumps({"hello": "world"}), "content_type": "application/json"}

    monkeypatch.setattr(asd, "_send", fake_send)
    out = json.loads(await asd.api_spec_discovery({"base_url": "http://t"}, None))
    assert out["specs_found"] == 0


@pytest.mark.asyncio
async def test_missing_base_url():
    out = await asd.api_spec_discovery({}, None)
    assert "base_url is required" in out
