from __future__ import annotations

import json

import pytest

from pentestagent.tools.registry import get_tool


@pytest.mark.asyncio
async def test_browser_tool_exposes_form_submission_and_cookie_actions():
    import pentestagent.tools.browser  # noqa: F401

    tool = get_tool("browser")
    assert tool is not None

    action_enum = tool.schema.properties["action"]["enum"]
    assert "submit_form" in action_enum
    assert "get_cookies" in action_enum
    assert "fields" in tool.schema.properties
    assert "submit" in tool.schema.properties

    class FakeRuntime:
        def __init__(self):
            self.calls = []

        async def browser_action(self, action, **kwargs):
            self.calls.append((action, dict(kwargs)))

            if action == "submit_form":
                assert kwargs["fields"] == {
                    "#username": "admin",
                    "#password": "pass",
                }
                assert kwargs["submit"] == "button[type=submit]"
                return {
                    "submitted": True,
                    "url": "http://127.0.0.1:3000/dashboard",
                    "submit_selector": kwargs["submit"],
                    "field_selectors": list(kwargs["fields"].keys()),
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

    submit_result = await tool.execute(
        {
            "action": "submit_form",
            "fields": {
                "#username": "admin",
                "#password": "pass",
            },
            "submit": "button[type=submit]",
        },
        runtime,
    )
    submit_payload = json.loads(submit_result)
    assert submit_payload == {
        "action": "submit_form",
        "field_selectors": ["#username", "#password"],
        "submitted": True,
        "submit_selector": "button[type=submit]",
        "url": "http://127.0.0.1:3000/dashboard",
    }

    cookie_result = await tool.execute({"action": "get_cookies"}, runtime)
    cookie_payload = json.loads(cookie_result)
    assert cookie_payload == {
        "action": "get_cookies",
        "cookie_count": 2,
        "cookie_names": ["sid", "theme"],
        "cookie_string": "sid=abc123; theme=light",
    }

    assert [action for action, _ in runtime.calls] == [
        "submit_form",
        "get_cookies",
    ]
