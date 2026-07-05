"""Boundary tests for the claim store adapter skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path
from typing import Any, Iterable, Mapping

from flaghunter.ports import ClaimStorePort


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "flaghunter" / "adapters" / "storage" / "claim_store_adapter.py"

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


class RecordingClaimStore:
    def __init__(self) -> None:
        self.create_calls: list[tuple[str, Mapping[str, Any]]] = []
        self.find_calls: list[tuple[str | None, str | None]] = []
        self.trace_calls: list[tuple[str, Mapping[str, Any]]] = []

    def create_candidate_claim(
        self,
        kind: str,
        content: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.create_calls.append((kind, content))
        return {
            "schemaVersion": "challenge.claim.v1",
            "claimId": "claim-1",
            "kind": kind,
            "content": content,
            "status": "candidate",
        }

    def find_claims(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
    ) -> Iterable[Mapping[str, Any]]:
        self.find_calls.append((kind, status))
        return (
            {
                "schemaVersion": "challenge.claim.v1",
                "claimId": "claim-1",
                "kind": kind,
                "status": status,
            },
        )

    def append_evidence_trace(
        self,
        claim_id: str,
        evidence: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.trace_calls.append((claim_id, evidence))
        return {
            "schemaVersion": "challenge.evidence_trace.v1",
            "claimId": claim_id,
            "evidence": evidence,
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


def test_claim_store_adapter_delegates_to_injected_port() -> None:
    module = importlib.import_module("flaghunter.adapters.storage.claim_store_adapter")
    package = importlib.import_module("flaghunter.adapters.storage")
    store = RecordingClaimStore()
    adapter = module.ClaimStoreAdapter(store)
    content = {
        "schemaVersion": "challenge.claim_content.v1",
        "claimValue": "answer-1",
    }
    evidence = {
        "schemaVersion": "challenge.evidence.v1",
        "evidenceRef": "memory://evidence-1",
    }

    created = adapter.create_candidate_claim("answer", content)
    found = list(adapter.find_claims(kind="answer", status="candidate"))
    traced = adapter.append_evidence_trace("claim-1", evidence)

    assert package.ClaimStoreAdapter is module.ClaimStoreAdapter
    assert isinstance(adapter, ClaimStorePort)
    assert store.create_calls == [("answer", content)]
    assert store.find_calls == [("answer", "candidate")]
    assert store.trace_calls == [("claim-1", evidence)]
    assert created == {
        "schemaVersion": "challenge.claim.v1",
        "claimId": "claim-1",
        "kind": "answer",
        "content": content,
        "status": "candidate",
    }
    assert found == [
        {
            "schemaVersion": "challenge.claim.v1",
            "claimId": "claim-1",
            "kind": "answer",
            "status": "candidate",
        },
    ]
    assert traced == {
        "schemaVersion": "challenge.evidence_trace.v1",
        "claimId": "claim-1",
        "evidence": evidence,
    }


def test_claim_store_adapter_has_no_concrete_or_action_imports() -> None:
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
