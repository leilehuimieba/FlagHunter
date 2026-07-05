"""Boundary tests for the neutral challenge board read model builder."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROOT = REPO_ROOT / "flaghunter" / "application"

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
    "open(",
    "write_text",
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


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


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


def _board_service_source() -> Path:
    return APPLICATION_ROOT / "challenge" / "board_read_model_service.py"


def test_board_read_model_contract_and_builder_are_importable_and_reexported() -> None:
    contracts = importlib.import_module("flaghunter.domain.challenge.contracts")
    module = importlib.import_module(
        "flaghunter.application.challenge.board_read_model_service"
    )
    package = importlib.import_module("flaghunter.application.challenge")

    assert contracts.BoardItem.__name__ == "BoardItem"
    assert contracts.ChallengeBoardReadModel.__name__ == "ChallengeBoardReadModel"
    assert module.BuildChallengeBoardReadModel.__name__ == "BuildChallengeBoardReadModel"
    assert package.BuildChallengeBoardReadModel is module.BuildChallengeBoardReadModel


def test_board_read_model_round_trips_with_schema_versioned_payloads() -> None:
    from flaghunter.domain.challenge.contracts import (
        BoardItem,
        ChallengeBoardReadModel,
    )

    item = BoardItem(
        item_id="fact-1",
        item_type="claim",
        value="possible answer",
        source_ref="source-1",
        confidence=0.75,
        metadata={"safe": True},
    )
    model = ChallengeBoardReadModel(
        run_id="run-1",
        challenge_id="challenge-1",
        facts=[item],
        surface_refs=[{"surfaceRef": "surface-1", "weight": 0.5}],
    )

    payload = model.to_dict()

    assert payload["schemaVersion"] == "challenge.board_read_model.v1"
    assert payload["facts"][0]["schemaVersion"] == "challenge.board_item.v1"
    assert payload["surfaceRefs"] == [{"surfaceRef": "surface-1", "weight": 0.5}]
    assert ChallengeBoardReadModel.from_dict(payload).to_dict() == payload
    _assert_json_friendly(payload)


def test_build_returns_empty_board_for_minimal_snapshot() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        BuildChallengeBoardReadModel,
    )
    from flaghunter.domain.challenge.contracts import ChallengeRunSnapshot

    builder = BuildChallengeBoardReadModel()
    model = builder.build(ChallengeRunSnapshot(run_id="run-1", challenge_id="challenge-1"))

    assert model.to_dict() == {
        "schemaVersion": "challenge.board_read_model.v1",
        "runId": "run-1",
        "challengeId": "challenge-1",
        "facts": [],
        "evidence": [],
        "receipts": [],
        "tasks": [],
        "decisions": [],
        "candidates": [],
        "actionResults": [],
        "recommendedTask": {},
        "surfaceRefs": [],
        "metadata": {},
    }


def test_build_projects_neutral_snapshot_records_without_mutating_input() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        BuildChallengeBoardReadModel,
    )
    from flaghunter.domain.challenge.contracts import (
        ChallengeClaim,
        ChallengeRunSnapshot,
        EvidenceRecord,
        TaskGraphNode,
        TaskReceipt,
    )

    snapshot = ChallengeRunSnapshot(
        run_id="run-2",
        challenge_id="challenge-2",
        claims=[
            ChallengeClaim(
                claim_id="claim-1",
                claim_type="answer",
                claim_value="candidate value",
                evidence_refs=["evidence-1"],
            )
        ],
        evidence=[
            EvidenceRecord(
                evidence_id="evidence-1",
                claim_id="claim-1",
                evidence_type="observation",
                evidence_value="observed value",
                source_ref="source-1",
            )
        ],
        receipts=[
            TaskReceipt(
                receipt_id="receipt-1",
                task_id="task-1",
                outcome="completed",
                summary="done",
            )
        ],
        task_nodes=[TaskGraphNode(node_id="task-1", title="Inspect prompt")],
        metadata={"surfaceRefs": [{"surfaceRef": "surface-1"}]},
    )
    before = snapshot.to_dict()

    payload = BuildChallengeBoardReadModel().build(snapshot).to_dict()

    assert payload["facts"] == [
        {
            "schemaVersion": "challenge.board_item.v1",
            "itemId": "claim-1",
            "itemType": "claim:answer",
            "value": "candidate value",
            "sourceRef": None,
            "confidence": None,
            "metadata": {
                "artifactRefs": [],
                "evidenceRefs": ["evidence-1"],
                "status": "candidate",
            },
        }
    ]
    assert payload["evidence"][0]["itemId"] == "evidence-1"
    assert payload["receipts"][0]["itemId"] == "receipt-1"
    assert payload["tasks"][0]["itemId"] == "task-1"
    assert payload["surfaceRefs"] == [{"surfaceRef": "surface-1"}]
    assert snapshot.to_dict() == before
    _assert_json_friendly(payload)


def test_board_read_model_service_uses_only_inner_contracts() -> None:
    path = _board_service_source()
    tree = _parse(path)
    offenders: list[tuple[str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            continue
        for module in modules:
            normalized = module.lstrip(".")
            if normalized.startswith(FORBIDDEN_IMPORT_PREFIXES):
                offenders.append((_relative(path), module))

    assert offenders == []


def test_board_read_model_service_has_no_action_or_proof_surfaces() -> None:
    text = _board_service_source().read_text(encoding="utf-8")

    assert [
        token
        for token in FORBIDDEN_ACTION_TOKENS | FORBIDDEN_PROOF_TOKENS
        if token in text
    ] == []


def test_board_read_model_public_names_are_domain_neutral() -> None:
    offenders: list[tuple[str, str, int]] = []
    for path in (
        REPO_ROOT / "flaghunter" / "domain" / "challenge" / "contracts" / "read_models.py",
        _board_service_source(),
    ):
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            lowered_name = node.name.lower()
            offenders.extend(
                (_relative(path), f"{node.name} contains {term}", node.lineno)
                for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                if term in lowered_name
            )

    assert offenders == []
