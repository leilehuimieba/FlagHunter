from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_api_layer_exposes_retry_task_function() -> None:
    source = _read("web/console/src/api.js")

    assert "async function retryTask(taskId)" in source
    assert "return apiFetch('/api/tasks/' + encodeURIComponent(taskId) + '/retry'" in source
    assert "retryTask," in source


def test_tasks_page_binds_retry_button_to_api_call() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "const retrySupported = !!capabilityMap.retry;" in source
    assert "const retryAvailable = retrySupported" in source
    assert "const retryUnavailableReason = !retrySupported" in source
    assert "const retryResult = await window.API.retryTask(detailTask.id);" in source
    assert "if (retryResult?.id && onNav) onNav(`tasks/${retryResult.id}`);" in source
    assert "{!isActive && <button className=\"btn\" onClick={handleRetry} disabled={!retryAvailable} title={!retryAvailable ? retryUnavailableReason : ''}>↻ {t('c.retry')}</button>}" in source
