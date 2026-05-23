"""Tests for CTF hint search helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pentestagent.config.constants as C
import pytest

from pentestagent.knowledge import ctf_hint_searcher as mod


@pytest.mark.asyncio
async def test_search_returns_hints_from_llm(monkeypatch):
    # AH: ctf_hint_searcher now calls _opencli_search first, then tavily_search
    monkeypatch.setattr(
        mod,
        "_opencli_search",
        AsyncMock(
            return_value=[
                {"content": "Check parser confusion and unusual decoding chain."},
                {"content": "Look at file metadata and hidden chunks."},
            ]
        ),
    )
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=SimpleNamespace(
            content=(
                '{"hints":["检查多层编码链","关注元数据和隐藏块"],'
                '"confidence":"high"}'
            )
        )
    )

    hints = await mod.search_ctf_hints("misc", "strange archive challenge", llm)

    assert hints == ["检查多层编码链", "关注元数据和隐藏块"]


@pytest.mark.asyncio
async def test_search_empty_on_tavily_fail(monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("all search unavailable")

    # Mock all three backends to fail — no network calls should succeed
    monkeypatch.setattr(mod, "tavily_search", _boom)
    monkeypatch.setattr(mod, "_brave_search", _boom)
    monkeypatch.setattr(mod, "_opencli_search", _boom)
    llm = MagicMock()
    llm.generate = AsyncMock()

    hints = await mod.search_ctf_hints("web", "login page", llm)

    assert hints == []
    llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_wp_summary_last_resort(monkeypatch):
    monkeypatch.setattr(
        mod,
        "tavily_search",
        AsyncMock(
            return_value=[
                {"content": "Writeup shows extraction, decode, and final validation."}
            ]
        ),
    )
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=SimpleNamespace(content="1. 提取附件\n2. 解码隐藏内容\n3. 验证关键参数")
    )

    summary = await mod.search_ctf_writeup_last_resort(
        "misc", "embedded blob", llm
    )

    assert summary
    assert "提取附件" in summary


def test_threshold_constants_exist():
    assert hasattr(C, "CTF_HINT_SEARCH_THRESHOLD")
    assert C.CTF_HINT_SEARCH_THRESHOLD == 2
    assert hasattr(C, "CTF_WP_SEARCH_THRESHOLD")
    assert C.CTF_WP_SEARCH_THRESHOLD == 4
