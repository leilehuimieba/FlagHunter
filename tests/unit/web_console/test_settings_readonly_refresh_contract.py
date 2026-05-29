from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_settings_readonly_refresh_no_longer_bare_calls_get_dashboard() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "window.API.getDashboard()" not in source


def test_settings_readonly_refresh_no_longer_bare_calls_get_knowledge() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "window.API.getKnowledge()" not in source


def test_settings_readonly_refresh_introduces_live_read_guard() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "readonlyRefreshAvailable" in source
    assert "readonlyRefreshUnavailableReason" in source
    assert "t('c.notConnected')" in source
    assert "t('c.notWired')" in source
