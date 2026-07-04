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
    "flaghunter.domain.challenge.contracts.control": {
        "ControlReceipt": {
            "producer": "control:finish",
            "success": True,
        },
    },
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
    "flaghunter.domain.challenge.contracts.progress": {
        "TaskProgressRef": {
            "task_id": "task-1",
            "status": "completed",
        },
        "WorkerTraceRef": {
            "worker_id": "worker-1",
            "task_id": "task-1",
        },
        "ChallengeProgressReadback": {
            "run_id": "run-1",
        },
    },
    "flaghunter.domain.challenge.contracts.task_execution": {
        "TaskExecutionNode": {
            "node_id": "node-1",
            "run_id": "run-1",
        },
        "TaskExecutionEdge": {
            "source_id": "node-1",
            "target_id": "node-2",
        },
        "TaskBrief": {
            "brief_id": "brief-1",
            "node_id": "node-1",
        },
        "TaskExecutionReceipt": {
            "receipt_id": "receipt-1",
            "node_id": "node-1",
        },
        "TaskExecutionReadback": {
            "run_id": "run-1",
        },
    },
}


EXPECTED_SCHEMA_VERSIONS = {
    "flaghunter.domain.challenge.contracts.progress": "challenge.progress.v1",
    "flaghunter.domain.challenge.contracts.task_execution": "challenge.task_execution.v1",
}


EXPECTED_CLASS_SCHEMA_VERSIONS = {
    (
        "flaghunter.domain.challenge.contracts.progress",
        "TaskProgressRef",
    ): "challenge.task_progress.v1",
    (
        "flaghunter.domain.challenge.contracts.progress",
        "WorkerTraceRef",
    ): "challenge.worker_trace.v1",
    (
        "flaghunter.domain.challenge.contracts.task_execution",
        "TaskExecutionNode",
    ): "challenge.task_execution_node.v1",
    (
        "flaghunter.domain.challenge.contracts.task_execution",
        "TaskExecutionEdge",
    ): "challenge.task_execution_edge.v1",
    (
        "flaghunter.domain.challenge.contracts.task_execution",
        "TaskBrief",
    ): "challenge.task_brief.v1",
    (
        "flaghunter.domain.challenge.contracts.task_execution",
        "TaskExecutionReceipt",
    ): "challenge.task_execution_receipt.v1",
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
        assert getattr(module, "SCHEMA_VERSION") == EXPECTED_SCHEMA_VERSIONS.get(
            module_name,
            1,
        )
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

            assert payload["schemaVersion"] == EXPECTED_CLASS_SCHEMA_VERSIONS.get(
                (module_name, class_name),
                EXPECTED_SCHEMA_VERSIONS.get(module_name, 1),
            )
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


def test_progress_readback_contract_composes_task_and_worker_refs() -> None:
    from flaghunter.domain.challenge.contracts import (
        ChallengeProgressReadback,
        TaskProgressRef,
        WorkerTraceRef,
    )

    progress = ChallengeProgressReadback(
        run_id="run-1",
        task_refs=[
            TaskProgressRef(
                task_id="task-a",
                status="completed",
                title_preview="HTTP/1.1 200 OK\n<html>password=secret</html>",
                evidence_refs=["evidence-a"],
                receipt_refs=["receipt-a"],
            )
        ],
        worker_refs=[
            WorkerTraceRef(
                worker_id="worker-a",
                task_id="task-a",
                worker_type="default",
                status="completed",
                summary_preview="token=worker-token",
            )
        ],
    )

    payload = progress.to_dict()

    assert payload["schemaVersion"] == "challenge.progress.v1"
    assert payload["runId"] == "run-1"
    assert payload["taskRefs"][0]["schemaVersion"] == "challenge.task_progress.v1"
    assert payload["taskRefs"][0]["titlePreview"] == "<redacted raw body>"
    assert payload["workerRefs"][0]["schemaVersion"] == "challenge.worker_trace.v1"
    assert payload["workerRefs"][0]["summaryPreview"] == "token=<redacted>"
    assert payload["summary"] == {
        "taskCount": 1,
        "workerCount": 1,
        "statusCounts": {"completed": 1},
        "workerStatusCounts": {"completed": 1},
    }
    assert ChallengeProgressReadback.from_dict(payload).to_dict() == payload
    _assert_json_friendly(payload)


def test_task_execution_contract_composes_neutral_execution_readback() -> None:
    from flaghunter.domain.challenge.contracts import (
        TaskBrief,
        TaskExecutionEdge,
        TaskExecutionNode,
        TaskExecutionReadback,
        TaskExecutionReceipt,
    )

    readback = TaskExecutionReadback(
        run_id="run-1",
        nodes=[
            TaskExecutionNode(
                node_id="node-a",
                run_id="run-1",
                task_kind="analysis",
                status="completed",
                title_preview="HTTP/1.1 200 OK\n<html>password=task-password</html>",
                claim_ids=["claim-a"],
                trace_ids=["trace-a"],
                receipt_ids=["receipt-a"],
                artifact_refs=["Authorization: Bearer artifact-token"],
            )
        ],
        edges=[
            TaskExecutionEdge(
                source_id="node-a",
                target_id="node-b",
                relation="reports_to",
            )
        ],
        briefs=[
            TaskBrief(
                brief_id="brief-a",
                node_id="node-a",
                run_id="run-1",
                worker_type="default",
                objective_preview="collect token=brief-token",
                allowed_tool_names=["browser"],
            )
        ],
        receipts=[
            TaskExecutionReceipt(
                receipt_id="receipt-a",
                node_id="node-a",
                run_id="run-1",
                worker_id="worker-a",
                worker_type="default",
                status="completed",
                output_summary_preview="password=receipt-password",
            )
        ],
    )

    payload = readback.to_dict()

    assert payload["schemaVersion"] == "challenge.task_execution.v1"
    assert payload["nodes"][0]["schemaVersion"] == "challenge.task_execution_node.v1"
    assert payload["nodes"][0]["titlePreview"] == "<redacted raw body>"
    assert payload["nodes"][0]["artifactRefs"] == ["<redacted>"]
    assert payload["briefs"][0]["objectivePreview"] == "collect token=<redacted>"
    assert payload["receipts"][0]["outputSummaryPreview"] == "password=<redacted>"
    assert payload["summary"] == {
        "nodeCount": 1,
        "edgeCount": 1,
        "briefCount": 1,
        "receiptCount": 1,
        "statusCounts": {"completed": 1},
        "receiptStatusCounts": {"completed": 1},
        "relationCounts": {"reports_to": 1},
    }
    assert TaskExecutionReadback.from_dict(payload).to_dict() == payload
    _assert_json_friendly(payload)


def test_evidence_text_redaction_is_deterministic_and_bounded() -> None:
    from flaghunter.domain.challenge.contracts.evidence import redact_text

    raw = "password=super-secret-token " + ("A" * 80)
    redacted = redact_text(raw, max_chars=40)

    assert "super-secret-token" not in redacted
    assert redacted.startswith("password=[redacted]")
    assert len(redacted) <= 40
    assert redact_text("", max_chars=40) == ""


def test_evidence_contract_uses_shared_sanitization_helpers() -> None:
    path = CONTRACTS_ROOT / "evidence.py"
    tree = _parse(path)
    imported_helpers: set[str] = set()
    duplicate_prefixes = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "sanitization" and node.level == 1:
                imported_helpers.update(alias.name for alias in node.names)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_SENSITIVE_PREFIXES":
                    duplicate_prefixes = True

    assert "redact_sensitive_text" in imported_helpers
    assert duplicate_prefixes is False


def test_sanitization_contract_redacts_raw_text_and_metadata() -> None:
    from flaghunter.domain.challenge.contracts.sanitization import (
        preview_text,
        redact_sensitive_text,
        sanitize_metadata,
    )

    raw_text = (
        "HTTP/1.1 200 OK\n"
        "<html>password=body-password Authorization: Bearer body-token</html>"
    )
    metadata = {
        "authorization": "Bearer metadata-token",
        "safe": "ok",
        "nested": {"password": "nested-password", "note": "visible"},
        "items": ["token=item-token", 3, True, None],
    }

    redacted = redact_sensitive_text("password=secret-token token=api-token")
    legacy_redacted = redact_sensitive_text(
        "password=secret-token token=api-token",
        marker="[redacted]",
    )
    sanitized = sanitize_metadata(metadata, max_chars=80)

    assert redacted == "password=<redacted> token=<redacted>"
    assert legacy_redacted == "password=[redacted] token=[redacted]"
    assert preview_text(raw_text, max_chars=80) == "<redacted raw body>"
    assert sanitized == {
        "authorization": "<redacted>",
        "safe": "ok",
        "nested": {"password": "<redacted>", "note": "visible"},
        "items": ["token=<redacted>", 3, True, None],
    }
    _assert_json_friendly(sanitized)
    for leaked in (
        "body-password",
        "body-token",
        "metadata-token",
        "nested-password",
        "item-token",
    ):
        assert leaked not in repr({"redacted": redacted, "sanitized": sanitized})


def test_control_receipt_payload_matches_legacy_trace_shape() -> None:
    from flaghunter.domain.challenge.contracts.control import (
        build_control_receipt_payload,
    )

    payload = build_control_receipt_payload(
        producer="control:finish",
        success=True,
        stop_reason="all_steps_complete",
        finish_status="answered",
        input_summary="Cookie: session=secret-cookie",
        output_summary="password=secret-password token=secret-token",
        artifact_refs=["Authorization: Bearer secret-auth"],
        answer_kind="plan_completion",
        source_channel="finish_tool",
        selected_claim_id="claim-1",
        selected_verification_record_id="record-1",
        selected_trace_id="trace-1",
        metadata={"ignored_extra": "token=extra"},
    )

    assert payload == {
        "kind": "control_receipt",
        "producer": "control:finish",
        "input_summary": "<redacted>",
        "output_summary": "password=<redacted> token=<redacted>",
        "success": True,
        "artifact_refs": ["<redacted>"],
        "metadata": {
            "answer_kind": "plan_completion",
            "finish_status": "answered",
            "selected_claim_id": "claim-1",
            "selected_trace_id": "trace-1",
            "selected_verification_record_id": "record-1",
            "source_channel": "finish_tool",
            "stop_reason": "all_steps_complete",
        },
    }


def test_control_receipt_contract_round_trips_to_trace_payload() -> None:
    from flaghunter.domain.challenge.contracts.control import ControlReceipt

    receipt = ControlReceipt(
        producer="control:finish",
        success=True,
        input_summary="Cookie: session=secret-cookie",
        output_summary="password=secret-password",
        artifact_refs=["token=artifact-token"],
        metadata={"stop_reason": "all_steps_complete"},
    )

    trace_payload = receipt.to_trace_payload()
    assert trace_payload["kind"] == "control_receipt"
    assert trace_payload["input_summary"] == "<redacted>"
    assert trace_payload["output_summary"] == "password=<redacted>"
    assert trace_payload["artifact_refs"] == ["token=<redacted>"]
    assert trace_payload["metadata"] == {
        "answer_kind": "",
        "finish_status": "",
        "selected_claim_id": "",
        "selected_trace_id": "",
        "selected_verification_record_id": "",
        "source_channel": "",
        "stop_reason": "all_steps_complete",
    }


def test_control_contract_uses_shared_sanitization_helpers() -> None:
    path = CONTRACTS_ROOT / "control.py"
    tree = _parse(path)
    imported_helpers: set[str] = set()
    imports_re = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports_re = imports_re or any(alias.name == "re" for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            if node.module == "sanitization" and node.level == 1:
                imported_helpers.update(alias.name for alias in node.names)

    assert "redact_sensitive_text" in imported_helpers
    assert imports_re is False


def test_evidence_snapshot_contract_builds_legacy_payload_shape() -> None:
    from flaghunter.domain.challenge.contracts.evidence_snapshot import (
        SCHEMA_VERSION as EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
        EvidenceSnapshot,
        build_evidence_snapshot_payload,
    )

    audit_export = {
        "summary": {
            "claimCount": 3,
            "executionTraceCount": 4,
            "verificationRecordCount": 1,
            "verifiedClaimCount": 0,
            "truncatedClaimCount": 1,
            "truncatedExecutionTraceCount": 2,
            "truncatedVerificationRecordCount": 0,
        }
    }
    payload = build_evidence_snapshot_payload(
        trace_refs=[{"claimId": "claim-1"}],
        claim_evidence_refs=[{"claimId": "claim-1"}],
        audit_evidence_export=audit_export,
        p3_solve_snapshot={"schemaVersion": "p3.solve_readback.v1"},
        trace_kinds={"control_receipt", "tool_receipt"},
    )

    assert EVIDENCE_SNAPSHOT_SCHEMA_VERSION == "p2.evidence_snapshot.v1"
    assert payload["schemaVersion"] == "p2.evidence_snapshot.v1"
    assert payload["summary"] == {
        "claimCount": 3,
        "traceCount": 4,
        "verificationRecordCount": 1,
        "hasVerifiedClaim": False,
        "hasControlReceipt": True,
        "hasToolReceipt": True,
        "hasVerificationReceipt": False,
        "truncated": {
            "traceRefs": 2,
            "claimEvidenceRefs": 2,
            "auditClaims": 1,
            "auditTraces": 2,
            "auditVerificationRecords": 0,
        },
    }
    assert EvidenceSnapshot.from_dict(payload).to_dict() == payload


def test_ledger_event_readback_contract_projects_legacy_shape() -> None:
    from flaghunter.domain.challenge.contracts.ledger_events import (
        LedgerEventReadback,
        build_ledger_event_readback,
    )

    readback = build_ledger_event_readback(
        [
            {
                "type": "task_finished",
                "payload": {"token": "ignored-token"},
            },
            {
                "type": "model_call",
                "t": 1.0,
                "payload": {
                    "model": "model token=model-token",
                    "provider": "provider",
                    "status": "success",
                    "duration_ms": 42,
                    "total_tokens": 30,
                },
            },
            {
                "event_type": "handoff_created",
                "ts": 2.0,
                "payload": {
                    "handoff_id": "handoff-1",
                    "source": "web password=source-password",
                    "target": "dispatcher",
                    "decision_kind": "direct",
                    "next_action": "Authorization: Bearer action-token",
                },
            },
        ],
        limit=5,
    )

    assert readback == {
        "refs": [
            {
                "type": "model_call",
                "t": 1.0,
                "model": "model token=<redacted>",
                "provider": "provider",
                "status": "success",
                "durationMs": 42,
                "totalTokens": 30,
            },
            {
                "type": "handoff_created",
                "t": 2.0,
                "handoffId": "handoff-1",
                "source": "web password=<redacted>",
                "target": "dispatcher",
                "decisionKind": "direct",
                "nextAction": "<redacted>",
            },
        ],
        "summary": {
            "countsByType": {
                "model_call": 1,
                "handoff_created": 1,
            },
            "hasModelCall": True,
            "hasStateTransition": False,
            "hasBudgetEvent": False,
            "hasHandoff": True,
        },
    }
    versioned = LedgerEventReadback.from_dict(readback).to_dict()
    assert versioned["schemaVersion"] == "p2.ledger_event_readback.v1"
    assert versioned["refs"] == readback["refs"]
    assert versioned["summary"] == readback["summary"]


def test_ledger_event_contract_uses_shared_sanitization_helpers() -> None:
    path = CONTRACTS_ROOT / "ledger_events.py"
    tree = _parse(path)
    imported_helpers: set[str] = set()
    imports_control = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "sanitization" and node.level == 1:
                imported_helpers.update(alias.name for alias in node.names)
            if node.module == "control" and node.level == 1:
                imports_control = True

    assert "redact_sensitive_text" in imported_helpers
    assert imports_control is False


def test_audit_evidence_contract_builds_legacy_export_shape() -> None:
    from flaghunter.domain.challenge.contracts.audit import (
        AuditEvidenceExport,
        build_audit_evidence_payload,
    )

    payload = build_audit_evidence_payload(
        target="http://target/?token=target-token",
        goal="login password=goal-password",
        stop_reason="done secret=stop-secret",
        claims=[{"claimId": "claim-1"}],
        verification_records=[{"recordId": "record-1"}],
        execution_traces=[{"traceId": "trace-1"}],
        p3_solve_snapshot={"schemaVersion": "p3.solve_readback.v1"},
        claim_count=2,
        verification_record_count=3,
        execution_trace_count=4,
        candidate_claim_count=1,
        accepted_claim_count=0,
        retracted_claim_count=1,
        preview_limit=80,
    )

    assert payload == {
        "schemaVersion": "p2.audit_evidence.v1",
        "target": "http://target/?token=<redacted>",
        "goal": "login password=<redacted>",
        "stopReason": "done secret=<redacted>",
        "summary": {
            "claimCount": 2,
            "exportedClaimCount": 1,
            "truncatedClaimCount": 1,
            "verificationRecordCount": 3,
            "exportedVerificationRecordCount": 1,
            "truncatedVerificationRecordCount": 2,
            "executionTraceCount": 4,
            "exportedExecutionTraceCount": 1,
            "truncatedExecutionTraceCount": 3,
            "candidateClaimCount": 1,
            "verifiedClaimCount": 0,
            "retractedClaimCount": 1,
        },
        "claims": [{"claimId": "claim-1"}],
        "verificationRecords": [{"recordId": "record-1"}],
        "executionTraces": [{"traceId": "trace-1"}],
        "p3SolveSnapshot": {"schemaVersion": "p3.solve_readback.v1"},
    }
    assert AuditEvidenceExport.from_dict(payload).to_dict() == payload


def test_audit_contract_uses_shared_sanitization_helpers() -> None:
    path = CONTRACTS_ROOT / "audit.py"
    tree = _parse(path)
    imported_helpers: set[str] = set()
    imports_control = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "sanitization" and node.level == 1:
                imported_helpers.update(alias.name for alias in node.names)
            if node.module == "control" and node.level == 1:
                imports_control = True

    assert "redact_sensitive_text" in imported_helpers
    assert imports_control is False


def test_task_plan_contract_relocates_legacy_task_dag_plan_objects() -> None:
    import flaghunter.agents.pa_agent.task_dag_plan as legacy_task_plan
    import flaghunter.domain.challenge.contracts.task_dag_plan as domain_task_plan

    exported_names = [
        "TASK_DAG_PLAN_SCHEMA_VERSION",
        "TASK_DAG_READY_SELECTION_SCHEMA_VERSION",
        "TaskDAGStatus",
        "TaskDAGNode",
        "TaskDAGEdge",
        "TaskDAGPlan",
        "TaskDAGGraphError",
        "TaskDAGTransitionError",
        "task_dag_node_to_dict",
        "task_dag_node_from_dict",
        "task_dag_edge_to_dict",
        "task_dag_edge_from_dict",
        "task_dag_plan_to_dict",
        "task_dag_plan_from_dict",
        "sanitize_task_dag_plan",
        "empty_task_dag_plan_readback",
        "empty_task_dag_ready_selection",
        "select_next_ready_task",
        "mark_task_ready",
        "mark_task_running",
        "mark_task_finished",
        "build_task_dag_plan_readback",
    ]

    for name in exported_names:
        assert getattr(legacy_task_plan, name) is getattr(domain_task_plan, name)


def test_task_plan_contract_round_trips_and_builds_readbacks() -> None:
    from flaghunter.domain.challenge.contracts.task_dag_plan import (
        TASK_DAG_PLAN_SCHEMA_VERSION,
        TaskDAGNode,
        TaskDAGPlan,
        TaskDAGStatus,
        build_task_dag_plan_readback,
        mark_task_finished,
        mark_task_ready,
        mark_task_running,
        select_next_ready_task,
        task_dag_plan_from_dict,
        task_dag_plan_to_dict,
    )

    plan = TaskDAGPlan(id="plan-domain", metadata={"token": "plan-token"})
    plan.add_node(TaskDAGNode(id="task-a", status="succeeded"))
    plan.add_node(
        TaskDAGNode(
            id="task-b",
            status="proposed",
            depends_on=["task-a"],
            title="HTTP/1.1 200 OK\n<html>secret</html>",
            goal="collect password=goal-password",
        )
    )

    ready = mark_task_ready(plan, "task-b", reason="dependency done")
    running = mark_task_running(ready, "task-b", started_at=123.0)
    finished = mark_task_finished(
        running,
        "task-b",
        status=TaskDAGStatus.SUCCEEDED,
        receipt_id="receipt-b",
        claim_ids=["claim-b"],
    )

    payload = task_dag_plan_to_dict(finished)
    restored = task_dag_plan_from_dict(payload)
    readback = build_task_dag_plan_readback(restored)

    assert payload["schemaVersion"] == TASK_DAG_PLAN_SCHEMA_VERSION
    assert restored.get_node("task-b").depends_on == ["task-a"]
    assert select_next_ready_task(restored)["reason"] == "no_ready_tasks"
    assert readback["summary"]["statusCounts"] == {"succeeded": 2}
    assert readback["nodes"][1]["titlePreview"] == "<redacted raw body>"
    assert "goal-password" not in repr(readback)
    _assert_json_friendly(payload)
    _assert_json_friendly(readback)


def test_task_plan_contract_uses_shared_sanitization_helpers() -> None:
    path = CONTRACTS_ROOT / "task_dag_plan.py"
    tree = _parse(path)
    imported_helpers: set[str] = set()
    duplicate_helpers: set[str] = set()
    imports_re = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports_re = imports_re or any(alias.name == "re" for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            if node.module == "sanitization" and node.level == 1:
                imported_helpers.update(alias.name for alias in node.names)
        if isinstance(node, ast.FunctionDef):
            if node.name in {"_redact_text", "_looks_like_raw_body", "_is_sensitive_key"}:
                duplicate_helpers.add(node.name)

    assert {
        "is_sensitive_key",
        "looks_like_raw_body",
        "redact_sensitive_text",
    } <= imported_helpers
    assert imports_re is False
    assert duplicate_helpers == set()


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
