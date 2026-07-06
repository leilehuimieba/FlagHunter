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


def _class_method(
    tree: ast.Module,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if (
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == method_name
            ):
                return item
    raise AssertionError(f"{class_name}.{method_name} was not found")


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


def test_verifier_adapter_review_claim_body_remains_direct_delegate_only() -> None:
    tree = _parse(ADAPTER_PATH)
    method = _class_method(tree, "VerifierAdapter", "review_claim")
    assert len(method.body) == 1
    assert isinstance(method.body[0], ast.Return)
    assert isinstance(method.body[0].value, ast.Await)
    call = method.body[0].value.value
    assert isinstance(call, ast.Call)
    assert isinstance(call.func, ast.Attribute)
    assert call.func.attr == "review_claim"
    assert isinstance(call.func.value, ast.Attribute)
    assert call.func.value.attr == "_verifier"
    assert isinstance(call.func.value.value, ast.Name)
    assert call.func.value.value.id == "self"
    assert [arg.id for arg in call.args if isinstance(arg, ast.Name)] == [
        "claim_id",
        "evidence",
    ]
    assert call.keywords == []

    forbidden_nodes = (
        ast.Assign,
        ast.AugAssign,
        ast.If,
        ast.For,
        ast.While,
        ast.Try,
        ast.With,
        ast.Raise,
    )
    offenders = [
        type(node).__name__
        for node in ast.walk(method)
        if isinstance(node, forbidden_nodes)
    ]
    assert offenders == []
