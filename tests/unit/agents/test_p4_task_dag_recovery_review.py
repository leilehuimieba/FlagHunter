from __future__ import annotations

from flaghunter.agents.pa_agent.task_dag_recovery_proposal_readback import (
    TASK_DAG_RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION,
    TaskDAGRecoveryProposalRecord,
)
from flaghunter.agents.pa_agent.task_dag_recovery_review import (
    TASK_DAG_RECOVERY_REVIEW_SCHEMA_VERSION,
    TaskDAGRecoveryReview,
    build_task_dag_recovery_review,
    select_task_dag_recovery_proposal,
)


def _record(
    proposal_id: str,
    *,
    task_id: str = "task-a",
    action: str = "propose_recovery",
    recommended_action: str = "retry_task",
    priority: str = "normal",
    confidence: float = 0.5,
    created_at: float = 0.0,
    valid: bool = True,
    warnings: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> TaskDAGRecoveryProposalRecord:
    return TaskDAGRecoveryProposalRecord(
        schema_version=TASK_DAG_RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION,
        source_schema_version="p4c.task_dag_recovery_proposal.v1",
        proposal_id=proposal_id,
        action=action,
        task_id=task_id,
        source_receipt_id=f"receipt-{proposal_id}",
        source_status="failed",
        recovery_reason="task_failed",
        recommended_action=recommended_action,
        confidence=confidence,
        priority=priority,
        evidence_refs=[f"trace-{proposal_id}", f"claim-{proposal_id}"],
        warnings=warnings or [],
        metadata=metadata or {"source_kind": "dry"},
        created_at=created_at,
        valid=valid,
    )


def test_p4c_d_empty_input_returns_compact_no_action_review() -> None:
    review = select_task_dag_recovery_proposal([])
    payload = review.to_dict()

    assert isinstance(review, TaskDAGRecoveryReview)
    assert payload["schemaVersion"] == TASK_DAG_RECOVERY_REVIEW_SCHEMA_VERSION
    assert payload["selectedProposalId"] == ""
    assert payload["recommendedAction"] == "no_action"
    assert payload["attention"] == "none"
    assert payload["valid"] is True
    assert "no_recovery_proposals" in payload["warnings"]
    assert payload["summary"]["inputCount"] == 0


def test_p4c_d_all_invalid_records_do_not_create_execution_action() -> None:
    review = select_task_dag_recovery_proposal(
        [
            _record(
                "proposal-invalid",
                action="invalid",
                recommended_action="retry_task",
                valid=False,
                warnings=["invalid_schema"],
            )
        ]
    )
    payload = review.to_dict()

    assert payload["selectedProposalId"] == ""
    assert payload["recommendedAction"] in {"no_action", "manual_review"}
    assert payload["attention"] in {"none", "review"}
    assert payload["valid"] is True
    assert "no_valid_recovery_proposals" in payload["warnings"]


def test_p4c_d_selects_high_manual_review_over_low_no_action_and_invalid() -> None:
    low = _record(
        "proposal-low",
        task_id="task-low",
        recommended_action="no_action",
        priority="low",
        confidence=1.0,
        created_at=1,
    )
    invalid = _record(
        "proposal-invalid",
        task_id="task-invalid",
        recommended_action="mark_blocked",
        priority="high",
        confidence=1.0,
        created_at=0,
        valid=False,
    )
    manual = _record(
        "proposal-manual",
        task_id="task-manual",
        recommended_action="manual_review",
        priority="high",
        confidence=0.4,
        created_at=3,
    )

    review = select_task_dag_recovery_proposal([low, invalid, manual])
    payload = review.to_dict()

    assert payload["selectedProposalId"] == "proposal-manual"
    assert payload["taskId"] == "task-manual"
    assert payload["recommendedAction"] == "manual_review"
    assert payload["attention"] == "urgent"
    assert payload["summary"]["validCount"] == 2
    assert payload["summary"]["invalidCount"] == 1


def test_p4c_d_tie_break_is_deterministic_by_confidence_created_and_id() -> None:
    first = _record(
        "proposal-b",
        recommended_action="retry_task",
        priority="high",
        confidence=0.8,
        created_at=20,
    )
    second = _record(
        "proposal-a",
        recommended_action="retry_task",
        priority="high",
        confidence=0.8,
        created_at=10,
    )
    third = _record(
        "proposal-c",
        recommended_action="retry_task",
        priority="high",
        confidence=0.8,
        created_at=10,
    )

    review_a = select_task_dag_recovery_proposal([first, second, third])
    review_b = select_task_dag_recovery_proposal([third, first, second])

    assert review_a.selected_proposal_id == "proposal-a"
    assert review_a.review_id == review_b.review_id
    assert review_a.to_dict() == review_b.to_dict()


def test_p4c_d_recommended_action_is_proposal_only_allowlist() -> None:
    review = select_task_dag_recovery_proposal(
        [
            _record(
                "proposal-bad-action",
                recommended_action="dispatch_now",
                priority="high",
                confidence=1.0,
            )
        ]
    )
    payload = review.to_dict()

    assert payload["recommendedAction"] == "no_action"
    assert "dispatch" not in "".join(payload)
    assert "executeAction" not in payload
    assert "dispatchAction" not in payload
    assert "applyRecovery" not in payload


def test_p4c_d_bounded_output_redacts_sensitive_and_raw_metadata() -> None:
    review = select_task_dag_recovery_proposal(
        [
            _record(
                "proposal-sensitive",
                recommended_action="manual_review",
                priority="high",
                confidence=0.9,
                warnings=[f"warning-{index}-" + ("W" * 300) for index in range(12)],
                metadata={
                    "authorization": "Bearer metadata-auth",
                    "session": "session-secret",
                    "long": "L" * 300,
                    "raw": "HTTP/1.1 500 ERROR\n<html>password=body-secret</html>",
                    "safe": "ok",
                },
            )
        ]
    )
    payload = review.to_dict()
    text = repr(payload)

    assert len(payload["reviewReason"]) <= 160
    assert len(payload["evidenceRefs"]) == 2
    assert len(payload["warnings"]) == 10
    assert all(len(item) <= 160 for item in payload["warnings"])
    assert len(payload["metadata"]["long"]) <= 160
    assert "<redacted>" in text
    assert "<redacted raw body>" in text
    for leaked in ("metadata-auth", "session-secret", "body-secret", "<html>"):
        assert leaked not in text


def test_p4c_d_direct_review_construction_strips_proof_like_metadata_and_summary() -> None:
    review = TaskDAGRecoveryReview(
        schema_version="",
        review_id="review-proof",
        selected_proposal_id="proposal-a",
        task_id="task-a",
        review_reason="manual review",
        recommended_action="manual_review",
        attention="review",
        confidence=1,
        metadata={
            "verification_decision": "bad",
            "verified_flags": ["flag{bad}"],
            "verifierProof": "proof",
            "proof_level": "runtime",
            "verificationRecordId": "record-a",
            "verifiedFlag": "flag{bad}",
            "flag_level": "verified",
            "flag_verified": True,
            "verifier_decision": "accepted",
            "note": 'level="verified"',
            "safe": "ok",
        },
        summary={
            "verification_decision": 1,
            "verified_flags": 2,
            'level="verified"': 3,
            "safeCount": 4,
        },
    )
    payload = review.to_dict()
    text = repr(payload)

    assert payload["metadata"] == {"safe": "ok"}
    assert payload["summary"] == {"safeCount": 4}
    for forbidden in (
        "verification_decision",
        "verified_flags",
        "verifierProof",
        "proof_level",
        "verificationRecordId",
        "verifiedFlag",
        "flag_level",
        "flag_verified",
        "verifier_decision",
        'level="verified"',
        "flag{bad}",
    ):
        assert forbidden not in text


def test_p4c_d_to_dict_is_schema_versioned_compact_and_id_is_deterministic() -> None:
    records = [
        _record(
            "proposal-stable",
            recommended_action="request_more_evidence",
            priority="normal",
            confidence=0.7,
            created_at=5,
        )
    ]

    first = build_task_dag_recovery_review(records)
    second = build_task_dag_recovery_review([record.to_dict() for record in records])
    payload = first.to_dict()

    assert first.review_id == second.review_id
    assert payload["schemaVersion"] == TASK_DAG_RECOVERY_REVIEW_SCHEMA_VERSION
    assert payload["reviewId"] == first.review_id
    assert payload["selectedProposalId"] == "proposal-stable"
    assert payload["summary"]["inputCount"] == 1
    assert "records" not in payload
    assert "proposals" not in payload
