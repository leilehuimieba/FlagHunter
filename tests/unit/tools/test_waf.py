"""Tests for the waf tool."""

import asyncio

import pentestagent.tools.waf as waf_module
from pentestagent.tools.waf import run_waf


def test_detect_cloudflare_by_header(monkeypatch):
    async def _fake_probe(runtime, url):
        return {
            "normal": {
                "status": 200,
                "headers": {"Server": "cloudflare", "cf-ray": "123abc"},
                "body": "ok",
                "error": "",
            },
            "attack": {
                "status": 403,
                "headers": {"cf-ray": "123abc"},
                "body": "blocked",
                "error": "",
            },
        }

    monkeypatch.setattr(waf_module, "_probe_http", _fake_probe)

    result = asyncio.run(run_waf(action="detect", url="http://example.com"))

    assert result["detected"] is True
    assert result["brand"] == "Cloudflare"
    assert result["confidence"] == "high"


def test_detect_by_body_keyword(monkeypatch):
    async def _fake_probe(runtime, url):
        return {
            "normal": {
                "status": 200,
                "headers": {"Server": "nginx"},
                "body": "welcome",
                "error": "",
            },
            "attack": {
                "status": 406,
                "headers": {"Server": "nginx"},
                "body": "Request blocked by ModSecurity",
                "error": "",
            },
        }

    monkeypatch.setattr(waf_module, "_probe_http", _fake_probe)

    result = asyncio.run(run_waf(action="detect", url="http://example.com"))

    assert result["detected"] is True
    assert result["brand"] == "ModSecurity"


def test_detect_no_waf(monkeypatch):
    async def _fake_probe(runtime, url):
        return {
            "normal": {
                "status": 200,
                "headers": {"Server": "nginx", "X-Powered-By": "PHP/8.2"},
                "body": "hello",
                "error": "",
            },
            "attack": {
                "status": 200,
                "headers": {"Server": "nginx"},
                "body": "normal application response",
                "error": "",
            },
        }

    monkeypatch.setattr(waf_module, "_probe_http", _fake_probe)

    result = asyncio.run(run_waf(action="detect", url="http://example.com"))

    assert result["detected"] is False
    assert result["brand"] == ""


def test_bypass_config_cloudflare():
    result = asyncio.run(
        run_waf(
            action="bypass_config",
            url="http://example.com",
            waf_hint="Cloudflare",
        )
    )

    assert result["brand"] == "Cloudflare"
    assert result["config"]["cf_bypass"] is True
    assert result["config"]["tls_fingerprint"] == "chrome"


def test_bypass_config_generic(monkeypatch):
    async def _fake_probe(runtime, url):
        return {
            "normal": {
                "status": 200,
                "headers": {"Server": "nginx"},
                "body": "ok",
                "error": "",
            },
            "attack": {
                "status": 200,
                "headers": {"Server": "nginx"},
                "body": "ok",
                "error": "",
            },
        }

    monkeypatch.setattr(waf_module, "_probe_http", _fake_probe)

    result = asyncio.run(
        run_waf(
            action="bypass_config",
            url="http://example.com",
            waf_hint="",
            runtime=None,
        )
    )

    assert result["config"]["user_agents"]
    assert result["config"]["delay_range"] == [0.5, 2.0]
    assert result["config"]["headers"]["X-Forwarded-For"] == "127.0.0.1"
