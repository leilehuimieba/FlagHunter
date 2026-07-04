"""Boundary tests for challenge-domain contract skeletons."""

from __future__ import annotations

import ast
import importlib
import inspect
import warnings
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = REPO_ROOT / "flaghunter" / "domain" / "challenge" / "contracts"


EXPECTED_CONTRACTS = {
    "flaghunter.domain.challenge.contracts.claims": {
        "ChallengeClaim": {
            "claim_id": "claim-1",
            "claim_type": "answer",
            "claim_value": "possible answer",
        },
    },
    "flaghunter.domain.challenge.contracts.evidence": {
        "EvidenceRecord": {
            "evidence_id": "evidence-1",
            "claim_id": "claim-1",
            "evidence_type": "observation",
            "evidence_value": "observed answer",
        },
    },
    "flaghunter.domain.challenge.contracts.receipts": {
        "TaskReceipt": {
            "receipt_id": "receipt-1",
            "task_id": "task-1",
            "outcome": "completed",
        },
    },
    "flaghunter.domain.challenge.contracts.task_graph": {
        "TaskGraphNode": {
            "node_id": "task-1",
            "title": "Inspect prompt",
        },
    },
    "flaghunter.domain.challenge.contracts.read_models": {
        "ReadModelRef": {
            "model_id": "model-1",
            "model_type": "challenge.summary",
        },
        "ChallengeRunSnapshot": {
            "run_id": "run-1",
            "challenge_id": "challenge-1",
        },
    },
    "flaghunter.domain.challenge.contracts.proof": {
        "ProofRecord": {
            "proof_id": "proof-1",
            "claim_id": "claim-1",
        },
    },
}


FORBIDDEN_IMPORT_PREFIXES = (
    "flaghunter.agents",
    "flaghunter.tools",
    "flaghunter.runtime",
    "flaghunter.interface",
    "flaghunter.mcp",
    "flaghunter.session",
    "flaghunter.ports",
)

FORBIDDEN_SIDE_EFFECT_TOKENS = {
    "subprocess",
    "asyncio.subprocess",
    "open(",
    "write_text",
    "requests",
    "httpx",
    "socket",
    "Playwright",
    "browser",
    "Runtime",
    "ToolExecutor",
    "execute_tools",
    "_execute_tools",
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

FORBIDDEN_PUBLIC_DOMAIN_TERMS = {
    "ctf",
    "pentest",
    "exploit",
    "vulnerability",
    "hacking",
    "attack",
    "redteam",
}

FORBIDDEN_CORE_FIELD_NAMES = {
    "flag",
    "verified_flag",
    "verified_flags",
}


def _contract_sources() -> list[Path]:
    assert CONTRACTS_ROOT.is_dir(), "challenge contracts package must exist"
    return sorted(CONTRACTS_ROOT.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


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


def _assert_json_friendly(value: Any) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for item in value:
            _assert_json_friendly(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str)
            _assert_json_friendly(item)
        return
    raise AssertionError(f"{value!r} is not JSON-friendly")


def test_expected_challenge_contract_modules_are_importable_and_reexported() -> None:
    package = importlib.import_module("flaghunter.domain.challenge.contracts")

    for module_name, expected_classes in EXPECTED_CONTRACTS.items():
        module = importlib.import_module(module_name)
        assert getattr(module, "SCHEMA_VERSION") == 1
        for class_name in expected_classes:
            assert getattr(module, class_name).__name__ == class_name
            assert getattr(package, class_name).__name__ == class_name


def test_contracts_are_dataclasses_with_schema_versioned_serialization() -> None:
    for module_name, expected_classes in EXPECTED_CONTRACTS.items():
        module = importlib.import_module(module_name)
        for class_name, kwargs in expected_classes.items():
            cls = getattr(module, class_name)
            assert inspect.isclass(cls)
            assert is_dataclass(cls)

            instance = cls(**kwargs)
            payload = instance.to_dict()

            assert payload["schemaVersion"] == 1
            _assert_json_friendly(payload)
            assert cls.from_dict(payload).to_dict() == payload


def test_minimal_inputs_use_empty_json_friendly_defaults() -> None:
    from flaghunter.domain.challenge.contracts import (
        ChallengeClaim,
        ChallengeRunSnapshot,
        EvidenceRecord,
        ProofRecord,
        ReadModelRef,
        TaskGraphNode,
        TaskReceipt,
    )

    instances = [
        ChallengeClaim(
            claim_id="claim-1",
            claim_type="answer",
            claim_value="maybe",
        ),
        EvidenceRecord(
            evidence_id="evidence-1",
            claim_id="claim-1",
            evidence_type="observation",
            evidence_value="seen",
        ),
        TaskReceipt(receipt_id="receipt-1", task_id="task-1", outcome="completed"),
        TaskGraphNode(node_id="task-1", title="Inspect prompt"),
        ReadModelRef(model_id="model-1", model_type="challenge.summary"),
        ProofRecord(proof_id="proof-1", claim_id="claim-1"),
        ChallengeRunSnapshot(run_id="run-1", challenge_id="challenge-1"),
    ]

    for instance in instances:
        payload = instance.to_dict()
        assert payload["schemaVersion"] == 1
        _assert_json_friendly(payload)


def test_challenge_run_snapshot_composes_contract_payloads() -> None:
    from flaghunter.domain.challenge.contracts import (
        ChallengeClaim,
        ChallengeRunSnapshot,
        EvidenceRecord,
        ProofRecord,
        ReadModelRef,
        TaskGraphNode,
        TaskReceipt,
    )

    snapshot = ChallengeRunSnapshot(
        run_id="run-1",
        challenge_id="challenge-1",
        claims=[
            ChallengeClaim(
                claim_id="claim-1",
                claim_type="answer",
                claim_value="maybe",
            )
        ],
        evidence=[
            EvidenceRecord(
                evidence_id="evidence-1",
                claim_id="claim-1",
                evidence_type="observation",
                evidence_value="seen",
            )
        ],
        receipts=[
            TaskReceipt(
                receipt_id="receipt-1",
                task_id="task-1",
                outcome="completed",
            )
        ],
        task_nodes=[TaskGraphNode(node_id="task-1", title="Inspect prompt")],
        read_models=[ReadModelRef(model_id="model-1", model_type="challenge.summary")],
        proof_records=[ProofRecord(proof_id="proof-1", claim_id="claim-1")],
    )

    payload = snapshot.to_dict()

    assert payload["claims"][0]["schemaVersion"] == 1
    assert payload["evidence"][0]["schemaVersion"] == 1
    assert payload["receipts"][0]["schemaVersion"] == 1
    assert payload["taskNodes"][0]["schemaVersion"] == 1
    assert payload["readModels"][0]["schemaVersion"] == 1
    assert payload["proofRecords"][0]["schemaVersion"] == 1
    assert ChallengeRunSnapshot.from_dict(payload).to_dict() == payload


def test_evidence_text_redaction_is_deterministic_and_bounded() -> None:
    from flaghunter.domain.challenge.contracts.evidence import redact_text

    raw = "password=super-secret-token " + ("A" * 80)
    redacted = redact_text(raw, max_chars=40)

    assert "super-secret-token" not in redacted
    assert len(redacted) <= 40
    assert redact_text("", max_chars=40) == ""


def test_contract_package_does_not_import_concrete_or_outer_layers() -> None:
    offenders: list[tuple[str, str]] = []
    for path in _contract_sources():
        for imported in _imported_module_names(_parse(path)):
            normalized = imported.lstrip(".")
            if normalized.startswith(FORBIDDEN_IMPORT_PREFIXES):
                offenders.append((_relative(path), imported))

    assert offenders == []


def test_contract_package_has_no_side_effect_surfaces() -> None:
    offenders: list[tuple[str, str]] = []
    for path in _contract_sources():
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_SIDE_EFFECT_TOKENS
            if token in text
        )

    assert offenders == []


def test_contract_package_has_no_proof_authority_actions() -> None:
    offenders: list[tuple[str, str]] = []
    for path in _contract_sources():
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_PROOF_ACTION_TOKENS
            if token in text
        )

    assert offenders == []


def test_public_names_docstrings_and_fields_are_domain_neutral() -> None:
    offenders: list[tuple[str, str, int]] = []
    for path in _contract_sources():
        tree = _parse(path)
        path_parts = [part.lower() for part in path.relative_to(REPO_ROOT).parts[1:]]
        for part in path_parts:
            offenders.extend(
                (_relative(path), f"path part {part} contains {term}", 1)
                for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                if term in part
            )

        module_doc = (ast.get_docstring(tree) or "").lower()
        offenders.extend(
            (_relative(path), f"module docstring contains {term}", 1)
            for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
            if term in module_doc
        )

        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                lowered_name = node.name.lower()
                offenders.extend(
                    (_relative(path), f"{node.name} contains {term}", node.lineno)
                    for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                    if term in lowered_name
                )
                lowered_doc = (ast.get_docstring(node) or "").lower()
                offenders.extend(
                    (
                        _relative(path),
                        f"{node.name} docstring contains {term}",
                        node.lineno,
                    )
                    for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                    if term in lowered_doc
                )

        for module_name, expected_classes in EXPECTED_CONTRACTS.items():
            module_path = module_name.replace(".", "/") + ".py"
            if module_path != _relative(path):
                continue
            module = importlib.import_module(module_name)
            for class_name in expected_classes:
                cls = getattr(module, class_name)
                field_names = {field.name for field in fields(cls)}
                offenders.extend(
                    (_relative(path), f"{class_name}.{field_name}", 1)
                    for field_name in field_names & FORBIDDEN_CORE_FIELD_NAMES
                )

    assert offenders == []
