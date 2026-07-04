"""Boundary tests for the artifact store adapter skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path
from typing import Any, Mapping

from flaghunter.ports import ArtifactStorePort


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "flaghunter" / "adapters" / "artifacts" / "artifact_store_adapter.py"

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


class RecordingArtifactStore:
    def __init__(self) -> None:
        self.artifacts: dict[str, Mapping[str, Any]] = {}
        self.register_calls: list[Mapping[str, Any]] = []
        self.get_calls: list[str] = []

    def register_artifact(
        self,
        artifact: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.register_calls.append(artifact)
        record = {
            "schemaVersion": "challenge.artifact_ref.v1",
            "artifactId": "artifact-1",
            "artifact": artifact,
        }
        self.artifacts["artifact-1"] = record
        return record

    def get_artifact(self, artifact_id: str) -> Mapping[str, Any] | None:
        self.get_calls.append(artifact_id)
        return self.artifacts.get(artifact_id)


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


def test_artifact_store_adapter_delegates_to_injected_port() -> None:
    module = importlib.import_module("flaghunter.adapters.artifacts.artifact_store_adapter")
    package = importlib.import_module("flaghunter.adapters.artifacts")
    store = RecordingArtifactStore()
    adapter = module.ArtifactStoreAdapter(store)
    artifact = {
        "schemaVersion": "challenge.artifact.v1",
        "artifactRef": "memory://artifact-1",
        "mediaType": "text/plain",
    }

    registered = adapter.register_artifact(artifact)
    loaded = adapter.get_artifact("artifact-1")
    missing = adapter.get_artifact("missing-artifact")

    assert package.ArtifactStoreAdapter is module.ArtifactStoreAdapter
    assert isinstance(adapter, ArtifactStorePort)
    assert store.register_calls == [artifact]
    assert store.get_calls == ["artifact-1", "missing-artifact"]
    assert registered == {
        "schemaVersion": "challenge.artifact_ref.v1",
        "artifactId": "artifact-1",
        "artifact": artifact,
    }
    assert loaded == registered
    assert missing is None


def test_artifact_store_adapter_has_no_concrete_or_action_imports() -> None:
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
