"""Tests for executor stealth mode."""

import asyncio

import pentestagent.tools.executor as executor_module
import pentestagent.tools.notes as notes_module
from pentestagent.tools.executor import ToolExecutor
from pentestagent.tools.registry import Tool, ToolSchema


class _NoopRuntime:
    pass


def _make_capture_tool(name: str) -> tuple[Tool, dict]:
    captured: dict = {}

    async def fn(arguments: dict, runtime) -> str:
        captured["arguments"] = arguments
        return "ok"

    tool = Tool(
        name=name,
        description="",
        schema=ToolSchema(
            properties={
                "url": {"type": "string"},
                "target": {"type": "string"},
                "headers": {"type": "object"},
            }
        ),
        execute_fn=fn,
    )
    return tool, captured


def test_stealth_off_by_default(monkeypatch):
    monkeypatch.delenv("PENTESTAGENT_STEALTH", raising=False)
    monkeypatch.setattr(notes_module, "get_all_notes_sync", lambda: {})

    active, delay_range = executor_module._is_stealth_active()

    assert active is False
    assert delay_range == (0.5, 2.0)


def test_stealth_on_via_env(monkeypatch):
    monkeypatch.setenv("PENTESTAGENT_STEALTH", "1")

    active, delay_range = executor_module._is_stealth_active()

    assert active is True
    assert delay_range == (1.0, 3.0)


def test_stealth_on_via_notes(monkeypatch):
    monkeypatch.delenv("PENTESTAGENT_STEALTH", raising=False)
    monkeypatch.setattr(
        notes_module,
        "get_all_notes_sync",
        lambda: {
            "waf_detected": {
                "category": "waf_detected",
                "metadata": {"delay_range": [1.2, 2.8]},
            }
        },
    )

    active, delay_range = executor_module._is_stealth_active()

    assert active is True
    assert delay_range == (1.2, 2.8)


def test_stealth_injects_user_agent(monkeypatch):
    async def _no_sleep(delay_range=(0.5, 2.0)):
        return None

    monkeypatch.setenv("PENTESTAGENT_STEALTH", "1")
    monkeypatch.setattr(notes_module, "get_all_notes_sync", lambda: {})
    monkeypatch.setattr(executor_module, "_stealth_delay", _no_sleep)
    monkeypatch.setattr(executor_module._random, "choice", lambda seq: "UA-TEST")

    tool, captured = _make_capture_tool("dirscan")
    executor = ToolExecutor(runtime=_NoopRuntime())

    result = asyncio.run(executor.execute(tool, {"target": "http://example.com"}))

    assert result.success is True
    assert captured["arguments"]["headers"]["User-Agent"] == "UA-TEST"


def test_stealth_no_overwrite_existing_ua(monkeypatch):
    async def _no_sleep(delay_range=(0.5, 2.0)):
        return None

    monkeypatch.setenv("PENTESTAGENT_STEALTH", "1")
    monkeypatch.setattr(notes_module, "get_all_notes_sync", lambda: {})
    monkeypatch.setattr(executor_module, "_stealth_delay", _no_sleep)
    monkeypatch.setattr(executor_module._random, "choice", lambda seq: "UA-TEST")

    tool, captured = _make_capture_tool("dirscan")
    executor = ToolExecutor(runtime=_NoopRuntime())

    result = asyncio.run(
        executor.execute(
            tool,
            {
                "target": "http://example.com",
                "headers": {"User-Agent": "UA-EXISTING"},
            },
        )
    )

    assert result.success is True
    assert captured["arguments"]["headers"]["User-Agent"] == "UA-EXISTING"
