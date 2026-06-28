"""vhost_discovery: Host-header brute that diffs responses against a baseline."""

from __future__ import annotations

import json

import pytest

import flaghunter.tools.vhost_discovery as vh
from flaghunter.tools.registry import get_tool


def test_tool_is_registered():
    tool = get_tool("vhost_discovery")
    assert tool is not None
    assert tool.category == "recon"
    assert "T1595.003" in tool.technique_ids


@pytest.mark.asyncio
async def test_detects_distinct_vhosts(monkeypatch):
    baseline_body = "<title>Default</title>" + "x" * 100

    async def fake_send(url, host, *, timeout=10):
        if host.startswith(vh._BASELINE_LABEL):
            return {"status": 200, "body": baseline_body, "length": len(baseline_body)}
        if host.startswith("admin."):  # distinct title + status
            b = "<title>Admin Panel</title>"
            return {"status": 401, "body": b, "length": len(b)}
        if host.startswith("staging."):  # distinct title only
            b = "<title>Staging</title>" + "x" * 100
            return {"status": 200, "body": b, "length": len(b)}
        # everything else mirrors the baseline -> not a real vhost
        return {"status": 200, "body": baseline_body, "length": len(baseline_body)}

    monkeypatch.setattr(vh, "_send", fake_send)
    out = json.loads(
        await vh.vhost_discovery(
            {"target": "10.0.0.5", "base_domain": "example.com", "wordlist": ["admin", "staging", "www"]},
            None,
        )
    )
    found = {f["vhost"]: f for f in out["found"]}
    assert "admin.example.com" in found
    assert "staging.example.com" in found
    assert "www.example.com" not in found  # mirrors baseline -> filtered
    assert found["staging.example.com"]["title"] == "Staging"


@pytest.mark.asyncio
async def test_no_false_positive_when_all_match_baseline(monkeypatch):
    body = "<title>Same</title>" + "y" * 50

    async def fake_send(url, host, *, timeout=10):
        return {"status": 200, "body": body, "length": len(body)}

    monkeypatch.setattr(vh, "_send", fake_send)
    out = json.loads(
        await vh.vhost_discovery(
            {"target": "http://10.0.0.5", "base_domain": "example.com", "wordlist": ["a", "b"]}, None
        )
    )
    assert out["found"] == []
    assert out["total_found"] == 0


@pytest.mark.asyncio
async def test_requires_target_and_domain():
    assert "target is required" in await vh.vhost_discovery({"base_domain": "x"}, None)
    assert "base_domain is required" in await vh.vhost_discovery({"target": "x"}, None)
