"""Tests for missing tool advisor and executor integration."""

from __future__ import annotations

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.tools._tool_env import suggest_missing_tool
from flaghunter.tools.executor import ToolExecutor
from flaghunter.tools.notes import set_notes_file
from flaghunter.tools.registry import Tool, ToolSchema


@pytest.fixture
def isolated_notes(tmp_path):
    notes_file = tmp_path / "notes.json"
    set_notes_file(notes_file)
    notes_module._notes.clear()
    yield notes_file
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


def _make_tool(name: str, exc: Exception | None = None) -> Tool:
    async def fn(arguments: dict, runtime) -> str:
        if exc is not None:
            raise exc
        return "ok"

    return Tool(
        name=name,
        description="",
        schema=ToolSchema(properties={"cmd": {"type": "string"}}),
        execute_fn=fn,
    )


def test_suggest_known_tool():
    hint = suggest_missing_tool("sqlmap")
    assert "apt install sqlmap" in hint


def test_suggest_unknown_tool():
    hint = suggest_missing_tool("xyz_tool")
    assert "not found" in hint


@pytest.mark.asyncio
async def test_not_found_writes_notes(isolated_notes):
    executor = ToolExecutor(runtime=None, timeout=10, max_retries=0)
    tool = _make_tool("sqlmap", RuntimeError("command not found"))

    result = await executor.execute(tool, {"cmd": "scan"})

    assert result.success is False
    assert "[Tool Advisor]" in result.error
    note = notes_module._notes["missing_tool_sqlmap"]
    assert note["category"] == "artifact"
    assert "apt install sqlmap" in note["content"]
    assert note["metadata"]["tool"] == "sqlmap"


@pytest.mark.asyncio
async def test_found_tool_no_note(isolated_notes):
    executor = ToolExecutor(runtime=None, timeout=10, max_retries=0)
    tool = _make_tool("sqlmap")

    result = await executor.execute(tool, {"cmd": "scan"})

    assert result.success is True
    assert "missing_tool_sqlmap" not in notes_module._notes
