from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_api_layer_get_dashboard_supports_query_params() -> None:
    source = _read("web/console/src/api.js")

    assert "async function getDashboard(params)" in source
    assert "const q = params ? '?' + new URLSearchParams(params) : '';" in source
    assert "return apiFetch('/api/dashboard/summary' + q);" in source


def test_dashboard_page_tracks_window_and_runtime_filters_in_live_requests() -> None:
    source = _read("web/console/src/pages/dashboard.jsx")

    assert "const [windowFilter, setWindowFilter] = uD('24h');" in source
    assert "const [runtimeFilter, setRuntimeFilter] = uD('all');" in source
    assert "window.API.getDashboard({ window: windowFilter, runtime: runtimeFilter }).then(data => {" in source
    assert "window.API.getDashboard({ window: windowFilter, runtime: runtimeFilter }).then(data => {" in source
    assert "value={windowFilter}" in source
    assert "value={runtimeFilter}" in source


def test_dashboard_notes_artifacts_browse_is_live_navigation() -> None:
    source = _read("web/console/src/pages/dashboard.jsx")

    assert "disabled={true} title={t('c.unavailable')}>{t('c.browse')}</button>" not in source
    assert "onClick={() => onNav('knowledge')}" in source
