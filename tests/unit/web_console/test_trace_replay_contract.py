from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_api_layer_exposes_replay_trace_function() -> None:
    source = _read("web/console/src/api.js")

    assert "async function replayTrace(runId)" in source
    assert "return apiFetch('/api/traces/' + encodeURIComponent(runId) + '/replay'" in source
    assert "replayTrace," in source


def test_traces_page_binds_replay_button_to_api_call() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "const replayAvailable = typeof window.API?.replayTrace === 'function';" in source
    assert "const replayResult = await window.API.replayTrace(resolvedRun.id);" in source
    assert "if (replayResult?.id && onNav) onNav(`tasks/${replayResult.id}`);" in source
    assert "<button className=\"btn\" disabled={!replayAvailable} title={!replayAvailable ? t('tr.replayUnavailable') : ''} onClick={handleReplay}>⟲ {t('c.replay')}</button>" in source
