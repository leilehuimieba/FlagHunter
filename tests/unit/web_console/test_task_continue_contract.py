from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_api_layer_exposes_continue_task_function() -> None:
    source = _read("web/console/src/api.js")

    assert "async function continueTask(taskId)" in source
    assert "return apiFetch('/api/tasks/' + encodeURIComponent(taskId) + '/continue'" in source
    assert "continueTask," in source


def test_tasks_page_binds_continue_send_path_to_api_call() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "const continueAvailable = continueSupported" in source
    assert "&& typeof window.API?.continueTask === 'function';" in source
    assert "typeof window.API?.continueTask !== 'function'" in source
    assert "const continueResult = await window.API.continueTask(detailTask.id);" in source
    assert "if (!continueResult?.ok) {" in source
    assert "appendSystemMessage('continue request failed');" in source
