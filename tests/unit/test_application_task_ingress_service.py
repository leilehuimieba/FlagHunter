"""Boundary tests for the task ingress application service."""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from typing import Any, Mapping

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROOT = REPO_ROOT / "flaghunter" / "application"
PLAYBOOK_PATH = (
    REPO_ROOT
    / "docs"
    / "dev"
    / "FlagHunter_Clean_Architecture_Migration_Playbook_v0.1_2026-07-04.md"
)

FORBIDDEN_IMPORT_PREFIXES = (
    "flaghunter.adapters",
    "flaghunter.agents",
    "flaghunter.config",
    "flaghunter.interface",
    "flaghunter.knowledge",
    "flaghunter.llm",
    "flaghunter.mcp",
    "flaghunter.runtime",
    "flaghunter.session",
    "flaghunter.tools",
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


class RecordingTaskIngress:
    def __init__(self, result: Mapping[str, Any]) -> None:
        self.result = dict(result)
        self.requests: list[Mapping[str, Any]] = []

    async def submit_task(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
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


def test_task_ingress_service_is_importable_and_reexported() -> None:
    package = importlib.import_module("flaghunter.application.challenge")
    module = importlib.import_module("flaghunter.application.challenge.task_ingress_service")

    assert module.SubmitTaskIngress.__name__ == "SubmitTaskIngress"
    assert package.SubmitTaskIngress is module.SubmitTaskIngress


@pytest.mark.asyncio
async def test_submit_returns_pending_payload_without_ingress_port() -> None:
    from flaghunter.application.challenge.task_ingress_service import SubmitTaskIngress

    payload = await SubmitTaskIngress().submit(
        task_id="task-1",
        task_type="review",
        instructions="Review current read model",
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
            "instructions": "Review current read model",
            "runId": "run-1",
            "metadata": {"priority": 2},
        },
        "ingress": {},
    }


@pytest.mark.asyncio
async def test_submit_delegates_to_task_ingress_port_only() -> None:
    from flaghunter.application.challenge.task_ingress_service import SubmitTaskIngress

    ingress = RecordingTaskIngress(
        {
            "schemaVersion": 1,
            "receiptId": "ingress-1",
            "status": "accepted",
        }
    )

    payload = await SubmitTaskIngress(task_ingress=ingress).submit(
        task_id="task-2",
        task_type="dispatch",
        instructions="Submit neutral task",
        run_id="run-2",
        metadata={"lane": "ingress"},
    )

    assert ingress.requests == [
        {
            "schemaVersion": 1,
            "taskId": "task-2",
            "taskType": "dispatch",
            "instructions": "Submit neutral task",
            "runId": "run-2",
            "metadata": {"lane": "ingress"},
        }
    ]
    assert payload == {
        "schemaVersion": 1,
        "taskId": "task-2",
        "request": ingress.requests[0],
        "ingress": {
            "schemaVersion": 1,
            "receiptId": "ingress-1",
            "status": "accepted",
        },
    }


@pytest.mark.asyncio
async def test_submit_accepts_minimal_empty_values() -> None:
    from flaghunter.application.challenge.task_ingress_service import SubmitTaskIngress

    payload = await SubmitTaskIngress().submit(
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
        "ingress": {},
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


def test_task_ingress_service_is_small_and_has_no_private_runtime_hooks() -> None:
    from flaghunter.application.challenge.task_ingress_service import SubmitTaskIngress

    public_methods = {
        name
        for name, member in inspect.getmembers(
            SubmitTaskIngress,
            predicate=inspect.isfunction,
        )
        if not name.startswith("_")
    }

    assert public_methods == {"submit"}


def test_task_ingress_service_contract_migration_pre_approval_guard() -> None:
    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    source_path = APPLICATION_ROOT / "challenge" / "task_ingress_service.py"
    source = source_path.read_text(encoding="utf-8")

    assert "Task ingress service contract migration pre-approval guard" in playbook
    assert "Status: pre-approval guard active, implementation not approved." in playbook

    forbidden_tokens = {
        "from flaghunter.domain.challenge.contracts.task_ingress",
        "TaskIngressRequest",
        "TaskIngressReceipt",
        "TaskIngressReadback",
    }

    offenders = sorted(token for token in forbidden_tokens if token in source)

    assert offenders == []
