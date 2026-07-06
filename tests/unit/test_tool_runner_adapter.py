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


def _class_method(
    tree: ast.Module,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if (
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == method_name
            ):
                return item
    raise AssertionError(f"{class_name}.{method_name} was not found")


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


def test_tool_runner_adapter_run_tool_body_remains_direct_delegate_only() -> None:
    tree = _parse(ADAPTER_PATH)
    method = _class_method(tree, "ToolRunnerAdapter", "run_tool")
    assert len(method.body) == 1
    assert isinstance(method.body[0], ast.Return)
    assert isinstance(method.body[0].value, ast.Await)
    call = method.body[0].value.value
    assert isinstance(call, ast.Call)
    assert isinstance(call.func, ast.Attribute)
    assert call.func.attr == "run_tool"
    assert isinstance(call.func.value, ast.Attribute)
    assert call.func.value.attr == "_runner"
    assert isinstance(call.func.value.value, ast.Name)
    assert call.func.value.value.id == "self"
    assert [arg.id for arg in call.args if isinstance(arg, ast.Name)] == [
        "name",
        "arguments",
    ]
    assert call.keywords == []

    forbidden_nodes = (
        ast.Assign,
        ast.AugAssign,
        ast.If,
        ast.For,
        ast.While,
        ast.Try,
        ast.With,
        ast.Raise,
    )
    offenders = [
        type(node).__name__
        for node in ast.walk(method)
        if isinstance(node, forbidden_nodes)
    ]
    assert offenders == []
