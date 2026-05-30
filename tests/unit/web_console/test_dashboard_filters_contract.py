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
    assert "const getDashboard = window.API?.getDashboard;" in source
    assert "const dashboardAvailable = ['connected', 'degraded'].includes(connection.status)" in source
    assert "getDashboard({ window: windowFilter, runtime: runtimeFilter }).then(data => {" in source
    assert "dashboardUnavailableReason" in source
    assert "value={windowFilter}" in source
    assert "value={runtimeFilter}" in source


def test_dashboard_notes_artifacts_browse_is_live_navigation() -> None:
    source = _read("web/console/src/pages/dashboard.jsx")

    assert "disabled={true} title={t('c.unavailable')}>{t('c.browse')}</button>" not in source
    assert "onClick={() => onNav('knowledge')}" in source


def test_dashboard_notes_artifacts_card_no_longer_depends_on_synthetic_notes_artifacts() -> None:
    source = _read("web/console/src/pages/dashboard.jsx")

    assert "recentNotes: []" not in source
    assert "recentNotes.length === 0 && recentArtifacts.length === 0" not in source
    assert "recentNotes.map(" not in source
    assert "const recentArtifacts = dashboardData.recentArtifacts || [];" in source
    assert "recentArtifacts.length === 0" in source
    assert "recentArtifacts.map(" in source
    assert "alerts.length === 0" not in source
    assert "alerts.map(n => (" not in source


def test_dashboard_recent_tools_rows_link_to_trace_detail() -> None:
    source = _read("web/console/src/pages/dashboard.jsx")

    assert "recentToolCalls.map(c => (" in source
    assert "onClick={() => c.runId && onNav(`traces/${c.runId}`)}" in source
    assert "cursor: c.runId ? 'pointer' : 'default'" in source
