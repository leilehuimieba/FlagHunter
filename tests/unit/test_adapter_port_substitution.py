"""Adapter substitution fixtures that avoid production wiring."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.adapters.artifacts.artifact_store_adapter import ArtifactStoreAdapter
from flaghunter.adapters.audit.audit_store_adapter import AuditStoreAdapter
from flaghunter.adapters.crew.crew_bridge_adapter import CrewBridgeAdapter
from flaghunter.adapters.crew.task_dag_runner_adapter import TaskDAGRunnerAdapter
from flaghunter.adapters.proof.verifier_adapter import VerifierAdapter
from flaghunter.adapters.storage.checkpoint_store_adapter import CheckpointStoreAdapter
from flaghunter.adapters.storage.claim_store_adapter import ClaimStoreAdapter
from flaghunter.adapters.storage.read_model_store_adapter import ReadModelStoreAdapter
from flaghunter.adapters.storage.state_store_adapter import StateStoreAdapter
from flaghunter.adapters.runtime.runtime_action_adapter import RuntimeActionAdapter
from flaghunter.adapters.tools.tool_runner_adapter import ToolRunnerAdapter
from flaghunter.ports import (
    ArtifactStorePort,
    AuditStorePort,
    CheckpointStorePort,
    ClaimStorePort,
    CrewBridgePort,
    ReadModelStorePort,
    RuntimeActionPort,
    StateStorePort,
    TaskDAGRunnerPort,
    ToolRunnerPort,
    VerifierPort,
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


class SubstitutableAuditStore:
    def __init__(self, label: str) -> None:
        self.label = label
        self.events: list[dict[str, Any]] = []
        self.append_calls: list[dict[str, Any]] = []
        self.query_calls: list[Mapping[str, Any] | None] = []

    def append_event(self, event: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = dict(event)
        self.append_calls.append(payload)
        self.events.append(payload)
        return {"store": self.label, "eventId": f"{self.label}-event", **payload}

    def query_events(
        self,
        filters: Mapping[str, Any] | None = None,
    ) -> list[Mapping[str, Any]]:
        self.query_calls.append(filters)
        return [
            {"store": self.label, **event}
            for event in self.events
            if not filters or all(event.get(key) == value for key, value in filters.items())
        ]


class SubstitutableArtifactStore:
    def __init__(self, label: str) -> None:
        self.label = label
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.register_calls: list[dict[str, Any]] = []
        self.get_calls: list[str] = []

    def register_artifact(self, artifact: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = dict(artifact)
        artifact_id = str(payload.get("artifactId") or f"{self.label}-artifact")
        self.register_calls.append(payload)
        self.artifacts[artifact_id] = payload
        return {"store": self.label, "artifactId": artifact_id, **payload}

    def get_artifact(self, artifact_id: str) -> Mapping[str, Any] | None:
        self.get_calls.append(artifact_id)
        artifact = self.artifacts.get(artifact_id)
        if artifact is None:
            return None
        return {"store": self.label, **artifact}


class SubstitutableCrewBridge:
    def __init__(self, label: str) -> None:
        self.label = label
        self.calls: list[dict[str, Any]] = []

    async def dispatch_task(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = dict(request)
        self.calls.append(payload)
        return {
            "schemaVersion": "challenge.worker_receipt.v1",
            "bridge": self.label,
            "taskId": payload.get("taskId"),
            "status": "queued",
        }


class SubstitutableTaskGraphRunner:
    def __init__(self, label: str) -> None:
        self.label = label
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def run_ready_task(
        self,
        plan: Mapping[str, Any],
        state_snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        plan_payload = dict(plan)
        state_payload = dict(state_snapshot)
        self.calls.append((plan_payload, state_payload))
        return {
            "schemaVersion": "challenge.task_receipt.v1",
            "runner": self.label,
            "taskId": plan_payload.get("taskId"),
            "runId": state_payload.get("runId"),
            "outcome": "completed",
        }


class SubstitutableVerifier:
    def __init__(self, label: str, outcome: str) -> None:
        self.label = label
        self.outcome = outcome
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def review_claim(
        self,
        claim_id: str,
        evidence: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        payload = dict(evidence)
        self.calls.append((claim_id, payload))
        return {
            "schemaVersion": "challenge.claim_review.v1",
            "reviewer": self.label,
            "claimId": claim_id,
            "outcome": self.outcome,
            "evidence": payload,
        }


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


def test_audit_and_artifact_adapters_substitute_injected_stores_without_wiring() -> None:
    audit_store = SubstitutableAuditStore("audit-a")
    artifact_store = SubstitutableArtifactStore("artifact-a")
    audit_adapter = AuditStoreAdapter(audit_store)
    artifact_adapter = ArtifactStoreAdapter(artifact_store)

    audit_event = audit_adapter.append_event(
        {"schemaVersion": 1, "eventType": "taskReceiptRecorded", "runId": "run-1"}
    )
    matching_events = list(audit_adapter.query_events({"runId": "run-1"}))
    missing_events = list(audit_adapter.query_events({"runId": "run-missing"}))
    artifact = artifact_adapter.register_artifact(
        {"artifactId": "artifact-1", "kind": "note", "runId": "run-1"}
    )
    loaded_artifact = artifact_adapter.get_artifact("artifact-1")
    missing_artifact = artifact_adapter.get_artifact("missing-artifact")

    assert isinstance(audit_adapter, AuditStorePort)
    assert isinstance(artifact_adapter, ArtifactStorePort)
    assert audit_store.append_calls == [
        {"schemaVersion": 1, "eventType": "taskReceiptRecorded", "runId": "run-1"}
    ]
    assert audit_store.query_calls == [{"runId": "run-1"}, {"runId": "run-missing"}]
    assert audit_event == {
        "store": "audit-a",
        "eventId": "audit-a-event",
        "schemaVersion": 1,
        "eventType": "taskReceiptRecorded",
        "runId": "run-1",
    }
    assert matching_events == [
        {
            "store": "audit-a",
            "schemaVersion": 1,
            "eventType": "taskReceiptRecorded",
            "runId": "run-1",
        }
    ]
    assert missing_events == []
    assert artifact_store.register_calls == [
        {"artifactId": "artifact-1", "kind": "note", "runId": "run-1"}
    ]
    assert artifact_store.get_calls == ["artifact-1", "missing-artifact"]
    assert artifact == {
        "store": "artifact-a",
        "artifactId": "artifact-1",
        "kind": "note",
        "runId": "run-1",
    }
    assert loaded_artifact == {
        "store": "artifact-a",
        "artifactId": "artifact-1",
        "kind": "note",
        "runId": "run-1",
    }
    assert missing_artifact is None


async def test_crew_adapters_substitute_injected_runners_without_wiring() -> None:
    crew_bridge = SubstitutableCrewBridge("crew-a")
    task_runner = SubstitutableTaskGraphRunner("runner-a")
    crew_adapter = CrewBridgeAdapter(crew_bridge)
    task_runner_adapter = TaskDAGRunnerAdapter(task_runner)
    worker_request = {
        "schemaVersion": "challenge.worker_task.v1",
        "taskId": "worker-task-1",
        "taskType": "review",
    }
    plan = {
        "schemaVersion": "challenge.task_graph_node.v1",
        "taskId": "task-1",
        "taskType": "review",
    }
    state_snapshot = {
        "schemaVersion": "challenge.run_snapshot.v1",
        "runId": "run-1",
    }

    worker_receipt = await crew_adapter.dispatch_task(worker_request)
    task_receipt = await task_runner_adapter.run_ready_task(plan, state_snapshot)

    assert isinstance(crew_adapter, CrewBridgePort)
    assert isinstance(task_runner_adapter, TaskDAGRunnerPort)
    assert crew_bridge.calls == [worker_request]
    assert task_runner.calls == [(plan, state_snapshot)]
    assert worker_receipt == {
        "schemaVersion": "challenge.worker_receipt.v1",
        "bridge": "crew-a",
        "taskId": "worker-task-1",
        "status": "queued",
    }
    assert task_receipt == {
        "schemaVersion": "challenge.task_receipt.v1",
        "runner": "runner-a",
        "taskId": "task-1",
        "runId": "run-1",
        "outcome": "completed",
    }


async def test_verifier_adapter_substitutes_injected_reviewers_without_wiring() -> None:
    first_verifier = SubstitutableVerifier("reviewer-a", "needs_more_evidence")
    second_verifier = SubstitutableVerifier("reviewer-b", "rejected")
    first_adapter = VerifierAdapter(first_verifier)
    second_adapter = VerifierAdapter(second_verifier)
    first_evidence = {"schemaVersion": 1, "evidenceId": "evidence-a"}
    second_evidence = {"schemaVersion": 1, "evidenceId": "evidence-b"}

    first_review = await first_adapter.review_claim("claim-a", first_evidence)
    second_review = await second_adapter.review_claim("claim-b", second_evidence)

    assert isinstance(first_adapter, VerifierPort)
    assert isinstance(second_adapter, VerifierPort)
    assert first_verifier.calls == [("claim-a", first_evidence)]
    assert second_verifier.calls == [("claim-b", second_evidence)]
    assert first_review == {
        "schemaVersion": "challenge.claim_review.v1",
        "reviewer": "reviewer-a",
        "claimId": "claim-a",
        "outcome": "needs_more_evidence",
        "evidence": first_evidence,
    }
    assert second_review == {
        "schemaVersion": "challenge.claim_review.v1",
        "reviewer": "reviewer-b",
        "claimId": "claim-b",
        "outcome": "rejected",
        "evidence": second_evidence,
    }
