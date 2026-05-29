from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_tasks_list_no_longer_renders_legacy_detected_type_badge() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "<TypeBadge type={tk.detectedType} />" not in source


def test_task_detail_no_longer_renders_legacy_detected_type_badge() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "<TypeBadge type={detailTask.detectedType} />" not in source
