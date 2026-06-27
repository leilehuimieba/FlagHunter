"""The guardrail_probe tool wires generation -> probe without hitting the network."""

from __future__ import annotations

import pytest

import flaghunter.tools.guardrail_probe as gp
from flaghunter.redteam.probe import ProbeResult
from flaghunter.tools.registry import get_tool


def test_tool_is_registered():
    tool = get_tool("guardrail_probe")
    assert tool is not None
    assert tool.category == "redteam"


@pytest.mark.asyncio
async def test_requires_url():
    out = await gp.guardrail_probe({}, None)
    assert "url is required" in out


@pytest.mark.asyncio
async def test_wires_generate_and_probe(monkeypatch):
    captured = {}

    def fake_probe(url, payloads, sender, timeout):
        captured["url"] = url
        captured["n"] = len(payloads)
        # one bypass, one block
        return [
            ProbeResult(
                pid="o01", category="injection", transform_chain=["base32"],
                expected_block=True, base_intent="x", sent_message="NFXH",
                decision="allow", risk_level="low", max_score=0.0,
                finding_kinds=[], outcome="bypassed", bypassed=True,
            ),
            ProbeResult(
                pid="o02", category="injection", transform_chain=["base64"],
                expected_block=True, base_intent="x", sent_message="aWdu",
                decision="block", risk_level="critical", max_score=0.85,
                finding_kinds=["obfuscated_injection"], outcome="blocked", bypassed=False,
            ),
        ]

    monkeypatch.setattr(gp, "probe_endpoint", fake_probe)
    out = await gp.guardrail_probe(
        {"url": "http://127.0.0.1:8000/gateway/chat", "categories": ["injection"]}, None
    )
    assert captured["url"].endswith("/gateway/chat")
    assert captured["n"] > 0
    assert "bypasses=1" in out
    assert "o01" in out  # bypassed pid surfaced
    assert "blocked" in out


@pytest.mark.asyncio
async def test_unknown_transform_reported(monkeypatch):
    out = await gp.guardrail_probe(
        {"url": "http://x", "categories": ["injection"], "transforms": ["nope"]}, None
    )
    assert "Error" in out
