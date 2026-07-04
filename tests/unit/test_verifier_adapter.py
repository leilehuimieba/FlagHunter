"""Boundary tests for the verifier adapter skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path
from typing import Any, Mapping

from flaghunter.ports import VerifierPort


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "flaghunter" / "adapters" / "proof" / "verifier_adapter.py"

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

FORBIDDEN_PROOF_AUTHORITY_TOKENS = {
    "upgrade_claim_to_verified",
    "append_verification_record",
    "append_proof_record",
    "confirm_claim",
    'level="verified"',
    "level='verified'",
    "verified_flags",
}


class RecordingVerifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    async def review_claim(
        self,
        claim_id: str,
        evidence: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls.append((claim_id, evidence))
        return {
            "schemaVersion": "challenge.claim_review.v1",
            "claimId": claim_id,
            "reviewStatus": "needs_more_evidence",
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


async def test_verifier_adapter_delegates_to_injected_port() -> None:
    module = importlib.import_module("flaghunter.adapters.proof.verifier_adapter")
    package = importlib.import_module("flaghunter.adapters.proof")
    verifier = RecordingVerifier()
    adapter = module.VerifierAdapter(verifier)
    evidence = {
        "schemaVersion": "challenge.evidence.v1",
        "evidenceRef": "memory://evidence-1",
    }

    review = await adapter.review_claim("claim-1", evidence)

    assert package.VerifierAdapter is module.VerifierAdapter
    assert isinstance(adapter, VerifierPort)
    assert verifier.calls == [("claim-1", evidence)]
    assert review == {
        "schemaVersion": "challenge.claim_review.v1",
        "claimId": "claim-1",
        "reviewStatus": "needs_more_evidence",
        "evidence": evidence,
    }


def test_verifier_adapter_has_no_concrete_or_proof_authority_imports() -> None:
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
        ("proof-authority", token)
        for token in FORBIDDEN_PROOF_AUTHORITY_TOKENS
        if token in text
    )

    assert offenders == []
