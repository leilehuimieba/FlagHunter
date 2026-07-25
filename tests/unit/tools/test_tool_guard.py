from __future__ import annotations

import sys
import threading
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


def test_detect_version_does_not_deadlock_on_lingering_grandchild(monkeypatch, tmp_path):
    """A version probe that leaves a grandchild holding the output handle must
    not deadlock the whole check.

    Regression guard for the Windows-LocalRuntime hang where ``firefox
    --version`` / ``chrome --version`` relaunch themselves, leaving a content
    process that inherits the write end of a captured PIPE. The reader threads
    never see EOF and the post-timeout ``communicate()`` cleanup joins forever.
    Capturing via a temp file (no reader threads) keeps the probe bounded.
    """
    # A fake "tool": prints its version, then leaves a grandchild alive that
    # inherits the process's stdout for far longer than the 8s probe timeout.
    faketool = tmp_path / "faketool.py"
    faketool.write_text(
        "import sys, subprocess\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(25)'])\n"
        "sys.stdout.write('FakeTool 9.9.9\\n')\n"
        "sys.stdout.flush()\n",
        encoding="utf-8",
    )
    # Route _detect_version's argv to `python <faketool.py>` for this tool name.
    monkeypatch.setitem(
        __import__("flaghunter.tools.tool_guard", fromlist=["_VERSION_FLAGS"])._VERSION_FLAGS,
        "faketool",
        [[str(faketool)]],
    )

    guard = ToolGuard(runtime=None)
    result: dict[str, object] = {}

    def _probe() -> None:
        result["version"] = guard._detect_version("faketool", sys.executable)

    worker = threading.Thread(target=_probe, daemon=True)
    worker.start()
    worker.join(15)
    assert not worker.is_alive(), "_detect_version deadlocked on a lingering grandchild"
    assert result.get("version") == "FakeTool 9.9.9"
