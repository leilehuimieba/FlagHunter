from __future__ import annotations

from types import SimpleNamespace

import pytest

from flaghunter.tools.tool_guard import ToolGuard, ToolMissingError


@pytest.mark.parametrize(
    ("tool_name", "resolved", "expected_available"),
    [
        ("curl", "C:/Windows/System32/curl.exe", True),
        ("sqlmap", "D:/tools/sqlmap.py", True),
        ("ffuf", None, False),
        ("nuclei", None, False),
        ("node", "C:/Program Files/nodejs/node.exe", True),
    ],
)
def test_tool_guard_check(monkeypatch, tool_name, resolved, expected_available):
    monkeypatch.setattr(
        "flaghunter.tools.tool_guard.find_tool",
        lambda name: resolved if name == tool_name else None,
    )
    if tool_name == "node":
        monkeypatch.setattr(
            "flaghunter.tools.tool_guard.shutil.which",
            lambda name: resolved if name == "node" else None,
        )
    guard = ToolGuard(runtime=None)
    status = guard.check(tool_name)
    assert status.available is expected_available


def test_tool_guard_suggest_install_known_tools():
    guard = ToolGuard(runtime=None)
    for tool_name in ["curl", "sqlmap", "ffuf", "nuclei", "node"]:
        hint = guard.suggest_install(tool_name)
        assert hint
        assert isinstance(hint, str)


def test_tool_guard_require_raises(monkeypatch):
    monkeypatch.setattr(
        "flaghunter.tools.tool_guard.find_tool",
        lambda name: None,
    )
    guard = ToolGuard(runtime=None)
    with pytest.raises(ToolMissingError):
        guard.require(["sqlmap", "ffuf"])


def test_tool_guard_browser_requires_playwright(monkeypatch):
    runtime = SimpleNamespace(browser_action=lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "flaghunter.tools.tool_guard.importlib.util.find_spec",
        lambda name: None if name == "playwright" else object(),
    )
    guard = ToolGuard(runtime=runtime)
    status = guard.check("browser")
    assert status.available is False


def test_tool_guard_http_request_requires_httpx(monkeypatch):
    runtime = SimpleNamespace(proxy_action=lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "flaghunter.tools.tool_guard.importlib.util.find_spec",
        lambda name: None if name == "httpx" else object(),
    )
    guard = ToolGuard(runtime=runtime)
    status = guard.check("http_request")
    assert status.available is False
