"""Tests for the clean architecture migration playbook status ledger."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK_PATH = (
    REPO_ROOT
    / "docs"
    / "dev"
    / "FlagHunter_Clean_Architecture_Migration_Playbook_v0.1_2026-07-04.md"
)


def _playbook_text() -> str:
    return PLAYBOOK_PATH.read_text(encoding="utf-8")


def test_playbook_tracks_completed_phase4_application_services() -> None:
    text = _playbook_text()

    assert "## 7. Current Execution Status" in text
    assert "Phase 4 application service skeletons completed" in text
    for service_name in (
        "BuildChallengeRunSnapshot",
        "RecordTaskReceipt",
        "BuildEvidenceSnapshot",
        "ReviewClaim",
        "RecordToolReceipt",
        "DispatchWorkerTask",
    ):
        assert service_name in text


def test_playbook_records_next_approval_gate_after_phase4_skeletons() -> None:
    text = _playbook_text()

    assert "Next approval gate" in text
    assert "production wiring" in text
    assert "composition root" in text
    assert "CTFTaskDispatcher" in text
    assert "ToolExecutor" in text
    assert "WorkerPool" in text
    assert "MCP production wiring" in text


def test_playbook_records_phase4_verification_baseline() -> None:
    text = _playbook_text()

    assert "tests/unit/test_import_layers.py" in text
    assert "tests/unit/test_application_worker_task_service.py" in text
    assert "application-service-boundary" in text
