from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_task_detail_reads_harness_truth_from_session_context() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "task.sessionContext" in source
    assert "sessionContext?.latestCheckpoint" in source
    assert "sessionContext?.recentEvents" in source
    assert "sessionContext?.artifacts" in source


def test_task_detail_renders_checkpoint_outcome_tool_and_artifact_cards() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "Latest checkpoint" in source
    assert "Run outcomes" in source
    assert "Tool audit" in source
    assert "Harness artifacts" in source


def test_task_detail_introduces_harness_truth_card_helpers() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "function normalizeHarnessToolEvents(" in source
    assert "function normalizeHarnessOutcomeEvents(" in source
    assert "function HarnessCheckpointCard(" in source
    assert "function HarnessArtifactsCard(" in source
