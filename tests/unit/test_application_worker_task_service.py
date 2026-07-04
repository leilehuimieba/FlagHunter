"""Boundary tests for the worker task application service."""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from typing import Any, Mapping

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROOT = REPO_ROOT / "flaghunter" / "application"

FORBIDDEN_IMPORT_PREFIXES = (
    "flaghunter.agents",
    "flaghunter.tools",
    "flaghunter.runtime",
    "flaghunter.interface",
    "flaghunter.mcp",
    "flaghunter.session",
    "flaghunter.adapters",
)

FORBIDDEN_ACTION_TOKENS = {
    "subprocess",
    "asyncio.subprocess",
    "execute_tools",
    "_execute_tools",
    "WorkerPool",
    "CTFTaskDispatcher",
    "ToolExecutor",
    "LocalRuntime",
    "DockerRuntime",
    "SSHRuntime",
    "Playwright",
    "write_text",
    "open(",
    "requests",
    "httpx",
    "socket",
}

FORBIDDEN_PROOF_TOKENS = {
    "verification_decision",
    "upgrade_claim_to_verified",
    "append_verification_record",
    "append_proof_record",
    "confirm_claim",
    'level="verified"',
    "level='verified'",
    "verified_flags",
    "ProofAuthorityPort",
}

FORBIDDEN_PUBLIC_DOMAIN_TERMS = {
    "ctf",
    "pentest",
    "exploit",
    "vulnerability",
    "hacking",
    "attack",
    "redteam",
}


class RecordingCrewBridge:
    def __init__(self, result: Mapping[str, Any]) -> None:
        self.result = dict(result)
        self.requests: list[Mapping[str, Any]] = []

    async def dispatch_task(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        self.requests.append(request)
        return dict(self.result)


def _application_sources() -> list[Path]:
    assert APPLICATION_ROOT.is_dir(), "flaghunter.application package must exist"
    return sorted(APPLICATION_ROOT.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _imported_module_names(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append("." * node.level + (node.module or ""))
    return modules


def test_worker_task_service_is_importable_and_reexported() -> None:
    package = importlib.import_module("flaghunter.application.challenge")
    module = importlib.import_module("flaghunter.application.challenge.worker_task_service")

    assert module.DispatchWorkerTask.__name__ == "DispatchWorkerTask"
    assert package.DispatchWorkerTask is module.DispatchWorkerTask


@pytest.mark.asyncio
async def test_dispatch_returns_pending_payload_without_bridge() -> None:
    from flaghunter.application.challenge.worker_task_service import DispatchWorkerTask

    payload = await DispatchWorkerTask().dispatch(
        task_id="task-1",
        task_type="review",
        instructions="Review evidence",
        run_id="run-1",
        metadata={"priority": 2},
    )

    assert payload == {
        "schemaVersion": 1,
        "taskId": "task-1",
        "request": {
            "schemaVersion": 1,
            "taskId": "task-1",
            "taskType": "review",
            "instructions": "Review evidence",
            "runId": "run-1",
            "metadata": {"priority": 2},
        },
        "dispatch": {},
    }


@pytest.mark.asyncio
async def test_dispatch_delegates_to_crew_bridge_port_only() -> None:
    from flaghunter.application.challenge.worker_task_service import DispatchWorkerTask

    bridge = RecordingCrewBridge(
        {
            "schemaVersion": 1,
            "dispatchId": "dispatch-1",
            "state": "queued",
        }
    )

    payload = await DispatchWorkerTask(crew_bridge=bridge).dispatch(
        task_id="task-2",
        task_type="investigate",
        instructions="Collect read model",
        run_id="run-2",
        metadata={"lane": "read-side"},
    )

    assert bridge.requests == [
        {
            "schemaVersion": 1,
            "taskId": "task-2",
            "taskType": "investigate",
            "instructions": "Collect read model",
            "runId": "run-2",
            "metadata": {"lane": "read-side"},
        }
    ]
    assert payload == {
        "schemaVersion": 1,
        "taskId": "task-2",
        "request": bridge.requests[0],
        "dispatch": {
            "schemaVersion": 1,
            "dispatchId": "dispatch-1",
            "state": "queued",
        },
    }


@pytest.mark.asyncio
async def test_dispatch_accepts_minimal_empty_values() -> None:
    from flaghunter.application.challenge.worker_task_service import DispatchWorkerTask

    payload = await DispatchWorkerTask().dispatch(
        task_id="",
        task_type="",
        instructions="",
    )

    assert payload == {
        "schemaVersion": 1,
        "taskId": "",
        "request": {
            "schemaVersion": 1,
            "taskId": "",
            "taskType": "",
            "instructions": "",
            "runId": None,
            "metadata": {},
        },
        "dispatch": {},
    }


def test_application_service_uses_only_inner_contracts_and_ports() -> None:
    offenders: list[tuple[str, str]] = []
    for path in _application_sources():
        for imported in _imported_module_names(_parse(path)):
            normalized = imported.lstrip(".")
            if normalized.startswith(FORBIDDEN_IMPORT_PREFIXES):
                offenders.append((_relative(path), imported))

    assert offenders == []


def test_application_service_contains_no_action_or_proof_authority_surfaces() -> None:
    offenders: list[tuple[str, str]] = []
    for path in _application_sources():
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_ACTION_TOKENS | FORBIDDEN_PROOF_TOKENS
            if token in text
        )

    assert offenders == []


def test_application_public_names_and_docstrings_are_domain_neutral() -> None:
    offenders: list[tuple[str, str, int]] = []
    for path in _application_sources():
        tree = _parse(path)
        module_doc = ast.get_docstring(tree) or ""
        lowered_doc = module_doc.lower()
        offenders.extend(
            (_relative(path), f"module docstring contains {term}", 1)
            for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
            if term in lowered_doc
        )
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                lowered_name = node.name.lower()
                offenders.extend(
                    (_relative(path), f"{node.name} contains {term}", node.lineno)
                    for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                    if term in lowered_name
                )
                docstring = (ast.get_docstring(node) or "").lower()
                offenders.extend(
                    (
                        _relative(path),
                        f"{node.name} docstring contains {term}",
                        node.lineno,
                    )
                    for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                    if term in docstring
                )

    assert offenders == []


def test_worker_task_service_is_small_and_has_no_private_runtime_hooks() -> None:
    from flaghunter.application.challenge.worker_task_service import DispatchWorkerTask

    public_methods = {
        name
        for name, member in inspect.getmembers(
            DispatchWorkerTask,
            predicate=inspect.isfunction,
        )
        if not name.startswith("_")
    }

    assert public_methods == {"dispatch"}
