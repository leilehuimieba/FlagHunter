"""Boundary tests for the tool receipt application service."""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROOT = REPO_ROOT / "flaghunter" / "application"

FORBIDDEN_IMPORT_PREFIXES = (
    "flaghunter.agents",
    "flaghunter.eval",
    "flaghunter.tools",
    "flaghunter.runtime",
    "flaghunter.interface",
    "flaghunter.mcp",
    "flaghunter.redteam",
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


class RecordingAuditStore:
    def __init__(self) -> None:
        self.events: list[Mapping[str, Any]] = []

    def append_event(self, event: Mapping[str, Any]) -> Mapping[str, Any]:
        self.events.append(event)
        return dict(event)

    def query_events(
        self,
        filters: Mapping[str, Any] | None = None,
    ) -> Iterable[Mapping[str, Any]]:
        raise AssertionError("tool receipt service should not query audit events")


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


def test_tool_receipt_service_is_importable_and_reexported() -> None:
    package = importlib.import_module("flaghunter.application.challenge")
    module = importlib.import_module("flaghunter.application.challenge.tool_receipt_service")

    assert module.RecordToolReceipt.__name__ == "RecordToolReceipt"
    assert package.RecordToolReceipt is module.RecordToolReceipt


def test_record_returns_task_receipt_without_store() -> None:
    from flaghunter.application.challenge.tool_receipt_service import RecordToolReceipt
    from flaghunter.domain.challenge.contracts.receipts import TaskReceipt

    receipt = RecordToolReceipt().record(
        receipt_id="receipt-1",
        task_id="task-1",
        tool_name="reader",
        outcome="completed",
        summary="Read artifact",
        artifact_refs=["artifact-1"],
        metadata={"duration": 1.25},
    )

    assert isinstance(receipt, TaskReceipt)
    assert receipt.to_dict() == {
        "schemaVersion": 1,
        "receiptId": "receipt-1",
        "taskId": "task-1",
        "outcome": "completed",
        "summary": "Read artifact",
        "artifactRefs": ["artifact-1"],
        "metadata": {"duration": 1.25, "toolName": "reader"},
    }


def test_record_appends_trace_event_through_injected_port() -> None:
    from flaghunter.application.challenge.tool_receipt_service import RecordToolReceipt

    audit_store = RecordingAuditStore()
    receipt = RecordToolReceipt(audit_store=audit_store).record(
        receipt_id="receipt-2",
        task_id="task-2",
        tool_name="browser",
        outcome="skipped",
        run_id="run-1",
        artifact_refs=["artifact-2"],
    )

    assert audit_store.events == [
        {
            "schemaVersion": 1,
            "eventType": "toolReceiptRecorded",
            "runId": "run-1",
            "traceKind": "tool_receipt",
            "traceRef": {
                "receiptId": "receipt-2",
                "taskId": "task-2",
                "toolName": "browser",
            },
            "receipt": receipt.to_dict(),
        }
    ]


def test_record_accepts_minimal_empty_values() -> None:
    from flaghunter.application.challenge.tool_receipt_service import RecordToolReceipt

    receipt = RecordToolReceipt().record(
        receipt_id="",
        task_id="",
        tool_name="",
        outcome="",
    )

    assert receipt.to_dict() == {
        "schemaVersion": 1,
        "receiptId": "",
        "taskId": "",
        "outcome": "",
        "summary": None,
        "artifactRefs": [],
        "metadata": {"toolName": ""},
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


def test_tool_receipt_service_is_small_and_has_no_private_runtime_hooks() -> None:
    from flaghunter.application.challenge.tool_receipt_service import RecordToolReceipt

    public_methods = {
        name
        for name, member in inspect.getmembers(
            RecordToolReceipt,
            predicate=inspect.isfunction,
        )
        if not name.startswith("_")
    }

    assert public_methods == {"record"}
