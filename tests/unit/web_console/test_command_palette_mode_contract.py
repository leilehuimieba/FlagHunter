from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_command_palette_no_longer_bare_calls_get_tasks() -> None:
    source = _read("web/console/src/command_palette.jsx")

    assert "const data = await window.API.getTasks();" not in source


def test_command_palette_introduces_live_task_availability_guard() -> None:
    source = _read("web/console/src/command_palette.jsx")

    assert "const getTasks = window.API?.getTasks;" in source
    assert "const tasksAvailable" in source


def test_command_palette_recent_tasks_render_mode_badges() -> None:
    source = _read("web/console/src/command_palette.jsx")

    assert "<ModeBadge mode={cmd.task.mode} />" in source
    assert "<SubtypeBadge value={cmd.task.modeSubtype} />" in source
