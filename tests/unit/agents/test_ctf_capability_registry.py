from __future__ import annotations

from types import SimpleNamespace

import pytest

from pentestagent.agents.pa_agent.capability_registry import CapabilityRegistry
from pentestagent.tools.tool_guard import ToolStatus


class _FakeToolGuard:
    def __init__(self, availability: dict[str, bool]):
        self.availability = availability
        self.runtime = None

    def check(self, tool_name: str) -> ToolStatus:
        available = bool(self.availability.get(tool_name, False))
        return ToolStatus(
            available=available,
            path=f"fake:{tool_name}" if available else None,
            version="test" if available else None,
        )

    def suggest_install(self, tool_name: str) -> str:
        return f"install {tool_name}"


@pytest.mark.asyncio
async def test_capability_registry_prefers_degradation_over_install_for_sqli():
    registry = CapabilityRegistry.build_default(
        runtime=SimpleNamespace(),
        tool_guard=_FakeToolGuard(
            {
                "sqlmap": False,
                "http_request": True,
                "terminal": True,
                "curl": True,
                "browser": False,
            }
        ),
    )

    await registry.full_check()
    choice = registry.best_available("sql_injection_test")
    decision = registry.resolve_execution_route("sql_injection_test")

    assert choice is not None
    assert choice.method == "manual_payload_via_requests"
    assert choice.quality == "medium"
    assert decision.decision_type == "degrade"
    assert decision.best_available is not None
    assert decision.best_available.method == "manual_payload_via_requests"
    assert registry.missing_tools_for("sql_injection_test")["sqlmap"].available is False


@pytest.mark.asyncio
async def test_capability_registry_keeps_http_request_basic_when_browser_unavailable():
    registry = CapabilityRegistry.build_default(
        runtime=SimpleNamespace(),
        tool_guard=_FakeToolGuard(
            {
                "http_request": True,
                "terminal": True,
                "curl": True,
                "browser": False,
                "ffuf": False,
            }
        ),
    )

    await registry.full_check()

    http_choice = registry.best_available("http_request_basic")
    browser_choice = registry.best_available("http_request_browser")
    http_decision = registry.resolve_execution_route("http_request_basic")
    browser_decision = registry.resolve_execution_route("http_request_browser")

    assert http_choice is not None
    assert http_choice.method == "requests_via_runtime"
    assert browser_choice is None
    assert http_decision.decision_type == "use_best"
    assert browser_decision.decision_type == "install"
    assert "browser" in browser_decision.missing_tools


@pytest.mark.asyncio
async def test_capability_registry_browser_probe_marks_html_fetch_only_as_degraded():
    runtime = SimpleNamespace()

    async def _browser_action(action: str, **kwargs):
        assert action == "diagnose"
        return {
            "available": True,
            "engine": "cli_fetch",
            "mode": "html_fetch_only",
            "rendered_dom": False,
            "js_execution": False,
            "supports_actions": ["navigate", "get_content", "get_forms"],
        }

    runtime.browser_action = _browser_action

    guard = _FakeToolGuard({"browser": True, "http_request": True})
    guard.runtime = runtime
    registry = CapabilityRegistry.build_default(
        runtime=runtime,
        tool_guard=guard,
    )

    await registry.full_check()

    browser_entry = registry.capability_table["browser"]
    browser_choice = registry.best_available("http_request_browser")
    js_choice = registry.best_available("js_execution_in_context")

    assert browser_entry.is_available is True
    assert browser_entry.health_state == "degraded"
    assert browser_choice is None
    assert js_choice is None


@pytest.mark.asyncio
async def test_capability_registry_marks_primitive_unavailable_without_install_path():
    registry = CapabilityRegistry.for_testing(
        {
            "custom_primitive": [
                {
                    "method": "manual_only",
                    "quality": "low",
                    "available": False,
                    "requires_install": False,
                    "tool_names": ["nonexistent_tool"],
                }
            ]
        },
        runtime=SimpleNamespace(),
        tool_guard=_FakeToolGuard({}),
    )

    await registry.full_check()
    decision = registry.resolve_execution_route("custom_primitive")

    assert decision.decision_type == "unavailable"
    assert decision.best_available is None
    assert decision.install_candidates == []


@pytest.mark.asyncio
async def test_capability_registry_resolves_sqlmap_tool_request_to_degrade():
    registry = CapabilityRegistry.build_default(
        runtime=SimpleNamespace(),
        tool_guard=_FakeToolGuard(
            {
                "sqlmap": False,
                "http_request": True,
                "terminal": True,
                "curl": True,
            }
        ),
    )

    await registry.full_check()
    decision = registry.resolve_tool_request("sqlmap")

    assert decision.decision_type == "degrade"
    assert decision.fallback_tool == "manual_sqli_payload"
    assert decision.entry is not None
    assert decision.entry.is_available is False


@pytest.mark.asyncio
async def test_capability_registry_resolves_unknown_tool_request_to_install_or_unavailable():
    registry = CapabilityRegistry.build_default(
        runtime=SimpleNamespace(),
        tool_guard=_FakeToolGuard({"metasploit": False}),
    )

    await registry.full_check()
    decision = registry.resolve_tool_request("metasploit")

    assert decision.decision_type in {"install", "unavailable"}
    assert decision.entry is not None
    assert decision.entry.is_available is False
