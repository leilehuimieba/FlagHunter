"""The llm_payload_gen tool registers, runs, and writes batches."""

from __future__ import annotations

import json

import pytest

from flaghunter.tools.llm_payload_gen import llm_payload_gen
from flaghunter.tools.registry import get_tool


def test_tool_is_registered():
    tool = get_tool("llm_payload_gen")
    assert tool is not None
    assert tool.category == "redteam"


@pytest.mark.asyncio
async def test_returns_summary_with_inline_jsonl():
    out = await llm_payload_gen({"categories": ["jailbreak"]}, None)
    assert "Generated" in out
    assert "Full JSONL" in out
    # the inline JSONL block contains parseable rows
    rows = [
        json.loads(line)
        for line in out.splitlines()
        if line.startswith("{") and '"pid"' in line
    ]
    assert rows
    assert all(r["category"] == "jailbreak" for r in rows)


@pytest.mark.asyncio
async def test_writes_file_when_output_path_given(tmp_path):
    target = tmp_path / "batch.jsonl"
    out = await llm_payload_gen(
        {"categories": ["injection"], "output_path": str(target)}, None
    )
    assert "Wrote JSONL batch" in out
    assert target.exists()
    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert lines and all(json.loads(line)["category"] == "injection" for line in lines)


@pytest.mark.asyncio
async def test_custom_transform_chain_is_applied():
    out = await llm_payload_gen(
        {"categories": ["injection"], "transforms": ["base32"]}, None
    )
    rows = [
        json.loads(line)
        for line in out.splitlines()
        if line.startswith("{") and '"pid"' in line
    ]
    assert rows
    assert all(r["transform_chain"] == ["base32"] for r in rows)


@pytest.mark.asyncio
async def test_unknown_transform_is_reported_gracefully():
    out = await llm_payload_gen(
        {"categories": ["injection"], "transforms": ["bogus"]}, None
    )
    assert "Error" in out
    assert "Available transforms" in out
