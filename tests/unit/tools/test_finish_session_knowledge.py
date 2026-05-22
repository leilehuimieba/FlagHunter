"""Tests for finish tool session knowledge persistence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import pentestagent.tools.notes as notes_module
from pentestagent.tools.finish import PlanStep, TaskPlan, finish
from pentestagent.tools.notes import set_notes_file


@pytest.fixture(autouse=True)
def isolated_notes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    notes_file = tmp_path / "notes.json"
    set_notes_file(notes_file)
    notes_module._notes.clear()
    notes_module._loaded_notes_file = None
    yield
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


async def _create_note(**kwargs) -> str:
    args = {"action": "create", **kwargs}
    return await notes_module.notes(args, runtime=None)


@dataclass
class _Runtime:
    plan: TaskPlan
    target: str = "127.0.0.1"


@pytest.mark.asyncio
async def test_finish_complete_writes_session_markdown_for_worthy_notes():
    await _create_note(
        key="ports_127001",
        value="Found open ports 22 and 80",
        category="finding",
        confidence="high",
        target="127.0.0.1",
        port="22",
    )
    await _create_note(
        key="noise_note",
        value="Noisy info that should not be exported",
        category="info",
        confidence="low",
    )

    runtime = _Runtime(plan=TaskPlan(steps=[PlanStep(id=1, description="Scan target")]))

    result = await finish({"action": "complete", "step_id": 1, "result": "done"}, runtime)

    assert "All steps complete" in result

    sessions_dir = Path("pentestagent/knowledge/sessions")
    md_files = list(sessions_dir.glob("*_127.0.0.1.md"))
    assert len(md_files) == 1

    content = md_files[0].read_text(encoding="utf-8")
    assert "ports_127001 (finding)" in content
    assert "noise_note" not in content


@pytest.mark.asyncio
async def test_finish_incomplete_step_does_not_write_session_markdown():
    await _create_note(
        key="ports_127001",
        value="Found open ports 22 and 80",
        category="finding",
        confidence="high",
        target="127.0.0.1",
        port="22",
    )

    runtime = _Runtime(
        plan=TaskPlan(
            steps=[
                PlanStep(id=1, description="Scan target"),
                PlanStep(id=2, description="Enumerate web"),
            ]
        )
    )

    result = await finish({"action": "complete", "step_id": 1, "result": "done"}, runtime)

    assert "Next: Step 2" in result
    sessions_dir = Path("pentestagent/knowledge/sessions")
    assert list(sessions_dir.glob("*.md")) == []
