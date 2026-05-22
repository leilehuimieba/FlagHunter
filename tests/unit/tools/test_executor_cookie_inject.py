"""Cookie auto-injection tests for ToolExecutor."""

import pytest

from pentestagent.tools import notes as notes_module
from pentestagent.tools.executor import ToolExecutor
from pentestagent.tools.registry import Tool, ToolSchema



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
                "cookie": {"type": "string"},
                "headers": {"type": "object"},
            }
        ),
        execute_fn=fn,
    )
    return tool, captured


@pytest.mark.asyncio
async def test_sqlmap_auto_inject_cookie(monkeypatch):
    monkeypatch.setattr(
        notes_module,
        "get_all_notes_sync",
        lambda: {
            "cred_latest": {
                "category": "credential",
                "metadata": {"cookie_string": "session=abc123; role=admin"},
            }
        },
    )

    tool, captured = _make_capture_tool("sqlmap")
    executor = ToolExecutor(runtime=None)
    original_args = {"url": "http://example.com/item?id=1"}

    result = await executor.execute(tool, original_args)

    assert result.success is True
    assert captured["arguments"]["cookie"] == "session=abc123; role=admin"
    assert original_args == {"url": "http://example.com/item?id=1"}


@pytest.mark.asyncio
async def test_dirscan_auto_inject_header(monkeypatch):
    monkeypatch.setattr(
        notes_module,
        "get_all_notes_sync",
        lambda: {
            "cred_latest": {
                "category": "credential",
                "metadata": {"cookie_string": "token=dirscan-cookie"},
            }
        },
    )

    tool, captured = _make_capture_tool("dirscan")
    executor = ToolExecutor(runtime=None)

    result = await executor.execute(
        tool,
        {"target": "http://example.com", "headers": {"User-Agent": "UA"}},
    )

    assert result.success is True
    assert captured["arguments"]["headers"] == {
        "User-Agent": "UA",
        "Cookie": "token=dirscan-cookie",
    }


@pytest.mark.asyncio
async def test_no_inject_when_cookie_already_set(monkeypatch):
    monkeypatch.setattr(
        notes_module,
        "get_all_notes_sync",
        lambda: {
            "cred_latest": {
                "category": "credential",
                "metadata": {"cookie_string": "session=from-notes"},
            }
        },
    )

    tool, captured = _make_capture_tool("sqlmap")
    executor = ToolExecutor(runtime=None)

    result = await executor.execute(
        tool,
        {"url": "http://example.com/item?id=1", "cookie": "session=planner"},
    )

    assert result.success is True
    assert captured["arguments"]["cookie"] == "session=planner"


@pytest.mark.asyncio
async def test_non_inject_tool_unaffected(monkeypatch):
    monkeypatch.setattr(
        notes_module,
        "get_all_notes_sync",
        lambda: {
            "cred_latest": {
                "category": "credential",
                "metadata": {"cookie_string": "session=ignored"},
            }
        },
    )

    tool, captured = _make_capture_tool("nmap")
    executor = ToolExecutor(runtime=None)
    original_args = {"target": "127.0.0.1"}

    result = await executor.execute(tool, original_args)

    assert result.success is True
    assert captured["arguments"] == {"target": "127.0.0.1"}
    assert original_args == {"target": "127.0.0.1"}
