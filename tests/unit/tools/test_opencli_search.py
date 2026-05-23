"""Tests for OpenCLI web search fallback behavior."""

from __future__ import annotations

import types
from unittest.mock import AsyncMock

import pytest

from pentestagent.tools import web_search as mod


def _completed(stdout: str = "", returncode: int = 0, stderr: str = ""):
    return types.SimpleNamespace(stdout=stdout, returncode=returncode, stderr=stderr)


def _cmd_tail(cmd):
    return list(cmd[1:])


@pytest.mark.asyncio
async def test_opencli_search_returns_results(monkeypatch):
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: _completed(
            stdout=(
                '[{"title":"Result A","url":"https://example.com","snippet":"Snippet A"}]'
            )
        ),
    )

    results = await mod._opencli_search("ctf web challenge", max_results=3)

    assert results == [
        {
            "title": "Result A",
            "url": "https://example.com",
            "content": "Snippet A",
        }
    ]


@pytest.mark.asyncio
async def test_opencli_fallback_to_ddg(monkeypatch):
    calls = []

    def _run(cmd, *args, **kwargs):
        calls.append(cmd)
        if _cmd_tail(cmd)[:2] == ["profile", "list"]:
            return _completed(stdout="")
        if cmd[1] == "google":
            return _completed(returncode=1, stderr="google failed")
        return _completed(
            stdout=(
                '[{"title":"DDG Result","url":"https://ddg.example","description":"DDG Snippet"}]'
            )
        )

    monkeypatch.setattr(mod.subprocess, "run", _run)

    results = await mod._opencli_search("fallback query", max_results=2)

    search_calls = [cmd for cmd in calls if _cmd_tail(cmd)[:2] != ["profile", "list"]]
    assert len(search_calls) == 2
    assert search_calls[0][1] == "google"
    assert search_calls[1][1] == "duckduckgo"
    assert results == [
        {
            "title": "DDG Result",
            "url": "https://ddg.example",
            "content": "DDG Snippet",
        }
    ]


@pytest.mark.asyncio
async def test_opencli_retries_other_connected_profile(monkeypatch):
    calls = []

    def _run(cmd, *args, **kwargs):
        calls.append((cmd, kwargs.get("env", {}).get("OPENCLI_PROFILE")))
        if _cmd_tail(cmd)[:2] == ["profile", "list"]:
            return _completed(
                stdout=(
                    "Connected Browser Bridge profiles\n\n"
                    "  zuuch92k default — connected v1.0.15\n"
                    "  nbuwf4xv — connected v1.0.15\n"
                )
            )
        if kwargs.get("env", {}).get("OPENCLI_PROFILE") == "zuuch92k":
            return _completed(returncode=1, stderr="google failed on first profile")
        return _completed(
            stdout=(
                '[{"title":"Google Result","url":"https://example.net","snippet":"Snippet B"}]'
            )
        )

    monkeypatch.setattr(mod.subprocess, "run", _run)
    monkeypatch.setenv("OPENCLI_PROFILE", "zuuch92k")

    results = await mod._run_opencli_search("google", "profile retry", max_results=2)

    assert [profile for _, profile in calls] == [None, "zuuch92k", "nbuwf4xv"]
    assert results == [
        {
            "title": "Google Result",
            "url": "https://example.net",
            "content": "Snippet B",
        }
    ]


@pytest.mark.asyncio
async def test_opencli_not_installed_silent(monkeypatch):
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: _completed(returncode=1, stderr="'opencli' not found"),
    )

    results = await mod._opencli_search("no opencli")

    assert results == []


@pytest.mark.asyncio
async def test_web_search_falls_back_to_opencli(monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("tavily/brave unavailable")

    # Disable both Tavily and Brave so the test reaches the opencli fallback
    monkeypatch.setattr(mod, "tavily_search", _boom)
    monkeypatch.setattr(mod, "_brave_search", _boom)
    monkeypatch.setattr(
        mod,
        "_opencli_search",
        AsyncMock(
            return_value=[
                {
                    "title": "OpenCLI Result",
                    "url": "https://example.org",
                    "content": "helpful snippet",
                }
            ]
        ),
    )

    output = await mod.web_search({"query": "jwt bypass"}, runtime=None)

    assert "OpenCLI Result" in output
    assert "https://example.org" in output
