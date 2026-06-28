"""param_discovery: probes a wordlist and flags reflected / behaviour-changing params."""

from __future__ import annotations

import json

import pytest

import flaghunter.tools.param_discovery as pd
from flaghunter.tools.registry import get_tool


def test_tool_is_registered():
    tool = get_tool("param_discovery")
    assert tool is not None
    assert tool.category == "recon"
    assert "T1595.003" in tool.technique_ids


@pytest.mark.asyncio
async def test_detects_reflected_status_and_length(monkeypatch):
    baseline = {"status": 200, "body": "home", "length": 4}

    async def fake_send(method, url, *, params=None, data=None, timeout=10):
        # baseline request carries no sentinel
        if pd._SENTINEL not in (url or "") and not data:
            return baseline
        # which param is under test?
        if data:
            name = next((k for k, v in data.items() if v == pd._SENTINEL), "")
        else:
            name = "id" if "id=" in url else ("page" if "page=" in url else "")
        if name == "id":  # reflects the sentinel
            return {"status": 200, "body": f"echo {pd._SENTINEL} ok", "length": 30}
        if name == "page":  # changes status
            return {"status": 500, "body": "err", "length": 3}
        return baseline  # everything else: no change

    monkeypatch.setattr(pd, "_send", fake_send)
    out = json.loads(await pd.param_discovery({"url": "http://t/", "wordlist": ["id", "page", "zzz"]}, None))

    signals = {f["param"]: f["signal"] for f in out["found"]}
    assert signals.get("id") == "reflected"
    assert signals.get("page") == "status-change"
    assert "zzz" not in signals  # no behaviour change -> not reported
    assert out["total_found"] == 2


@pytest.mark.asyncio
async def test_no_false_positive_on_static_endpoint(monkeypatch):
    async def fake_send(method, url, *, params=None, data=None, timeout=10):
        return {"status": 200, "body": "static page", "length": 11}

    monkeypatch.setattr(pd, "_send", fake_send)
    out = json.loads(await pd.param_discovery({"url": "http://t/", "wordlist": ["a", "b", "c"]}, None))
    assert out["found"] == []
    assert out["total_found"] == 0


@pytest.mark.asyncio
async def test_post_method_uses_form_body(monkeypatch):
    seen_methods = []

    async def fake_send(method, url, *, params=None, data=None, timeout=10):
        seen_methods.append(method)
        if data and data.get("user") == pd._SENTINEL:
            return {"status": 200, "body": f"{pd._SENTINEL}", "length": 12}
        return {"status": 200, "body": "x", "length": 1}

    monkeypatch.setattr(pd, "_send", fake_send)
    out = json.loads(await pd.param_discovery({"url": "http://t/login", "method": "post", "wordlist": ["user"]}, None))
    assert all(m == "POST" for m in seen_methods)
    assert any(f["param"] == "user" for f in out["found"])


@pytest.mark.asyncio
async def test_missing_url():
    out = await pd.param_discovery({}, None)
    assert "url is required" in out
