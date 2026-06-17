"""Tests for the minimal structured http_request tool."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.tools import ToolExecutor
from flaghunter.tools.notes import get_all_notes_sync, set_notes_file
from flaghunter.tools.registry import clear_tools, get_tool

import flaghunter.tools.http_request as http_request_module


class _FakeRuntime:
    def __init__(self, result: dict):
        self.result = result
        self.proxy_calls: list[tuple[str, dict]] = []

    async def proxy_action(self, action: str, **kwargs):
        self.proxy_calls.append((action, dict(kwargs)))
        return self.result


@pytest.fixture(autouse=True)
def isolated_notes(tmp_path: Path):
    clear_tools()
    importlib.reload(http_request_module)
    notes_file = tmp_path / "notes.json"
    set_notes_file(notes_file)
    notes_module._notes.clear()
    notes_module._loaded_notes_file = None
    yield notes_file
    clear_tools()
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_http_request_passes_form_args_and_formats_output():
    tool = get_tool("http_request")
    assert tool is not None

    runtime = _FakeRuntime(
        {
            "status_code": 200,
            "headers": {"set-cookie": "sid=demo; Path=/"},
            "body": "logged in",
        }
    )

    output = await tool.execute(
        {
            "method": "POST",
            "url": "http://example.com/login",
            "headers": {"X-Test": "1"},
            "data": {"username": "demo", "password": "pw"},
            "timeout": 9,
        },
        runtime,
    )

    assert runtime.proxy_calls == [
        (
            "request",
            {
                "method": "POST",
                "url": "http://example.com/login",
                "headers": {"X-Test": "1"},
                "data": {"username": "demo", "password": "pw"},
                "files": None,
                "json": None,
                "timeout": 9,
            },
        )
    ]
    assert "HTTP POST http://example.com/login" in output
    assert "Status Code: 200" in output
    assert "set-cookie: sid=demo; Path=/" in output
    assert "Body:\nlogged in" in output


@pytest.mark.asyncio
async def test_http_request_form_alias_and_json_passthrough():
    tool = get_tool("http_request")
    assert tool is not None

    runtime = _FakeRuntime(
        {
            "status_code": 201,
            "headers": {"content-type": "application/json"},
            "body": '{"ok":true}',
        }
    )

    output = await tool.execute(
        {
            "method": "POST",
            "url": "http://example.com/visit",
            "headers": {"Content-Type": "application/json"},
            "json": {"url": "http://collector.local/"},
            "timeout": 5,
        },
        runtime,
    )

    assert runtime.proxy_calls[0] == (
        "request",
        {
            "method": "POST",
            "url": "http://example.com/visit",
            "headers": {"Content-Type": "application/json"},
            "data": None,
            "files": None,
            "json": {"url": "http://collector.local/"},
            "timeout": 5,
        },
    )
    assert "Status Code: 201" in output
    assert '{"ok":true}' in output


@pytest.mark.asyncio
async def test_http_request_rejects_conflicting_body_modes():
    tool = get_tool("http_request")
    assert tool is not None

    runtime = _FakeRuntime({"status_code": 200, "headers": {}, "body": "ok"})
    output = await tool.execute(
        {
            "method": "POST",
            "url": "http://example.com/login",
            "data": {"username": "demo"},
            "json": {"username": "demo"},
        },
        runtime,
    )

    assert "use either 'data/form' or 'json'" in output
    assert runtime.proxy_calls == []


@pytest.mark.asyncio
async def test_http_request_passes_files_for_multipart_upload():
    tool = get_tool("http_request")
    assert tool is not None

    runtime = _FakeRuntime(
        {
            "status_code": 200,
            "headers": {"content-type": "text/plain"},
            "body": "upload ok",
        }
    )

    output = await tool.execute(
        {
            "method": "POST",
            "url": "http://example.com/update.php",
            "data": {
                "phone": "12345678901",
                "email": "demo_1@demo_1.com",
                "nickname": "demo_user",
            },
            "files": {
                "photo": {
                    "filename": "avatar.txt",
                    "content": "hello-world",
                    "content_type": "text/plain",
                }
            },
        },
        runtime,
    )

    assert runtime.proxy_calls == [
        (
            "request",
            {
                "method": "POST",
                "url": "http://example.com/update.php",
                "headers": {},
                "data": {
                    "phone": "12345678901",
                    "email": "demo_1@demo_1.com",
                    "nickname": "demo_user",
                },
                "files": {
                    "photo": {
                        "filename": "avatar.txt",
                        "content": "hello-world",
                        "content_type": "text/plain",
                    }
                },
                "json": None,
                "timeout": 30,
            },
        )
    ]
    assert "upload ok" in output


@pytest.mark.asyncio
async def test_http_request_rejects_files_with_json():
    tool = get_tool("http_request")
    assert tool is not None

    runtime = _FakeRuntime({"status_code": 200, "headers": {}, "body": "ok"})
    output = await tool.execute(
        {
            "method": "POST",
            "url": "http://example.com/upload",
            "files": {"photo": {"filename": "a.txt", "content": "x"}},
            "json": {"hello": "world"},
        },
        runtime,
    )

    assert "use either 'files' or 'json'" in output
    assert runtime.proxy_calls == []


@pytest.mark.asyncio
async def test_http_request_flag_body_is_visible_to_executor():
    tool = get_tool("http_request")
    assert tool is not None

    runtime = _FakeRuntime(
        {
            "status_code": 200,
            "headers": {"content-type": "text/plain"},
            "body": "welcome admin\nflag{http_request_cookie_ok}\n",
        }
    )

    result = await ToolExecutor(runtime=runtime, timeout=10).execute(
        tool,
        {
            "method": "GET",
            "url": "http://example.com/admin",
            "headers": {"Cookie": "sid=demo"},
        },
    )

    assert result.success is True
    assert "flag{http_request_cookie_ok}" in (result.result or "")

    notes = get_all_notes_sync()
    assert any(
        note.get("content") == "flag{http_request_cookie_ok}"
        and (note.get("metadata") or {}).get("source_tool") == "http_request"
        for note in notes.values()
    )
