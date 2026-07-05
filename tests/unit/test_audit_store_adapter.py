"""Boundary tests for the audit store adapter skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path
from typing import Any, Iterable, Mapping

from flaghunter.ports import AuditStorePort


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "flaghunter" / "adapters" / "audit" / "audit_store_adapter.py"

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


class RecordingAuditStore:
    def __init__(self) -> None:
        self.append_calls: list[Mapping[str, Any]] = []
        self.query_calls: list[Mapping[str, Any] | None] = []

    def append_event(
        self,
        event: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.append_calls.append(event)
        return {
            "schemaVersion": "challenge.audit_event.v1",
            "eventId": "event-1",
            "event": event,
        }

    def query_events(
        self,
        filters: Mapping[str, Any] | None = None,
    ) -> Iterable[Mapping[str, Any]]:
        self.query_calls.append(filters)
        return (
            {
                "schemaVersion": "challenge.audit_event.v1",
                "eventId": "event-1",
                "filters": filters,
            },
        )


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


def test_audit_store_adapter_delegates_to_injected_port() -> None:
    module = importlib.import_module("flaghunter.adapters.audit.audit_store_adapter")
    package = importlib.import_module("flaghunter.adapters.audit")
    store = RecordingAuditStore()
    adapter = module.AuditStoreAdapter(store)
    event = {
        "schemaVersion": "challenge.audit_event.v1",
        "eventType": "task.started",
        "runId": "run-1",
    }

    appended = adapter.append_event(event)
    queried = list(adapter.query_events({"runId": "run-1"}))

    assert package.AuditStoreAdapter is module.AuditStoreAdapter
    assert isinstance(adapter, AuditStorePort)
    assert store.append_calls == [event]
    assert store.query_calls == [{"runId": "run-1"}]
    assert appended == {
        "schemaVersion": "challenge.audit_event.v1",
        "eventId": "event-1",
        "event": event,
    }
    assert queried == [
        {
            "schemaVersion": "challenge.audit_event.v1",
            "eventId": "event-1",
            "filters": {"runId": "run-1"},
        },
    ]


def test_audit_store_adapter_has_no_concrete_or_action_imports() -> None:
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
