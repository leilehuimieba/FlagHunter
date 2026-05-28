from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_settings_page_no_longer_derives_connection_state_from_window_is_live() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "window.API?.getConnectionState" in source
    assert "window.addEventListener('fh:connection'" in source
    assert "Boolean(window.IS_LIVE)" not in source


def test_settings_page_no_longer_inlines_connected_disconnected_fallback_shape() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "status: e.detail?.type === 'connected' ? 'connected' : 'disconnected'" not in source
    assert "isLive: e.detail?.type === 'connected'" not in source
