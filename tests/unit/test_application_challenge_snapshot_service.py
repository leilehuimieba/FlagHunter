"""Boundary tests for the challenge run snapshot application service."""

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
    "flaghunter.tools",
    "flaghunter.runtime",
    "flaghunter.interface",
    "flaghunter.mcp",
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


class EmptyStateStore:
    def __init__(self) -> None:
        self.loaded_run_ids: list[str] = []

    def load_snapshot(self, run_id: str) -> Mapping[str, Any] | None:
        self.loaded_run_ids.append(run_id)
        return None

    def save_snapshot(self, run_id: str, snapshot: Mapping[str, Any]) -> None:
        raise AssertionError("snapshot service must not mutate state")


class MappingStateStore(EmptyStateStore):
    def __init__(self, payload: Mapping[str, Any]) -> None:
        super().__init__()
        self.payload = payload

    def load_snapshot(self, run_id: str) -> Mapping[str, Any] | None:
        self.loaded_run_ids.append(run_id)
        return self.payload


class RecordingReadModelStore:
    def __init__(self, models: Iterable[Mapping[str, Any]]) -> None:
        self.models = list(models)
        self.list_calls = 0

    def get_read_model(
        self,
        name: str,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        raise AssertionError("snapshot service should not fetch concrete read models")

    def list_read_models(self) -> Iterable[Mapping[str, Any]]:
        self.list_calls += 1
        return list(self.models)


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


def test_snapshot_service_is_importable_and_reexported() -> None:
    package = importlib.import_module("flaghunter.application.challenge")
    module = importlib.import_module("flaghunter.application.challenge.snapshot_service")

    assert module.BuildChallengeRunSnapshot.__name__ == "BuildChallengeRunSnapshot"
    assert package.BuildChallengeRunSnapshot is module.BuildChallengeRunSnapshot


def test_build_returns_empty_snapshot_for_minimal_input() -> None:
    from flaghunter.application.challenge.snapshot_service import (
        BuildChallengeRunSnapshot,
    )
    from flaghunter.domain.challenge.contracts.read_models import ChallengeRunSnapshot

    state_store = EmptyStateStore()
    service = BuildChallengeRunSnapshot(state_store=state_store)

    snapshot = service.build(run_id="run-1", challenge_id="challenge-1")

    assert isinstance(snapshot, ChallengeRunSnapshot)
    assert snapshot.to_dict() == {
        "schemaVersion": 1,
        "runId": "run-1",
        "challengeId": "challenge-1",
        "claims": [],
        "evidence": [],
        "receipts": [],
        "taskNodes": [],
        "readModels": [],
        "proofRecords": [],
        "metadata": {},
    }
    assert state_store.loaded_run_ids == ["run-1"]


def test_build_normalizes_state_snapshot_and_read_model_refs() -> None:
    from flaghunter.application.challenge.snapshot_service import (
        BuildChallengeRunSnapshot,
    )

    state_store = MappingStateStore(
        {
            "metadata": {"source": "state-store"},
            "readModels": [
                {
                    "modelId": "state-summary",
                    "modelType": "summary",
                    "runId": "run-2",
                    "label": "State Summary",
                }
            ],
        }
    )
    read_model_store = RecordingReadModelStore(
        [
            {
                "modelId": "audit-view",
                "modelType": "audit",
                "runId": "run-2",
                "version": 2,
                "metadata": {"count": 3},
            },
            {"modelId": "ignored-other-run", "modelType": "audit", "runId": "run-x"},
            {"notAModel": True},
        ]
    )
    service = BuildChallengeRunSnapshot(
        state_store=state_store,
        read_model_store=read_model_store,
    )

    snapshot = service.build(run_id="run-2", challenge_id="challenge-2")
    payload = snapshot.to_dict()

    assert payload["schemaVersion"] == 1
    assert payload["runId"] == "run-2"
    assert payload["challengeId"] == "challenge-2"
    assert payload["metadata"] == {"source": "state-store"}
    assert [model["modelId"] for model in payload["readModels"]] == [
        "state-summary",
        "audit-view",
    ]
    assert payload == snapshot.from_dict(payload).to_dict()
    assert read_model_store.list_calls == 1


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


def test_snapshot_service_is_small_and_has_no_private_runtime_hooks() -> None:
    from flaghunter.application.challenge.snapshot_service import (
        BuildChallengeRunSnapshot,
    )

    public_methods = {
        name
        for name, member in inspect.getmembers(
            BuildChallengeRunSnapshot,
            predicate=inspect.isfunction,
        )
        if not name.startswith("_")
    }

    assert public_methods == {"build"}
