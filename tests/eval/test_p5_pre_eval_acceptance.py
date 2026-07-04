from __future__ import annotations

from pathlib import Path

from flaghunter.agents.pa_agent.task_dag_replay_audit_bundle import (
    build_task_dag_replay_audit_bundle,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
P5_PLAN_PATH = REPO_ROOT / "docs" / "dev" / "FlagHunter_P5_Pre_Eval_Plan_v0.1_2026-07-04.md"


def _compact_fixture_artifacts() -> list[dict]:
    return [
        {
            "schemaVersion": "p5.pre_eval.synthetic.recovery_review.v1",
            "id": "p5-fixture-recovery-review",
            "taskId": "task-pre-eval-recovery",
            "status": "review",
            "decision": "manual_review_required",
            "summary": "Synthetic recovery review artifact for pre-eval planning",
            "metadata": {
                "fixture": "synthetic_authorized_local",
                "authorization": "Bearer fixture-token",
                "candidate": "flag{candidate_not_proof}",
            },
        },
        {
            "schemaVersion": "p5.pre_eval.synthetic.crew_bridge.v1",
            "id": "p5-fixture-crew-bridge",
            "taskId": "task-pre-eval-crew",
            "status": "succeeded",
            "decision": "admit_dry",
            "summary": "Synthetic dry crew bridge artifact for read-side replay",
            "metadata": {"fixture": "synthetic_authorized_local"},
        },
    ]


def test_p5_pre_eval_plan_documents_goals_gates_and_non_goals() -> None:
    text = P5_PLAN_PATH.read_text(encoding="utf-8")

    required_sections = [
        "Evaluation Goals",
        "Evaluation Inputs",
        "Fixture Selection",
        "Metric Definitions",
        "Pass/Fail Gates",
        "Manual Review Checklist",
        "Explicit Non-Goals",
        "P5 Implementation Authorization Boundary",
    ]
    for section in required_sections:
        assert f"## {section}" in text

    required_terms = [
        "evidence completeness",
        "trace reproducibility",
        "receipt coverage",
        "proof-boundary compliance",
        "redaction compliance",
        "operator reviewability",
        "replay consistency",
        "explicit user authorization",
    ]
    lowered = text.lower()
    for term in required_terms:
        assert term in lowered


def test_p5_pre_eval_synthetic_bundle_is_compact_redacted_and_deterministic() -> None:
    artifacts = _compact_fixture_artifacts()

    first = build_task_dag_replay_audit_bundle(
        artifacts=artifacts,
        max_events=10,
        max_rows=10,
        max_items=10,
    ).to_dict()
    second = build_task_dag_replay_audit_bundle(
        artifacts=list(reversed(artifacts)),
        max_events=10,
        max_rows=10,
        max_items=10,
    ).to_dict()
    surface = repr(first)

    assert first == second
    assert first["schemaVersion"] == "p4e.task_dag_replay_audit_bundle.v1"
    assert first["summary"]["artifactCount"] == 2
    assert first["summary"]["indexEventCount"] == 2
    assert first["summary"]["readbackRowCount"] == 2
    assert first["summary"]["viewItemCount"] == 2
    assert first["view"]["overview"]["sourcePackageCount"] == 1
    assert "fixture-token" not in surface
    assert "flag{candidate_not_proof}" not in surface
    assert "verification" + "_decision" not in surface
    assert "verified" + "_flags" not in surface
    assert "executeAction" not in surface
    assert "dispatchAction" not in surface
    assert "applyRecovery" not in surface
