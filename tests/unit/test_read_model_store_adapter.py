"""Boundary tests for the read model store adapter skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path
from typing import Any, Iterable, Mapping

from flaghunter.ports import ReadModelStorePort


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "flaghunter" / "adapters" / "storage" / "read_model_store_adapter.py"

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


class RecordingReadModelStore:
    def __init__(self) -> None:
        self.get_calls: list[tuple[str, dict[str, Any] | None]] = []
        self.list_calls = 0

    def get_read_model(
        self,
        name: str,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        payload = dict(filters) if filters is not None else None
        self.get_calls.append((name, payload))
        return {
            "schemaVersion": "challenge.read_model.v1",
            "name": name,
            "filters": payload,
            "items": [],
        }

    def list_read_models(self) -> Iterable[Mapping[str, Any]]:
        self.list_calls += 1
        return (
            {
                "schemaVersion": "challenge.read_model_ref.v1",
                "name": "challenge-run",
            },
        )


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


def test_read_model_store_adapter_delegates_to_injected_port() -> None:
    module = importlib.import_module("flaghunter.adapters.storage.read_model_store_adapter")
    package = importlib.import_module("flaghunter.adapters.storage")
    store = RecordingReadModelStore()
    adapter = module.ReadModelStoreAdapter(store)

    read_model = adapter.get_read_model("challenge-run", filters={"runId": "run-1"})
    read_model_refs = list(adapter.list_read_models())

    assert package.ReadModelStoreAdapter is module.ReadModelStoreAdapter
    assert isinstance(adapter, ReadModelStorePort)
    assert store.get_calls == [("challenge-run", {"runId": "run-1"})]
    assert store.list_calls == 1
    assert read_model == {
        "schemaVersion": "challenge.read_model.v1",
        "name": "challenge-run",
        "filters": {"runId": "run-1"},
        "items": [],
    }
    assert read_model_refs == [
        {
            "schemaVersion": "challenge.read_model_ref.v1",
            "name": "challenge-run",
        },
    ]


def test_read_model_store_adapter_has_no_concrete_or_action_imports() -> None:
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
