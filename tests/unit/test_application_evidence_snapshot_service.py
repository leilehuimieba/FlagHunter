"""Boundary tests for the evidence snapshot application service."""

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
    def __init__(self, events: Iterable[Mapping[str, Any]]) -> None:
        self.events = list(events)
        self.appended_events: list[Mapping[str, Any]] = []
        self.queries: list[Mapping[str, Any] | None] = []

    def append_event(self, event: Mapping[str, Any]) -> Mapping[str, Any]:
        self.appended_events.append(event)
        raise AssertionError("snapshot service must not append audit events")

    def query_events(
        self,
        filters: Mapping[str, Any] | None = None,
    ) -> Iterable[Mapping[str, Any]]:
        self.queries.append(filters)
        if not filters or filters.get("runId") is None:
            return list(self.events)
        return [
            event
            for event in self.events
            if event.get("runId") in (None, filters.get("runId"))
        ]


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


def test_evidence_snapshot_service_is_importable_and_reexported() -> None:
    package = importlib.import_module("flaghunter.application.challenge")
    module = importlib.import_module(
        "flaghunter.application.challenge.evidence_snapshot_service"
    )

    assert module.BuildEvidenceSnapshot.__name__ == "BuildEvidenceSnapshot"
    assert package.BuildEvidenceSnapshot is module.BuildEvidenceSnapshot


def test_build_returns_empty_snapshot_without_store() -> None:
    from flaghunter.application.challenge.evidence_snapshot_service import (
        BuildEvidenceSnapshot,
    )
    from flaghunter.domain.challenge.contracts.evidence_snapshot import EvidenceSnapshot

    snapshot = BuildEvidenceSnapshot().build(run_id="run-1")

    assert isinstance(snapshot, EvidenceSnapshot)
    assert snapshot.to_dict() == {
        "schemaVersion": "p2.evidence_snapshot.v1",
        "traceRefs": [],
        "claimEvidenceRefs": [],
        "auditEvidenceExport": {},
        "p3SolveSnapshot": {},
        "summary": {
            "claimCount": 0,
            "traceCount": 0,
            "verificationRecordCount": 0,
            "hasVerifiedClaim": False,
            "hasControlReceipt": False,
            "hasToolReceipt": False,
            "hasVerificationReceipt": False,
            "truncated": {
                "traceRefs": 0,
                "claimEvidenceRefs": 0,
                "auditClaims": 0,
                "auditTraces": 0,
                "auditVerificationRecords": 0,
            },
        },
    }


def test_build_collects_trace_and_claim_evidence_refs_from_audit_port() -> None:
    from flaghunter.application.challenge.evidence_snapshot_service import (
        BuildEvidenceSnapshot,
    )

    audit_store = RecordingAuditStore(
        [
            {
                "eventId": "event-1",
                "eventType": "taskReceiptRecorded",
                "runId": "run-1",
                "traceKind": "tool_receipt",
                "traceRef": {"eventId": "event-1", "kind": "tool_receipt"},
            },
            {
                "eventId": "event-2",
                "eventType": "evidenceObserved",
                "runId": "run-1",
                "claimEvidenceRef": {"evidenceId": "evidence-1", "claimId": "claim-1"},
            },
            {
                "eventId": "event-x",
                "eventType": "taskReceiptRecorded",
                "runId": "run-x",
                "traceRef": {"eventId": "event-x"},
            },
        ]
    )
    service = BuildEvidenceSnapshot(audit_store=audit_store)

    snapshot = service.build(run_id="run-1")
    payload = snapshot.to_dict()

    assert audit_store.queries == [{"runId": "run-1"}]
    assert audit_store.appended_events == []
    assert payload["schemaVersion"] == "p2.evidence_snapshot.v1"
    assert payload["traceRefs"] == [{"eventId": "event-1", "kind": "tool_receipt"}]
    assert payload["claimEvidenceRefs"] == [
        {"evidenceId": "evidence-1", "claimId": "claim-1"}
    ]
    assert payload["auditEvidenceExport"] == {
        "schemaVersion": 1,
        "summary": {
            "claimCount": 1,
            "executionTraceCount": 1,
            "verificationRecordCount": 0,
        },
    }
    assert payload["summary"]["hasToolReceipt"] is True
    assert payload == snapshot.from_dict(payload).to_dict()


def test_build_truncates_refs_without_losing_summary_counts() -> None:
    from flaghunter.application.challenge.evidence_snapshot_service import (
        BuildEvidenceSnapshot,
    )

    audit_store = RecordingAuditStore(
        [
            {"traceRef": {"eventId": "trace-1"}, "claimEvidenceRef": {"id": "claim-1"}},
            {"traceRef": {"eventId": "trace-2"}, "claimEvidenceRef": {"id": "claim-2"}},
        ]
    )

    payload = BuildEvidenceSnapshot(audit_store=audit_store).build(
        trace_limit=1,
        claim_evidence_limit=1,
    ).to_dict()

    assert payload["traceRefs"] == [{"eventId": "trace-1"}]
    assert payload["claimEvidenceRefs"] == [{"id": "claim-1"}]
    assert payload["auditEvidenceExport"]["summary"] == {
        "claimCount": 2,
        "executionTraceCount": 2,
        "verificationRecordCount": 0,
    }
    assert payload["summary"]["truncated"]["traceRefs"] == 1
    assert payload["summary"]["truncated"]["claimEvidenceRefs"] == 1


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


def test_evidence_snapshot_service_is_small_and_has_no_private_runtime_hooks() -> None:
    from flaghunter.application.challenge.evidence_snapshot_service import (
        BuildEvidenceSnapshot,
    )

    public_methods = {
        name
        for name, member in inspect.getmembers(
            BuildEvidenceSnapshot,
            predicate=inspect.isfunction,
        )
        if not name.startswith("_")
    }

    assert public_methods == {"build"}
