"""Boundary tests for the task graph runner adapter skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path
from typing import Any, Mapping

from flaghunter.ports import TaskDAGRunnerPort


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "flaghunter" / "adapters" / "crew" / "task_dag_runner_adapter.py"

FORBIDDEN_IMPORT_PREFIXES = (
    "flaghunter.agents",
    "flaghunter.interface",
    "flaghunter.mcp",
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
    "TaskDAGExecutor",
    "task_dag_runner.py",
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


class RecordingTaskGraphRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []

    async def run_ready_task(
        self,
        plan: Mapping[str, Any],
        state_snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls.append((plan, state_snapshot))
        return {
            "schemaVersion": "challenge.task_receipt.v1",
            "taskId": plan["taskId"],
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


async def test_task_dag_runner_adapter_delegates_to_injected_port() -> None:
    module = importlib.import_module("flaghunter.adapters.crew.task_dag_runner_adapter")
    package = importlib.import_module("flaghunter.adapters.crew")
    runner = RecordingTaskGraphRunner()
    adapter = module.TaskDAGRunnerAdapter(runner)
    plan = {
        "schemaVersion": "challenge.task_graph_node.v1",
        "taskId": "task-1",
        "taskKind": "review",
    }
    state_snapshot = {
        "schemaVersion": "challenge.run_snapshot.v1",
        "runId": "run-1",
    }

    receipt = await adapter.run_ready_task(plan, state_snapshot)

    assert package.TaskDAGRunnerAdapter is module.TaskDAGRunnerAdapter
    assert isinstance(adapter, TaskDAGRunnerPort)
    assert runner.calls == [(plan, state_snapshot)]
    assert receipt == {
        "schemaVersion": "challenge.task_receipt.v1",
        "taskId": "task-1",
        "outcome": "completed",
    }


def test_task_dag_runner_adapter_has_no_concrete_or_action_imports() -> None:
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
