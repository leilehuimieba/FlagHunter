"""Boundary tests for the checkpoint store adapter skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path
from typing import Any, Mapping

from flaghunter.ports import CheckpointStorePort


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "flaghunter" / "adapters" / "storage" / "checkpoint_store_adapter.py"

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


class RecordingCheckpointStore:
    def __init__(self) -> None:
        self.checkpoints: dict[str, Mapping[str, Any]] = {}
        self.create_calls: list[tuple[str, Mapping[str, Any]]] = []
        self.load_calls: list[str] = []

    def create_checkpoint(
        self,
        run_id: str,
        snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.create_calls.append((run_id, snapshot))
        record = {
            "schemaVersion": "challenge.checkpoint.v1",
            "checkpointId": "checkpoint-1",
            "runId": run_id,
            "snapshot": snapshot,
        }
        self.checkpoints["checkpoint-1"] = record
        return record

    def load_checkpoint(self, checkpoint_id: str) -> Mapping[str, Any] | None:
        self.load_calls.append(checkpoint_id)
        return self.checkpoints.get(checkpoint_id)


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


def test_checkpoint_store_adapter_delegates_to_injected_port() -> None:
    module = importlib.import_module("flaghunter.adapters.storage.checkpoint_store_adapter")
    package = importlib.import_module("flaghunter.adapters.storage")
    store = RecordingCheckpointStore()
    adapter = module.CheckpointStoreAdapter(store)
    snapshot = {
        "schemaVersion": "challenge.run_snapshot.v1",
        "runId": "run-1",
        "status": "paused",
    }

    created = adapter.create_checkpoint("run-1", snapshot)
    loaded = adapter.load_checkpoint("checkpoint-1")
    missing = adapter.load_checkpoint("missing-checkpoint")

    assert package.CheckpointStoreAdapter is module.CheckpointStoreAdapter
    assert isinstance(adapter, CheckpointStorePort)
    assert store.create_calls == [("run-1", snapshot)]
    assert store.load_calls == ["checkpoint-1", "missing-checkpoint"]
    assert created == {
        "schemaVersion": "challenge.checkpoint.v1",
        "checkpointId": "checkpoint-1",
        "runId": "run-1",
        "snapshot": snapshot,
    }
    assert loaded == created
    assert missing is None


def test_checkpoint_store_adapter_has_no_concrete_or_action_imports() -> None:
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
