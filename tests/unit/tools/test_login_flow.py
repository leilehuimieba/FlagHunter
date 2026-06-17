from __future__ import annotations

from pathlib import Path

import pytest

from flaghunter.tools.notes import set_notes_file

import flaghunter.tools.notes as notes_module


@pytest.mark.asyncio
async def test_login_flow_no_runtime():
    from flaghunter.tools.login_flow import run_login_flow

    result = await run_login_flow(
        "http://x",
        "#u",
        "#p",
        "admin",
        "pass",
        runtime=None,
    )

    assert result["success"] is False
    assert "runtime" in result["error"].lower()


@pytest.mark.asyncio
async def test_login_flow_ssh_runtime_rejected():
    from flaghunter.tools.login_flow import run_login_flow

    FakeSSH = type("SSHRuntime", (), {})

    result = await run_login_flow(
        "http://x",
        "#u",
        "#p",
        "admin",
        "pass",
        runtime=FakeSSH(),
    )

    assert result["success"] is False
    assert "LocalRuntime" in result["error"] or "Playwright" in result["error"]


@pytest.mark.asyncio
async def test_login_flow_browser_error_propagates():
    from flaghunter.tools.login_flow import run_login_flow

    class FakeRuntime:
        async def browser_action(self, action, **kw):
            return {"error": "page not found"}

    result = await run_login_flow(
        "http://x",
        "#u",
        "#p",
        "admin",
        "pass",
        runtime=FakeRuntime(),
    )

    assert result["success"] is False


@pytest.fixture
def isolated_notes(tmp_path: Path):
    notes_file = tmp_path / "notes.json"
    set_notes_file(notes_file)
    notes_module._notes.clear()
    notes_module._loaded_notes_file = None
    yield notes_file
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_login_flow_success_returns_structured_cookie_payload(
    isolated_notes, monkeypatch
):
    from flaghunter.tools.login_flow import run_login_flow

    class _DummyAsyncLock:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(notes_module, "_ensure_notes_loaded_unlocked", lambda: None)
    monkeypatch.setattr(notes_module, "_save_notes_unlocked", lambda: None)
    monkeypatch.setattr(notes_module, "_notes_lock", _DummyAsyncLock())

    class FakeRuntime:
        def __init__(self):
            self.calls = []

        async def browser_action(self, action, **kw):
            self.calls.append((action, dict(kw)))

            if action == "navigate":
                return {
                    "url": "http://127.0.0.1:3000/login",
                    "title": "easy_login",
                }

            if action == "submit_form":
                assert kw["fields"] == {
                    "#username": "admin",
                    "#password": "pass",
                }
                assert kw["submit"] == "button[type=submit]"
                return {
                    "submitted": True,
                    "url": "http://127.0.0.1:3000/dashboard",
                    "submit_selector": kw["submit"],
                    "field_selectors": list(kw["fields"].keys()),
                }

            if action == "get_cookies":
                return {
                    "cookie_string": "sid=abc123; theme=light",
                    "cookie_count": 2,
                    "cookie_names": ["sid", "theme"],
                    "cookies": [
                        {"name": "sid", "value": "abc123"},
                        {"name": "theme", "value": "light"},
                    ],
                }

            raise AssertionError(f"unexpected action: {action}")

    runtime = FakeRuntime()
    result = await run_login_flow(
        "http://127.0.0.1:3000/login",
        "#username",
        "#password",
        "admin",
        "pass",
        submit_selector="button[type=submit]",
        runtime=runtime,
    )

    assert result["success"] is True
    assert result["cookie_string"] == "sid=abc123; theme=light"
    assert result["cookie_names"] == ["sid", "theme"]
    assert result["cookie_count"] == 2
    assert result["submitted_url"] == "http://127.0.0.1:3000/dashboard"
    assert result["submitted_via"] == "button[type=submit]"
    assert result["submission"]["field_selectors"] == ["#username", "#password"]
    assert result["submission"]["submit_selector"] == "button[type=submit]"

    assert [action for action, _ in runtime.calls] == [
        "navigate",
        "submit_form",
        "get_cookies",
    ]
