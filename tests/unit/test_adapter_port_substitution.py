"""Adapter substitution fixtures that avoid production wiring."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.adapters.runtime.runtime_action_adapter import RuntimeActionAdapter
from flaghunter.adapters.tools.tool_runner_adapter import ToolRunnerAdapter
from flaghunter.ports import RuntimeActionPort, ToolRunnerPort


class FirstToolRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run_tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        payload = dict(arguments)
        self.calls.append((name, payload))
        return {
            "schemaVersion": "challenge.tool_run_receipt.v1",
            "runner": "first",
            "toolName": name,
            "arguments": payload,
        }


class SecondToolRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run_tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        payload = dict(arguments)
        self.calls.append((name, payload))
        return {
            "schemaVersion": "challenge.tool_run_receipt.v1",
            "runner": "second",
            "toolName": name,
            "arguments": payload,
        }


class FirstRuntimeAction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float | None]] = []

    async def run_command(
        self,
        command: str,
        *,
        timeout_seconds: float | None = None,
    ) -> Mapping[str, Any]:
        self.calls.append((command, timeout_seconds))
        return {
            "schemaVersion": "challenge.runtime_action_receipt.v1",
            "runtime": "first",
            "command": command,
            "timeoutSeconds": timeout_seconds,
        }


class SecondRuntimeAction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float | None]] = []

    async def run_command(
        self,
        command: str,
        *,
        timeout_seconds: float | None = None,
    ) -> Mapping[str, Any]:
        self.calls.append((command, timeout_seconds))
        return {
            "schemaVersion": "challenge.runtime_action_receipt.v1",
            "runtime": "second",
            "command": command,
            "timeoutSeconds": timeout_seconds,
        }


async def test_tool_runner_adapter_substitutes_injected_ports_without_wiring() -> None:
    first_runner = FirstToolRunner()
    second_runner = SecondToolRunner()
    first_adapter = ToolRunnerAdapter(first_runner)
    second_adapter = ToolRunnerAdapter(second_runner)

    first_result = await first_adapter.run_tool("inspect", {"target": "alpha"})
    second_result = await second_adapter.run_tool("inspect", {"target": "beta"})

    assert isinstance(first_adapter, ToolRunnerPort)
    assert isinstance(second_adapter, ToolRunnerPort)
    assert first_runner.calls == [("inspect", {"target": "alpha"})]
    assert second_runner.calls == [("inspect", {"target": "beta"})]
    assert first_result == {
        "schemaVersion": "challenge.tool_run_receipt.v1",
        "runner": "first",
        "toolName": "inspect",
        "arguments": {"target": "alpha"},
    }
    assert second_result == {
        "schemaVersion": "challenge.tool_run_receipt.v1",
        "runner": "second",
        "toolName": "inspect",
        "arguments": {"target": "beta"},
    }


async def test_runtime_action_adapter_substitutes_injected_ports_without_wiring() -> None:
    first_runtime = FirstRuntimeAction()
    second_runtime = SecondRuntimeAction()
    first_adapter = RuntimeActionAdapter(first_runtime)
    second_adapter = RuntimeActionAdapter(second_runtime)

    first_result = await first_adapter.run_command("echo alpha", timeout_seconds=1.0)
    second_result = await second_adapter.run_command("echo beta", timeout_seconds=2.0)

    assert isinstance(first_adapter, RuntimeActionPort)
    assert isinstance(second_adapter, RuntimeActionPort)
    assert first_runtime.calls == [("echo alpha", 1.0)]
    assert second_runtime.calls == [("echo beta", 2.0)]
    assert first_result == {
        "schemaVersion": "challenge.runtime_action_receipt.v1",
        "runtime": "first",
        "command": "echo alpha",
        "timeoutSeconds": 1.0,
    }
    assert second_result == {
        "schemaVersion": "challenge.runtime_action_receipt.v1",
        "runtime": "second",
        "command": "echo beta",
        "timeoutSeconds": 2.0,
    }
