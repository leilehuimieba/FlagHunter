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
    "flaghunter.eval",
    "flaghunter.interface",
    "flaghunter.knowledge",
    "flaghunter.llm",
    "flaghunter.mcp",
    "flaghunter.redteam",
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


def test_board_read_model_sanitizes_raw_values_and_metadata() -> None:
    from flaghunter.domain.challenge.contracts import (
        BoardItem,
        ChallengeBoardReadModel,
    )

    item = BoardItem(
        item_id="fact-raw",
        item_type="evidence",
        value="HTTP/1.1 200 OK\n<html>password=body-password</html>",
        source_ref="Authorization: Bearer source-token",
        metadata={
            "authorization": "Bearer metadata-token",
            "safe": "visible",
            "raw_output": "HTTP/1.1 200 OK\n<html>token=raw-token</html>",
            "nested": {"password": "nested-password"},
        },
    )
    model = ChallengeBoardReadModel(
        run_id="run-raw",
        challenge_id="challenge-raw",
        facts=[item],
        decisions=[{"reason": "token=decision-token"}],
        recommended_task={"summary": "password=task-password"},
        metadata={"raw_body": "HTTP/1.1 200 OK\n<html>secret</html>"},
    )

    payload = model.to_dict()

    assert payload["facts"][0]["value"] == "<redacted raw body>"
    assert payload["facts"][0]["sourceRef"] == "<redacted>"
    assert payload["facts"][0]["metadata"] == {
        "authorization": "<redacted>",
        "safe": "visible",
        "raw_output": "<redacted raw body>",
        "nested": {"password": "<redacted>"},
    }
    assert payload["decisions"] == [{"reason": "token=<redacted>"}]
    assert payload["recommendedTask"] == {"summary": "password=<redacted>"}
    assert payload["metadata"] == {"raw_body": "<redacted raw body>"}
    for leaked in (
        "body-password",
        "source-token",
        "metadata-token",
        "raw-token",
        "nested-password",
        "decision-token",
        "task-password",
    ):
        assert leaked not in repr(payload)
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


def test_build_promotes_neutral_board_metadata_to_read_model_fields() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        BuildChallengeBoardReadModel,
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import ChallengeRunSnapshot

    snapshot = ChallengeRunSnapshot(
        run_id="run-board-metadata",
        challenge_id="challenge-board-metadata",
        metadata={
            "decisions": [
                {
                    "nextAction": "collect_initial_facts",
                    "strongestHypothesisKind": "generic_web_recon",
                }
            ],
            "candidates": [
                {"action": "collect_initial_facts", "selected": True},
                {"action": "probe_discovered_endpoint", "selected": False},
            ],
            "actionResults": [
                {"action": "collect_initial_facts", "result": "failed"}
            ],
            "recommendedTask": {
                "action": "probe_discovered_endpoint",
                "reason": "continue from neutral metadata",
            },
            "surfaceRefs": [{"endpoint": "http://challenge.test/admin"}],
            "hypotheses": [{"kind": "generic_web_recon", "confidence": 0.5}],
        },
    )

    model = BuildChallengeBoardReadModel().build(snapshot)
    payload = model.to_dict()
    projection = build_task_board_projection(model)

    assert payload["decisions"] == [
        {
            "nextAction": "collect_initial_facts",
            "strongestHypothesisKind": "generic_web_recon",
        }
    ]
    assert payload["candidates"] == [
        {"action": "collect_initial_facts", "selected": True},
        {"action": "probe_discovered_endpoint", "selected": False},
    ]
    assert payload["actionResults"] == [
        {"action": "collect_initial_facts", "result": "failed"}
    ]
    assert payload["recommendedTask"] == {
        "action": "probe_discovered_endpoint",
        "reason": "continue from neutral metadata",
    }
    assert payload["surfaceRefs"] == [{"endpoint": "http://challenge.test/admin"}]
    assert payload["metadata"] == {
        "hypotheses": [{"kind": "generic_web_recon", "confidence": 0.5}]
    }
    assert projection["active_decision"] == {
        "nextAction": "collect_initial_facts",
        "strongestHypothesisKind": "generic_web_recon",
    }
    assert projection["recommended_action"] == {
        "action": "probe_discovered_endpoint",
        "reason": "continue from neutral metadata",
    }
    assert projection["attack_surfaces"] == [
        {"endpoint": "http://challenge.test/admin"}
    ]
    _assert_json_friendly(payload)
    _assert_json_friendly(projection)


def test_build_promotes_board_metadata_aliases_to_read_model_fields() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        BuildChallengeBoardReadModel,
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import ChallengeRunSnapshot

    snapshot = ChallengeRunSnapshot(
        run_id="run-board-aliases",
        challenge_id="challenge-board-aliases",
        metadata={
            "activeDecision": {
                "nextAction": "verify_runtime_signal",
                "driver": "board.proof_candidate",
            },
            "recommendedAction": {
                "action": "collect_initial_facts",
                "reason": "camel-case source",
            },
            "action_results": [
                {"action": "verify_runtime_signal", "result": "skipped"}
            ],
            "attack_surfaces": [{"endpoint": "http://challenge.test/status"}],
        },
    )

    model = BuildChallengeBoardReadModel().build(snapshot)
    payload = model.to_dict()
    projection = build_task_board_projection(model)

    assert payload["decisions"] == [
        {
            "nextAction": "verify_runtime_signal",
            "driver": "board.proof_candidate",
        }
    ]
    assert payload["recommendedTask"] == {
        "action": "collect_initial_facts",
        "reason": "camel-case source",
    }
    assert payload["actionResults"] == [
        {"action": "verify_runtime_signal", "result": "skipped"}
    ]
    assert payload["surfaceRefs"] == [{"endpoint": "http://challenge.test/status"}]
    assert payload["metadata"] == {}
    assert projection["active_decision"] == {
        "nextAction": "verify_runtime_signal",
        "driver": "board.proof_candidate",
    }
    assert projection["recommended_action"] == {
        "action": "collect_initial_facts",
        "reason": "camel-case source",
    }
    assert projection["attack_surfaces"] == [
        {"endpoint": "http://challenge.test/status"}
    ]
    _assert_json_friendly(payload)
    _assert_json_friendly(projection)


def test_task_board_projection_matches_candidate_a_public_shape() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import (
        BoardItem,
        ChallengeBoardReadModel,
    )

    model = ChallengeBoardReadModel(
        run_id="run-a",
        challenge_id="challenge-a",
        facts=[
            BoardItem(
                item_id="fact-1",
                item_type="next_action",
                value="collect_initial_facts",
                source_ref="ingress",
                confidence=0.75,
                metadata={"rationale": "continue from checkpoint"},
            )
        ],
        evidence=[
            BoardItem(
                item_id="pending-1",
                item_type="runtime_flag",
                value="candidate-answer",
                source_ref="runtime",
                metadata={
                    "boardBucket": "pendingVerification",
                    "rationale": "needs review",
                },
            )
        ],
        decisions=[{"nextAction": "collect_initial_facts"}],
        candidates=[{"action": "collect_initial_facts", "selected": True}],
        action_results=[{"action": "collect_initial_facts", "result": "ok"}],
        recommended_task={"action": "probe_discovered_endpoint"},
        surface_refs=[{"endpoint": "http://challenge.test/admin", "score": 0.5}],
        metadata={"hypotheses": [{"kind": "generic_web_recon", "confidence": 0.5}]},
    )

    projection = build_task_board_projection(model)

    assert projection == {
        "facts": [
            {
                "kind": "next_action",
                "value": "collect_initial_facts",
                "source": "ingress",
                "confidence": 0.75,
                "rationale": "continue from checkpoint",
            }
        ],
        "hypotheses": [{"kind": "generic_web_recon", "confidence": 0.5}],
        "pending_verifications": [
            {
                "kind": "runtime_flag",
                "value": "candidate-answer",
                "source": "runtime",
                "rationale": "needs review",
            }
        ],
        "decisions": [{"nextAction": "collect_initial_facts"}],
        "candidates": [{"action": "collect_initial_facts", "selected": True}],
        "active_decision": {"nextAction": "collect_initial_facts"},
        "action_results": [{"action": "collect_initial_facts", "result": "ok"}],
        "recommended_action": {"action": "probe_discovered_endpoint"},
        "attack_surfaces": [{"endpoint": "http://challenge.test/admin", "score": 0.5}],
    }
    _assert_json_friendly(projection)


def test_task_board_projection_promotes_non_pending_evidence_to_facts() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import (
        BoardItem,
        ChallengeBoardReadModel,
    )

    model = ChallengeBoardReadModel(
        run_id="run-evidence",
        challenge_id="challenge-evidence",
        evidence=[
            BoardItem(
                item_id="evidence-fact",
                item_type="discovered_endpoint",
                value="http://challenge.test/admin",
                source_ref="neutral-evidence",
                confidence=0.8,
                metadata={"rationale": "observed during read model build"},
            ),
            BoardItem(
                item_id="pending-evidence",
                item_type="runtime_flag",
                value="candidate-answer",
                metadata={"boardBucket": "pendingVerification"},
            ),
        ],
    )

    projection = build_task_board_projection(model)

    assert projection["facts"] == [
        {
            "kind": "discovered_endpoint",
            "value": "http://challenge.test/admin",
            "source": "neutral-evidence",
            "confidence": 0.8,
            "rationale": "observed during read model build",
        }
    ]
    assert projection["pending_verifications"] == [
        {"kind": "runtime_flag", "value": "candidate-answer"}
    ]
    _assert_json_friendly(projection)


def test_task_board_projection_is_quiet_for_empty_or_malformed_inputs() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )

    expected_empty = {
        "facts": [],
        "hypotheses": [],
        "pending_verifications": [],
        "decisions": [],
        "candidates": [],
        "active_decision": {},
        "action_results": [],
        "recommended_action": {},
        "attack_surfaces": [],
    }

    assert build_task_board_projection(None) == expected_empty
    assert build_task_board_projection(
        {
            "facts": ["ignored"],
            "evidence": "not-a-list",
            "decisions": [{"nextAction": "collect_initial_facts"}, "ignored"],
            "recommendedTask": "not-a-mapping",
            "surfaceRefs": [{"endpoint": "http://challenge.test/admin"}, "ignored"],
            "metadata": {"hypotheses": "not-a-list"},
        }
    ) == {
        **expected_empty,
        "decisions": [{"nextAction": "collect_initial_facts"}],
        "active_decision": {"nextAction": "collect_initial_facts"},
        "attack_surfaces": [{"endpoint": "http://challenge.test/admin"}],
    }


def test_task_board_projection_omits_malformed_board_item_rows() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )

    projection = build_task_board_projection(
        {
            "facts": [
                {},
                {"itemType": "", "value": "blank kind"},
                {"itemType": "observed_fact", "value": "kept"},
            ],
            "evidence": [
                {"metadata": {"boardBucket": "pendingVerification"}},
                {
                    "itemType": "",
                    "value": "blank pending kind",
                    "metadata": {"boardBucket": "pendingVerification"},
                },
                {
                    "itemType": "pending_answer",
                    "value": "candidate",
                    "metadata": {"boardBucket": "pendingVerification"},
                },
                {"itemType": "evidence_fact", "value": "observed"},
            ],
        }
    )

    assert projection["facts"] == [
        {"kind": "observed_fact", "value": "kept"},
        {"kind": "evidence_fact", "value": "observed"},
    ]
    assert projection["pending_verifications"] == [
        {"kind": "pending_answer", "value": "candidate"}
    ]
    _assert_json_friendly(projection)


def test_task_board_projection_derives_recommended_action_from_candidate_results() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import ChallengeBoardReadModel

    model = ChallengeBoardReadModel(
        run_id="run-recommendation",
        challenge_id="challenge-recommendation",
        decisions=[
            {
                "nextAction": "collect_initial_facts",
                "strongestHypothesisKind": "generic_web_recon",
                "strongestHypothesisStatus": "active",
                "strongestHypothesisConfidence": 0.52,
            }
        ],
        candidates=[
            {
                "action": "collect_initial_facts",
                "driver": "board.derived_target",
                "sourceType": "observation",
                "selected": True,
                "recommended": False,
            },
            {
                "action": "probe_discovered_endpoint",
                "driver": "board.discovered_endpoint",
                "sourceType": "observation",
                "recommended": False,
            },
        ],
        action_results=[
            {
                "action": "collect_initial_facts",
                "driver": "board.derived_target",
                "result": "failed",
                "details": {"reason": "no new facts"},
                "t": "2026-06-03T10:00:02+00:00",
            }
        ],
    )

    projection = build_task_board_projection(model)

    assert projection["recommended_action"] == {
        "action": "probe_discovered_endpoint",
        "driver": "board.discovered_endpoint",
        "sourceType": "observation",
        "reason": "selected action failed; switch to next best candidate",
        "switchedFrom": "collect_initial_facts",
        "triggerResult": "failed",
        "triggerReason": "no new facts",
        "triggerActionDriver": "board.derived_target",
        "triggerAt": "2026-06-03T10:00:02+00:00",
        "strongestHypothesisKind": "generic_web_recon",
        "strongestHypothesisStatus": "active",
        "strongestHypothesisConfidence": 0.52,
    }
    assert projection["candidates"][1]["recommended"] is True
    _assert_json_friendly(projection)


def test_task_board_projection_accepts_hypothesis_summary_aliases() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import ChallengeBoardReadModel

    model = ChallengeBoardReadModel(
        run_id="run-hypothesis-aliases",
        challenge_id="challenge-hypothesis-aliases",
        decisions=[{"nextAction": "collect_initial_facts"}],
        candidates=[
            {
                "action": "collect_initial_facts",
                "priority": 20,
                "selected": True,
            },
            {
                "action": "probe_discovered_endpoint",
                "priority": 11,
            },
        ],
        action_results=[
            {
                "action": "collect_initial_facts",
                "result": "failed",
                "strongest_hypothesis_kind": "generic_web_recon",
                "strongest_hypothesis_status": "active",
                "strongest_hypothesis_confidence": 0.62,
            }
        ],
    )

    projection = build_task_board_projection(model)

    assert projection["recommended_action"] == {
        "action": "probe_discovered_endpoint",
        "driver": "",
        "sourceType": "",
        "reason": "selected action failed; switch to next best candidate",
        "switchedFrom": "collect_initial_facts",
        "triggerResult": "failed",
        "strongestHypothesisKind": "generic_web_recon",
        "strongestHypothesisStatus": "active",
        "strongestHypothesisConfidence": 0.62,
    }
    recommended = [
        item
        for item in projection["candidates"]
        if item["action"] == "probe_discovered_endpoint"
    ][0]
    assert recommended["strongestHypothesisKind"] == "generic_web_recon"
    assert recommended["strongestHypothesisStatus"] == "active"
    assert recommended["strongestHypothesisConfidence"] == 0.62
    _assert_json_friendly(projection)


def test_task_board_projection_accepts_candidate_source_type_alias() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import ChallengeBoardReadModel

    model = ChallengeBoardReadModel(
        run_id="run-source-type-alias",
        challenge_id="challenge-source-type-alias",
        decisions=[{"nextAction": "collect_initial_facts"}],
        candidates=[
            {
                "action": "collect_initial_facts",
                "priority": 20,
                "selected": True,
            },
            {
                "action": "probe_discovered_endpoint",
                "driver": "board.discovered_endpoint",
                "source_type": "observation",
                "priority": 11,
            },
        ],
        action_results=[
            {
                "action": "collect_initial_facts",
                "result": "failed",
            }
        ],
    )

    projection = build_task_board_projection(model)

    assert projection["recommended_action"] == {
        "action": "probe_discovered_endpoint",
        "driver": "board.discovered_endpoint",
        "sourceType": "observation",
        "reason": "selected action failed; switch to next best candidate",
        "switchedFrom": "collect_initial_facts",
        "triggerResult": "failed",
    }
    recommended = [
        item
        for item in projection["candidates"]
        if item["action"] == "probe_discovered_endpoint"
    ][0]
    assert recommended["sourceType"] == "observation"
    _assert_json_friendly(projection)


def test_task_board_projection_accepts_action_result_trigger_reason_alias() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import ChallengeBoardReadModel

    model = ChallengeBoardReadModel(
        run_id="run-trigger-reason-alias",
        challenge_id="challenge-trigger-reason-alias",
        decisions=[{"nextAction": "collect_initial_facts"}],
        candidates=[
            {
                "action": "collect_initial_facts",
                "priority": 20,
                "selected": True,
            },
            {
                "action": "probe_discovered_endpoint",
                "priority": 11,
            },
        ],
        action_results=[
            {
                "action": "collect_initial_facts",
                "result": "failed",
                "trigger_reason": "direct trigger alias",
            }
        ],
    )

    projection = build_task_board_projection(model)

    assert projection["recommended_action"] == {
        "action": "probe_discovered_endpoint",
        "driver": "",
        "sourceType": "",
        "reason": "selected action failed; switch to next best candidate",
        "switchedFrom": "collect_initial_facts",
        "triggerResult": "failed",
        "triggerReason": "direct trigger alias",
    }
    recommended = [
        item
        for item in projection["candidates"]
        if item["action"] == "probe_discovered_endpoint"
    ][0]
    assert recommended["triggerReason"] == "direct trigger alias"
    _assert_json_friendly(projection)


def test_task_board_projection_accepts_action_result_trigger_driver_alias() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import ChallengeBoardReadModel

    model = ChallengeBoardReadModel(
        run_id="run-trigger-driver-alias",
        challenge_id="challenge-trigger-driver-alias",
        decisions=[{"nextAction": "collect_initial_facts"}],
        candidates=[
            {
                "action": "collect_initial_facts",
                "priority": 20,
                "selected": True,
            },
            {
                "action": "probe_discovered_endpoint",
                "priority": 11,
            },
        ],
        action_results=[
            {
                "action": "collect_initial_facts",
                "result": "failed",
                "trigger_action_driver": "board.alias_driver",
            }
        ],
    )

    projection = build_task_board_projection(model)

    assert projection["recommended_action"] == {
        "action": "probe_discovered_endpoint",
        "driver": "",
        "sourceType": "",
        "reason": "selected action failed; switch to next best candidate",
        "switchedFrom": "collect_initial_facts",
        "triggerResult": "failed",
        "triggerActionDriver": "board.alias_driver",
    }
    recommended = [
        item
        for item in projection["candidates"]
        if item["action"] == "probe_discovered_endpoint"
    ][0]
    assert recommended["triggerActionDriver"] == "board.alias_driver"
    _assert_json_friendly(projection)


def test_task_board_projection_enriches_selected_and_recommended_candidates() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import ChallengeBoardReadModel

    model = ChallengeBoardReadModel(
        run_id="run-candidate-enrichment",
        challenge_id="challenge-candidate-enrichment",
        decisions=[
            {
                "nextAction": "collect_initial_facts",
                "driver": "board.derived_target",
                "reason": "continue from current observation",
                "strongestHypothesisKind": "generic_web_recon",
                "strongestHypothesisStatus": "active",
                "strongestHypothesisConfidence": 0.52,
            }
        ],
        candidates=[
            {
                "action": "collect_initial_facts",
                "selected": True,
                "recommended": False,
            },
            {
                "action": "probe_discovered_endpoint",
                "driver": "board.discovered_endpoint",
                "sourceType": "observation",
                "recommended": False,
            },
        ],
        action_results=[
            {
                "action": "collect_initial_facts",
                "driver": "board.derived_target",
                "result": "failed",
                "details": {"reason": "no new facts"},
                "t": "2026-06-03T10:00:02+00:00",
            }
        ],
    )

    projection = build_task_board_projection(model)

    selected = [
        item
        for item in projection["candidates"]
        if item["action"] == "collect_initial_facts"
    ][0]
    recommended = [
        item
        for item in projection["candidates"]
        if item["action"] == "probe_discovered_endpoint"
    ][0]
    assert selected["driver"] == "board.derived_target"
    assert selected["reason"] == "continue from current observation"
    assert selected["strongestHypothesisKind"] == "generic_web_recon"
    assert selected["strongestHypothesisStatus"] == "active"
    assert selected["strongestHypothesisConfidence"] == 0.52
    assert recommended["recommended"] is True
    assert recommended["triggerReason"] == "no new facts"
    assert recommended["triggerActionDriver"] == "board.derived_target"
    assert recommended["triggerAt"] == "2026-06-03T10:00:02+00:00"
    assert recommended["strongestHypothesisKind"] == "generic_web_recon"
    assert recommended["strongestHypothesisStatus"] == "active"
    assert recommended["strongestHypothesisConfidence"] == 0.52
    _assert_json_friendly(projection)


def test_task_board_projection_orders_candidates_and_projects_last_result() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import ChallengeBoardReadModel

    model = ChallengeBoardReadModel(
        run_id="run-candidate-ordering",
        challenge_id="challenge-candidate-ordering",
        candidates=[
            {
                "action": "probe_discovered_endpoint",
                "priority": 11,
                "recommended": False,
            },
            {
                "action": "collect_initial_facts",
                "priority": 20,
                "recommended": False,
                "lastResult": "stale",
            },
            {
                "action": "verify_runtime_signal",
                "priority": 2,
                "recommended": False,
            },
        ],
        action_results=[
            {
                "action": "collect_initial_facts",
                "result": "failed",
                "details": {"reason": "old failure"},
                "t": "2026-06-03T10:00:01+00:00",
            },
            {
                "action": "verify_runtime_signal",
                "result": "ok",
                "t": "2026-06-03T10:00:02+00:00",
            },
            {
                "action": "collect_initial_facts",
                "result": "skipped",
                "details": {"reason": "latest result wins"},
                "t": "2026-06-03T10:00:03+00:00",
            },
        ],
    )

    projection = build_task_board_projection(model)

    assert [item["action"] for item in projection["candidates"]] == [
        "verify_runtime_signal",
        "probe_discovered_endpoint",
        "collect_initial_facts",
    ]
    assert projection["candidates"] == [
        {
            "action": "verify_runtime_signal",
            "priority": 2,
            "recommended": False,
            "lastResult": "ok",
        },
        {
            "action": "probe_discovered_endpoint",
            "priority": 11,
            "recommended": False,
        },
        {
            "action": "collect_initial_facts",
            "priority": 20,
            "recommended": False,
            "lastResult": "skipped",
        },
    ]
    _assert_json_friendly(projection)


def test_task_board_projection_adds_default_recommended_marker_for_ordered_candidates() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import ChallengeBoardReadModel

    model = ChallengeBoardReadModel(
        run_id="run-candidate-marker",
        challenge_id="challenge-candidate-marker",
        candidates=[
            {
                "action": "collect_initial_facts",
                "priority": 20,
            },
            {
                "action": "probe_discovered_endpoint",
                "priority": 11,
            },
        ],
    )

    projection = build_task_board_projection(model)

    assert projection["candidates"] == [
        {
            "action": "probe_discovered_endpoint",
            "priority": 11,
            "recommended": False,
        },
        {
            "action": "collect_initial_facts",
            "priority": 20,
            "recommended": False,
        },
    ]
    _assert_json_friendly(projection)


def test_task_board_projection_marks_explicit_recommended_candidate() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import ChallengeBoardReadModel

    model = ChallengeBoardReadModel(
        run_id="run-explicit-recommendation",
        challenge_id="challenge-explicit-recommendation",
        decisions=[{"nextAction": "collect_initial_facts"}],
        candidates=[
            {
                "action": "collect_initial_facts",
                "selected": True,
                "recommended": False,
            },
            {
                "action": "probe_discovered_endpoint",
                "selected": False,
                "recommended": False,
            },
        ],
        action_results=[
            {
                "action": "collect_initial_facts",
                "result": "failed",
                "details": {"reason": "derive would include this"},
            }
        ],
        recommended_task={
            "action": "probe_discovered_endpoint",
            "reason": "explicit neutral planner hint",
        },
    )

    projection = build_task_board_projection(model)

    assert projection["recommended_action"] == {
        "action": "probe_discovered_endpoint",
        "reason": "explicit neutral planner hint",
    }
    assert projection["candidates"] == [
        {
            "action": "collect_initial_facts",
            "selected": True,
            "recommended": False,
        },
        {
            "action": "probe_discovered_endpoint",
            "selected": False,
            "recommended": True,
        },
    ]
    assert "derive would include this" not in repr(projection["recommended_action"])
    _assert_json_friendly(projection)


def test_task_board_projection_omits_malformed_candidate_and_action_rows() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )

    projection = build_task_board_projection(
        {
            "candidates": [
                {},
                {"action": "", "selected": True},
                {"action": "collect_initial_facts", "selected": True},
            ],
            "actionResults": [
                {},
                {"action": "", "result": "failed"},
                {"action": "collect_initial_facts"},
                {"result": "failed"},
                {"action": "collect_initial_facts", "result": "failed"},
            ],
        }
    )

    assert projection["candidates"] == [
        {"action": "collect_initial_facts", "selected": True}
    ]
    assert projection["action_results"] == [
        {"action": "collect_initial_facts", "result": "failed"}
    ]
    _assert_json_friendly(projection)


def test_task_board_projection_respects_suppressed_recommendation() -> None:
    from flaghunter.application.challenge.board_read_model_service import (
        build_task_board_projection,
    )
    from flaghunter.domain.challenge.contracts import ChallengeBoardReadModel

    model = ChallengeBoardReadModel(
        run_id="run-suppressed-recommendation",
        challenge_id="challenge-suppressed-recommendation",
        decisions=[
            {
                "nextAction": "verify_or_submit_proof",
                "suppressedRecommendation": {
                    "action": "collect_initial_facts",
                    "driver": "board.derived_target",
                    "reason": "higher priority proof candidate present",
                    "suppressedBy": "board.proof_candidate",
                },
            }
        ],
        candidates=[
            {
                "action": "verify_or_submit_proof",
                "selected": True,
                "recommended": False,
            },
            {
                "action": "collect_initial_facts",
                "selected": False,
                "recommended": False,
            },
        ],
        action_results=[
            {
                "action": "verify_or_submit_proof",
                "driver": "board.proof_candidate",
                "result": "failed",
                "details": {"reason": "would derive without suppression"},
            }
        ],
    )

    projection = build_task_board_projection(model)

    assert projection["active_decision"]["suppressedRecommendation"] == {
        "action": "collect_initial_facts",
        "driver": "board.derived_target",
        "reason": "higher priority proof candidate present",
        "suppressedBy": "board.proof_candidate",
    }
    assert projection["recommended_action"] == {}
    assert projection["candidates"] == [
        {
            "action": "verify_or_submit_proof",
            "selected": True,
            "recommended": False,
        },
        {
            "action": "collect_initial_facts",
            "selected": False,
            "recommended": False,
        },
    ]
    assert "would derive without suppression" not in repr(projection["recommended_action"])
    _assert_json_friendly(projection)


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
