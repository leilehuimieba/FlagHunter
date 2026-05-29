from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_dashboard_recent_tasks_render_mode_badge_from_true_task_mode() -> None:
    source = _read("web/console/src/pages/dashboard.jsx")

    assert "<ModeBadge mode={tk.mode} />" in source


def test_dashboard_recent_tasks_render_subtype_badge_from_true_task_mode_subtype() -> None:
    source = _read("web/console/src/pages/dashboard.jsx")

    assert "<SubtypeBadge value={tk.modeSubtype} />" in source
