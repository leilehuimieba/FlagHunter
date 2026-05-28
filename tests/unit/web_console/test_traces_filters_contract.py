from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_traces_page_tracks_window_filter_in_live_requests() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "const [windowFilter, setWindowFilter] = uS('24h');" in source
    assert "window.API.getTraces({ window: windowFilter }).then(data => {" in source
    assert "window.API.getTraces({ window: windowFilter }).then(data => {" in source
    assert "value={windowFilter}" in source


def test_traces_page_target_filter_button_remains_honestly_disabled() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "title={t('c.notWired')}" in source
