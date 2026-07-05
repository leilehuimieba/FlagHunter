"""Boundary tests for the task ingress adapter skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path
from typing import Any, Mapping

from flaghunter.ports import TaskIngressPort


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "flaghunter" / "adapters" / "mcp" / "task_ingress_adapter.py"

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
    "CTFTaskDispatcher",
    "CTFState",
    "CTFVerifier",
    "ToolExecutor",
    "WorkerPool",
    "CrewOrchestrator",
    "LocalRuntime",
    "DockerRuntime",
    "SSHRuntime",
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
    "append_proof_record",
    "confirm_claim",
    'level="verified"',
    "level='verified'",
    "verified_flags",
}


class RecordingTaskIngress:
    def __init__(self) -> None:
        self.calls: list[Mapping[str, Any]] = []

    async def submit_task(
        self,
        request: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls.append(request)
        return {
            "schemaVersion": "challenge.task_ingress_receipt.v1",
            "taskId": request["taskId"],
            "status": "accepted",
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


async def test_task_ingress_adapter_delegates_to_injected_port() -> None:
    module = importlib.import_module("flaghunter.adapters.mcp.task_ingress_adapter")
    package = importlib.import_module("flaghunter.adapters.mcp")
    ingress = RecordingTaskIngress()
    adapter = module.TaskIngressAdapter(ingress)
    request = {
        "schemaVersion": "challenge.task_ingress_request.v1",
        "taskId": "task-1",
        "taskKind": "review",
    }

    receipt = await adapter.submit_task(request)

    assert package.TaskIngressAdapter is module.TaskIngressAdapter
    assert isinstance(adapter, TaskIngressPort)
    assert ingress.calls == [request]
    assert receipt == {
        "schemaVersion": "challenge.task_ingress_receipt.v1",
        "taskId": "task-1",
        "status": "accepted",
    }


def test_task_ingress_adapter_has_no_concrete_or_action_imports() -> None:
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
