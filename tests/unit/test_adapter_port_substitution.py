"""Adapter substitution fixtures that avoid production wiring."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.adapters.storage.checkpoint_store_adapter import CheckpointStoreAdapter
from flaghunter.adapters.storage.claim_store_adapter import ClaimStoreAdapter
from flaghunter.adapters.storage.read_model_store_adapter import ReadModelStoreAdapter
from flaghunter.adapters.storage.state_store_adapter import StateStoreAdapter
from flaghunter.adapters.runtime.runtime_action_adapter import RuntimeActionAdapter
from flaghunter.adapters.tools.tool_runner_adapter import ToolRunnerAdapter
from flaghunter.ports import (
    CheckpointStorePort,
    ClaimStorePort,
    ReadModelStorePort,
    RuntimeActionPort,
    StateStorePort,
    ToolRunnerPort,
)


class FirstToolRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run_tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        payload = dict(arguments)
        self.calls.append((name, payload))
        return {
            "schemaVersion": "challenge.tool_run_receipt.v1",
            "runner": "first",
            "toolName": name,
            "arguments": payload,
        }


class SecondToolRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run_tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        payload = dict(arguments)
        self.calls.append((name, payload))
        return {
            "schemaVersion": "challenge.tool_run_receipt.v1",
            "runner": "second",
            "toolName": name,
            "arguments": payload,
        }


class FirstRuntimeAction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float | None]] = []

    async def run_command(
        self,
        command: str,
        *,
        timeout_seconds: float | None = None,
    ) -> Mapping[str, Any]:
        self.calls.append((command, timeout_seconds))
        return {
            "schemaVersion": "challenge.runtime_action_receipt.v1",
            "runtime": "first",
            "command": command,
            "timeoutSeconds": timeout_seconds,
        }


class SecondRuntimeAction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float | None]] = []

    async def run_command(
        self,
        command: str,
        *,
        timeout_seconds: float | None = None,
    ) -> Mapping[str, Any]:
        self.calls.append((command, timeout_seconds))
        return {
            "schemaVersion": "challenge.runtime_action_receipt.v1",
            "runtime": "second",
            "command": command,
            "timeoutSeconds": timeout_seconds,
        }


class SubstitutableStateStore:
    def __init__(self, label: str) -> None:
        self.label = label
        self.snapshots: dict[str, Mapping[str, Any]] = {}
        self.save_calls: list[tuple[str, dict[str, Any]]] = []
        self.load_calls: list[str] = []

    def save_snapshot(self, run_id: str, snapshot: Mapping[str, Any]) -> None:
        payload = dict(snapshot)
        self.save_calls.append((run_id, payload))
        self.snapshots[run_id] = payload

    def load_snapshot(self, run_id: str) -> Mapping[str, Any] | None:
        self.load_calls.append(run_id)
        snapshot = self.snapshots.get(run_id)
        if snapshot is None:
            return None
        return {"store": self.label, **dict(snapshot)}


class SubstitutableReadModelStore:
    def __init__(self, label: str) -> None:
        self.label = label
        self.get_calls: list[tuple[str, Mapping[str, Any] | None]] = []
        self.list_calls = 0

    def get_read_model(
        self,
        name: str,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        self.get_calls.append((name, filters))
        return {"store": self.label, "modelName": name, "filters": dict(filters or {})}

    def list_read_models(self) -> list[Mapping[str, Any]]:
        self.list_calls += 1
        return [{"store": self.label, "modelName": f"{self.label}-summary"}]


class SubstitutableClaimStore:
    def __init__(self, label: str) -> None:
        self.label = label
        self.create_calls: list[tuple[str, dict[str, Any]]] = []
        self.find_calls: list[tuple[str | None, str | None]] = []
        self.trace_calls: list[tuple[str, dict[str, Any]]] = []

    def create_candidate_claim(
        self,
        kind: str,
        content: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        payload = dict(content)
        self.create_calls.append((kind, payload))
        return {"store": self.label, "claimId": f"{self.label}-claim", "kind": kind}

    def find_claims(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
    ) -> list[Mapping[str, Any]]:
        self.find_calls.append((kind, status))
        return [{"store": self.label, "kind": kind, "status": status}]

    def append_evidence_trace(
        self,
        claim_id: str,
        evidence: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        payload = dict(evidence)
        self.trace_calls.append((claim_id, payload))
        return {"store": self.label, "claimId": claim_id, "evidence": payload}


class SubstitutableCheckpointStore:
    def __init__(self, label: str) -> None:
        self.label = label
        self.checkpoints: dict[str, Mapping[str, Any]] = {}
        self.create_calls: list[tuple[str, dict[str, Any]]] = []
        self.load_calls: list[str] = []

    def create_checkpoint(
        self,
        run_id: str,
        snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        payload = dict(snapshot)
        checkpoint_id = f"{self.label}-checkpoint"
        self.create_calls.append((run_id, payload))
        self.checkpoints[checkpoint_id] = payload
        return {"store": self.label, "checkpointId": checkpoint_id, "runId": run_id}

    def load_checkpoint(self, checkpoint_id: str) -> Mapping[str, Any] | None:
        self.load_calls.append(checkpoint_id)
        payload = self.checkpoints.get(checkpoint_id)
        if payload is None:
            return None
        return {"store": self.label, "checkpointId": checkpoint_id, "snapshot": payload}


async def test_tool_runner_adapter_substitutes_injected_ports_without_wiring() -> None:
    first_runner = FirstToolRunner()
    second_runner = SecondToolRunner()
    first_adapter = ToolRunnerAdapter(first_runner)
    second_adapter = ToolRunnerAdapter(second_runner)

    first_result = await first_adapter.run_tool("inspect", {"target": "alpha"})
    second_result = await second_adapter.run_tool("inspect", {"target": "beta"})

    assert isinstance(first_adapter, ToolRunnerPort)
    assert isinstance(second_adapter, ToolRunnerPort)
    assert first_runner.calls == [("inspect", {"target": "alpha"})]
    assert second_runner.calls == [("inspect", {"target": "beta"})]
    assert first_result == {
        "schemaVersion": "challenge.tool_run_receipt.v1",
        "runner": "first",
        "toolName": "inspect",
        "arguments": {"target": "alpha"},
    }
    assert second_result == {
        "schemaVersion": "challenge.tool_run_receipt.v1",
        "runner": "second",
        "toolName": "inspect",
        "arguments": {"target": "beta"},
    }


async def test_runtime_action_adapter_substitutes_injected_ports_without_wiring() -> None:
    first_runtime = FirstRuntimeAction()
    second_runtime = SecondRuntimeAction()
    first_adapter = RuntimeActionAdapter(first_runtime)
    second_adapter = RuntimeActionAdapter(second_runtime)

    first_result = await first_adapter.run_command("echo alpha", timeout_seconds=1.0)
    second_result = await second_adapter.run_command("echo beta", timeout_seconds=2.0)

    assert isinstance(first_adapter, RuntimeActionPort)
    assert isinstance(second_adapter, RuntimeActionPort)
    assert first_runtime.calls == [("echo alpha", 1.0)]
    assert second_runtime.calls == [("echo beta", 2.0)]
    assert first_result == {
        "schemaVersion": "challenge.runtime_action_receipt.v1",
        "runtime": "first",
        "command": "echo alpha",
        "timeoutSeconds": 1.0,
    }
    assert second_result == {
        "schemaVersion": "challenge.runtime_action_receipt.v1",
        "runtime": "second",
        "command": "echo beta",
        "timeoutSeconds": 2.0,
    }


def test_storage_adapters_substitute_injected_stores_without_wiring() -> None:
    state_store = SubstitutableStateStore("state-a")
    read_model_store = SubstitutableReadModelStore("read-a")
    claim_store = SubstitutableClaimStore("claim-a")
    checkpoint_store = SubstitutableCheckpointStore("checkpoint-a")

    state_adapter = StateStoreAdapter(state_store)
    read_model_adapter = ReadModelStoreAdapter(read_model_store)
    claim_adapter = ClaimStoreAdapter(claim_store)
    checkpoint_adapter = CheckpointStoreAdapter(checkpoint_store)

    state_adapter.save_snapshot("run-1", {"schemaVersion": 1, "runId": "run-1"})
    loaded_snapshot = state_adapter.load_snapshot("run-1")
    read_model = read_model_adapter.get_read_model("summary", filters={"runId": "run-1"})
    read_models = list(read_model_adapter.list_read_models())
    claim = claim_adapter.create_candidate_claim("answer", {"claimValue": "candidate"})
    claims = list(claim_adapter.find_claims(kind="answer", status="candidate"))
    trace = claim_adapter.append_evidence_trace("claim-1", {"evidenceId": "evidence-1"})
    checkpoint = checkpoint_adapter.create_checkpoint("run-1", {"step": "ready"})
    loaded_checkpoint = checkpoint_adapter.load_checkpoint("checkpoint-a-checkpoint")

    assert isinstance(state_adapter, StateStorePort)
    assert isinstance(read_model_adapter, ReadModelStorePort)
    assert isinstance(claim_adapter, ClaimStorePort)
    assert isinstance(checkpoint_adapter, CheckpointStorePort)
    assert state_store.save_calls == [("run-1", {"schemaVersion": 1, "runId": "run-1"})]
    assert state_store.load_calls == ["run-1"]
    assert loaded_snapshot == {"store": "state-a", "schemaVersion": 1, "runId": "run-1"}
    assert read_model_store.get_calls == [("summary", {"runId": "run-1"})]
    assert read_model_store.list_calls == 1
    assert read_model == {
        "store": "read-a",
        "modelName": "summary",
        "filters": {"runId": "run-1"},
    }
    assert read_models == [{"store": "read-a", "modelName": "read-a-summary"}]
    assert claim_store.create_calls == [("answer", {"claimValue": "candidate"})]
    assert claim_store.find_calls == [("answer", "candidate")]
    assert claim_store.trace_calls == [("claim-1", {"evidenceId": "evidence-1"})]
    assert claim == {"store": "claim-a", "claimId": "claim-a-claim", "kind": "answer"}
    assert claims == [{"store": "claim-a", "kind": "answer", "status": "candidate"}]
    assert trace == {
        "store": "claim-a",
        "claimId": "claim-1",
        "evidence": {"evidenceId": "evidence-1"},
    }
    assert checkpoint_store.create_calls == [("run-1", {"step": "ready"})]
    assert checkpoint_store.load_calls == ["checkpoint-a-checkpoint"]
    assert checkpoint == {
        "store": "checkpoint-a",
        "checkpointId": "checkpoint-a-checkpoint",
        "runId": "run-1",
    }
    assert loaded_checkpoint == {
        "store": "checkpoint-a",
        "checkpointId": "checkpoint-a-checkpoint",
        "snapshot": {"step": "ready"},
    }
