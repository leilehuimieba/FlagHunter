from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_tasks_list_renders_mode_badge_from_true_task_mode() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "<ModeBadge mode={tk.mode} />" in source


def test_tasks_list_renders_subtype_badge_from_true_task_mode_subtype() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "<SubtypeBadge value={tk.modeSubtype} />" in source


def test_task_detail_header_renders_mode_badge_from_true_detail_mode() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "<ModeBadge mode={detailTask.mode} />" in source


def test_task_detail_header_renders_subtype_badge_from_true_detail_mode_subtype() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "<SubtypeBadge value={detailTask.modeSubtype} />" in source
