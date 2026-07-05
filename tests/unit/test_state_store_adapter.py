"""Boundary tests for the state store adapter skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path
from typing import Any, Mapping

from flaghunter.ports import StateStorePort


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "flaghunter" / "adapters" / "storage" / "state_store_adapter.py"

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


class RecordingStateStore:
    def __init__(self) -> None:
        self.snapshots: dict[str, Mapping[str, Any]] = {}
        self.load_calls: list[str] = []
        self.save_calls: list[tuple[str, Mapping[str, Any]]] = []

    def load_snapshot(self, run_id: str) -> Mapping[str, Any] | None:
        self.load_calls.append(run_id)
        return self.snapshots.get(run_id)

    def save_snapshot(
        self,
        run_id: str,
        snapshot: Mapping[str, Any],
    ) -> None:
        self.save_calls.append((run_id, snapshot))
        self.snapshots[run_id] = snapshot


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


def test_state_store_adapter_delegates_to_injected_port() -> None:
    module = importlib.import_module("flaghunter.adapters.storage.state_store_adapter")
    package = importlib.import_module("flaghunter.adapters.storage")
    store = RecordingStateStore()
    adapter = module.StateStoreAdapter(store)
    snapshot = {
        "schemaVersion": "challenge.run_snapshot.v1",
        "runId": "run-1",
        "status": "active",
    }

    adapter.save_snapshot("run-1", snapshot)
    loaded = adapter.load_snapshot("run-1")
    missing = adapter.load_snapshot("missing-run")

    assert package.StateStoreAdapter is module.StateStoreAdapter
    assert isinstance(adapter, StateStorePort)
    assert store.save_calls == [("run-1", snapshot)]
    assert store.load_calls == ["run-1", "missing-run"]
    assert loaded == snapshot
    assert missing is None


def test_state_store_adapter_has_no_concrete_or_action_imports() -> None:
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
