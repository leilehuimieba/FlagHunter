from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_dashboard_page_no_longer_bare_calls_get_dashboard() -> None:
    source = _read("web/console/src/pages/dashboard.jsx")

    assert "window.API.getDashboard({ window: windowFilter, runtime: runtimeFilter }).then(data => {" not in source


def test_dashboard_page_no_longer_bare_calls_subscribe_events() -> None:
    source = _read("web/console/src/pages/dashboard.jsx")

    assert "window.API.subscribeEvents(ev => {" not in source


def test_dashboard_page_introduces_live_availability_guard() -> None:
    source = _read("web/console/src/pages/dashboard.jsx")

    assert "dashboardAvailable" in source
    assert "dashboardUnavailableReason" in source
    assert "t('c.unavailable')" in source
