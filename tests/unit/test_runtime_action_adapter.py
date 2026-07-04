"""Boundary tests for the runtime action adapter skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path
from typing import Any, Mapping

from flaghunter.ports import RuntimeActionPort


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "flaghunter" / "adapters" / "runtime" / "runtime_action_adapter.py"

FORBIDDEN_IMPORT_PREFIXES = (
    "flaghunter.agents",
    "flaghunter.interface",
    "flaghunter.mcp",
    "flaghunter.runtime",
    "flaghunter.session",
    "flaghunter.tools",
)

FORBIDDEN_ACTION_TOKENS = {
    "LocalRuntime",
    "DockerRuntime",
    "SSHRuntime",
    "ToolExecutor",
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


class RecordingRuntime:
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
            "command": command,
            "timeoutSeconds": timeout_seconds,
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


async def test_runtime_action_adapter_delegates_to_injected_port() -> None:
    module = importlib.import_module("flaghunter.adapters.runtime.runtime_action_adapter")
    package = importlib.import_module("flaghunter.adapters.runtime")
    runtime = RecordingRuntime()
    adapter = module.RuntimeActionAdapter(runtime)

    result = await adapter.run_command("echo hello", timeout_seconds=3.5)

    assert package.RuntimeActionAdapter is module.RuntimeActionAdapter
    assert isinstance(adapter, RuntimeActionPort)
    assert runtime.calls == [("echo hello", 3.5)]
    assert result == {
        "schemaVersion": "challenge.runtime_action_receipt.v1",
        "command": "echo hello",
        "timeoutSeconds": 3.5,
        "outcome": "completed",
    }


def test_runtime_action_adapter_has_no_concrete_or_action_imports() -> None:
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
