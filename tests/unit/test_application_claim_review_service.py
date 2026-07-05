"""Boundary tests for the claim review application service."""

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


class RecordingVerifier:
    def __init__(self, result: Mapping[str, Any]) -> None:
        self.result = dict(result)
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    async def review_claim(
        self,
        claim_id: str,
        evidence: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls.append((claim_id, evidence))
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


def test_claim_review_service_is_importable_and_reexported() -> None:
    package = importlib.import_module("flaghunter.application.challenge")
    module = importlib.import_module("flaghunter.application.challenge.claim_review_service")

    assert module.ReviewClaim.__name__ == "ReviewClaim"
    assert package.ReviewClaim is module.ReviewClaim


@pytest.mark.asyncio
async def test_review_returns_neutral_payload_without_verifier() -> None:
    from flaghunter.application.challenge.claim_review_service import ReviewClaim
    from flaghunter.domain.challenge.contracts.claims import ChallengeClaim

    claim = ChallengeClaim(
        claim_id="claim-1",
        claim_type="answer",
        claim_value="answer-value",
        evidence_refs=["evidence-1"],
    )

    payload = await ReviewClaim().review(
        claim=claim,
        evidence={"evidenceId": "evidence-1", "score": 0.4},
    )

    assert payload == {
        "schemaVersion": 1,
        "claimId": "claim-1",
        "claim": claim.to_dict(),
        "evidence": {"evidenceId": "evidence-1", "score": 0.4},
        "review": {},
    }


@pytest.mark.asyncio
async def test_review_delegates_to_verifier_port_without_proof_write() -> None:
    from flaghunter.application.challenge.claim_review_service import ReviewClaim
    from flaghunter.domain.challenge.contracts.claims import ChallengeClaim

    verifier = RecordingVerifier(
        {
            "schemaVersion": 1,
            "outcome": "needs_more_evidence",
            "reason": "source missing",
        }
    )
    claim = ChallengeClaim(
        claim_id="claim-2",
        claim_type="answer",
        claim_value={"answerValue": "candidate"},
    )
    evidence = {"evidenceId": "evidence-2", "artifactRef": "artifact-2"}

    payload = await ReviewClaim(verifier=verifier).review(
        claim=claim,
        evidence=evidence,
    )

    assert verifier.calls == [("claim-2", evidence)]
    assert payload == {
        "schemaVersion": 1,
        "claimId": "claim-2",
        "claim": claim.to_dict(),
        "evidence": evidence,
        "review": {
            "schemaVersion": 1,
            "outcome": "needs_more_evidence",
            "reason": "source missing",
        },
    }


@pytest.mark.asyncio
async def test_review_accepts_minimal_empty_inputs() -> None:
    from flaghunter.application.challenge.claim_review_service import ReviewClaim
    from flaghunter.domain.challenge.contracts.claims import ChallengeClaim

    payload = await ReviewClaim().review(
        claim=ChallengeClaim(claim_id="", claim_type="", claim_value=None),
    )

    assert payload == {
        "schemaVersion": 1,
        "claimId": "",
        "claim": {
            "schemaVersion": 1,
            "claimId": "",
            "claimType": "",
            "claimValue": None,
            "status": "candidate",
            "evidenceRefs": [],
            "artifactRefs": [],
            "metadata": {},
        },
        "evidence": {},
        "review": {},
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


def test_claim_review_service_is_small_and_has_no_private_runtime_hooks() -> None:
    from flaghunter.application.challenge.claim_review_service import ReviewClaim

    public_methods = {
        name
        for name, member in inspect.getmembers(
            ReviewClaim,
            predicate=inspect.isfunction,
        )
        if not name.startswith("_")
    }

    assert public_methods == {"review"}
