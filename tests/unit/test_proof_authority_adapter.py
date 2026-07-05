"""Boundary tests for the proof authority adapter skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path
from typing import Any, Mapping

from flaghunter.ports import ProofAuthorityPort


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "flaghunter" / "adapters" / "proof" / "proof_authority_adapter.py"

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

FORBIDDEN_PROOF_IMPLEMENTATION_TOKENS = {
    "upgrade_claim_to_verified",
    "append_verification_record",
    'level="verified"',
    "level='verified'",
    "verified_flags",
}


class RecordingProofAuthority:
    def __init__(self) -> None:
        self.record_calls: list[tuple[str, Mapping[str, Any]]] = []
        self.confirm_calls: list[tuple[str, str]] = []

    def append_proof_record(
        self,
        claim_id: str,
        record: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.record_calls.append((claim_id, record))
        return {
            "schemaVersion": "challenge.proof_record.v1",
            "claimId": claim_id,
            "recordId": "proof-record-1",
            "record": record,
        }

    def confirm_claim(
        self,
        claim_id: str,
        *,
        record_id: str,
    ) -> Mapping[str, Any]:
        self.confirm_calls.append((claim_id, record_id))
        return {
            "schemaVersion": "challenge.claim_confirmation.v1",
            "claimId": claim_id,
            "recordId": record_id,
            "outcome": "accepted",
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


def test_proof_authority_adapter_delegates_to_injected_port() -> None:
    module = importlib.import_module("flaghunter.adapters.proof.proof_authority_adapter")
    package = importlib.import_module("flaghunter.adapters.proof")
    authority = RecordingProofAuthority()
    adapter = module.ProofAuthorityAdapter(authority)
    record = {
        "schemaVersion": "challenge.proof_record.v1",
        "proofRef": "memory://proof-1",
        "basis": "reviewed-evidence",
    }

    appended = adapter.append_proof_record("claim-1", record)
    confirmed = adapter.confirm_claim("claim-1", record_id="proof-record-1")

    assert package.ProofAuthorityAdapter is module.ProofAuthorityAdapter
    assert isinstance(adapter, ProofAuthorityPort)
    assert authority.record_calls == [("claim-1", record)]
    assert authority.confirm_calls == [("claim-1", "proof-record-1")]
    assert appended == {
        "schemaVersion": "challenge.proof_record.v1",
        "claimId": "claim-1",
        "recordId": "proof-record-1",
        "record": record,
    }
    assert confirmed == {
        "schemaVersion": "challenge.claim_confirmation.v1",
        "claimId": "claim-1",
        "recordId": "proof-record-1",
        "outcome": "accepted",
    }


def test_proof_authority_adapter_has_no_concrete_or_upgrade_implementation_imports() -> None:
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
        ("proof-implementation", token)
        for token in FORBIDDEN_PROOF_IMPLEMENTATION_TOKENS
        if token in text
    )

    assert offenders == []
