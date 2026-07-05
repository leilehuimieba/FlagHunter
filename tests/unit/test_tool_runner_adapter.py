"""Boundary tests for the tool runner adapter skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path
from typing import Any, Mapping

from flaghunter.ports import ToolRunnerPort


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "flaghunter" / "adapters" / "tools" / "tool_runner_adapter.py"

FORBIDDEN_IMPORT_PREFIXES = (
    "flaghunter.agents",
    "flaghunter.eval",
    "flaghunter.interface",
    "flaghunter.mcp",
    "flaghunter.redteam",
    "flaghunter.runtime",
    "flaghunter.session",
    "flaghunter.tools",
)

FORBIDDEN_ACTION_TOKENS = {
    "ToolExecutor",
    "execute_tools",
    "_execute_tools",
    "subprocess",
    "asyncio.subprocess",
    "Playwright",
    "requests",
    "httpx",
    "socket",
    "open(",
    "write_text",
}

FORBIDDEN_PROOF_ACTION_TOKENS = {
    "verification_decision",
    "upgrade_claim_to_verified",
    "append_verification_record",
    'level="verified"',
    "level='verified'",
    "verified_flags",
}


class RecordingRunner:
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
            "toolName": name,
            "arguments": payload,
            "outcome": "completed",
        }


def _parse(path: Path) -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _imported_module_names(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append("." * node.level + (node.module or ""))
    return modules


async def test_tool_runner_adapter_delegates_to_injected_port() -> None:
    module = importlib.import_module("flaghunter.adapters.tools.tool_runner_adapter")
    package = importlib.import_module("flaghunter.adapters.tools")
    runner = RecordingRunner()
    adapter = module.ToolRunnerAdapter(runner)

    result = await adapter.run_tool("inspect", {"target": "example"})

    assert package.ToolRunnerAdapter is module.ToolRunnerAdapter
    assert isinstance(adapter, ToolRunnerPort)
    assert runner.calls == [("inspect", {"target": "example"})]
    assert result == {
        "schemaVersion": "challenge.tool_run_receipt.v1",
        "toolName": "inspect",
        "arguments": {"target": "example"},
        "outcome": "completed",
    }


def test_tool_runner_adapter_has_no_concrete_or_action_imports() -> None:
    tree = _parse(ADAPTER_PATH)
    offenders: list[tuple[str, str]] = []

    for imported in _imported_module_names(tree):
        normalized = imported.lstrip(".")
        if normalized.startswith(FORBIDDEN_IMPORT_PREFIXES):
            offenders.append(("import", imported))

    text = ADAPTER_PATH.read_text(encoding="utf-8")
    offenders.extend(
        ("action", token)
        for token in FORBIDDEN_ACTION_TOKENS
        if token in text
    )
    offenders.extend(
        ("proof", token)
        for token in FORBIDDEN_PROOF_ACTION_TOKENS
        if token in text
    )

    assert offenders == []
