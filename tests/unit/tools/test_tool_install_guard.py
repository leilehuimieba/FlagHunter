"""Tests for missing-tool install guard helpers and executor notifications."""

from __future__ import annotations

import pytest

import flaghunter.session.notifier as notifier_module
import flaghunter.tools._tool_env as tool_env
import flaghunter.tools.notes as notes_module
from flaghunter.tools._tool_env import check_disk_space, get_tool_install_info
from flaghunter.tools.executor import (
    ToolExecutor,
    _build_tool_install_confirmation_message,
)
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


def test_check_disk_space_returns_dict(tmp_path):
    result = check_disk_space(str(tmp_path))

    assert isinstance(result, dict)
    assert "free_gb" in result
    assert "free_pct" in result


def test_get_tool_info_known():
    info = get_tool_install_info("nuclei")

    assert info["tool"] == "nuclei"
    assert info["estimated_mb"] == 60
    assert info["estimated_display"] == "60 MB"


def test_get_tool_info_unknown():
    info = get_tool_install_info("xyz")

    assert info["tool"] == "xyz"
    assert info["estimated_mb"] == 0
    assert info["estimated_display"] == "unknown"


def test_low_disk_warning(monkeypatch):
    monkeypatch.setattr(
        tool_env,
        "check_disk_space",
        lambda path=".": {
            "total_gb": 100.0,
            "used_gb": 99.5,
            "free_gb": 0.5,
            "free_pct": 0.5,
        },
    )

    confirm_msg, disk, info = _build_tool_install_confirmation_message("nuclei")

    assert "LOW DISK SPACE" in confirm_msg
    assert disk["free_gb"] == 0.5
    assert info["estimated_mb"] == 60


@pytest.mark.asyncio
async def test_notify_called_on_missing_tool(isolated_notes, monkeypatch):
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        tool_env,
        "check_disk_space",
        lambda path=".": {
            "total_gb": 100.0,
            "used_gb": 50.0,
            "free_gb": 50.0,
            "free_pct": 50.0,
        },
    )
    monkeypatch.setattr(
        notifier_module,
        "notify",
        lambda level, message: calls.append((level, message)),
    )

    executor = ToolExecutor(runtime=None, timeout=10, max_retries=0)
    tool = _make_tool("sqlmap", RuntimeError("command not found"))

    result = await executor.execute(tool, {"cmd": "scan"})

    assert result.success is False
    assert calls
    level, payload = calls[0]
    assert level == "tool_install_required"
    assert isinstance(payload, dict)
    assert payload["tool"] == "sqlmap"
    assert payload["size_mb"] == 10
    assert payload["disk_free_gb"] == 50.0
