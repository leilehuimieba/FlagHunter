from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_traces_page_tracks_window_filter_in_live_requests() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "const [windowFilter, setWindowFilter] = uS('24h');" in source
    assert "const getTraces = window.API?.getTraces;" in source
    assert "getTraces({ window: windowFilter, target: targetFilter }).then(data => {" in source
    assert "value={windowFilter}" in source


def test_traces_page_tracks_target_filter_in_live_requests() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "const [targetFilter, setTargetFilter] = uS('all');" in source
    assert "const [targetOptions, setTargetOptions] = uS(['all']);" in source
    assert "getTraces({ window: windowFilter, target: targetFilter }).then(data => {" in source
    assert "setApiTraces(Array.isArray(data?.items) ? data.items : []);" in source
    assert "setTargetOptions(Array.isArray(data?.filters?.targets) ? data.filters.targets : ['all']);" in source
    assert "value={targetFilter}" in source
    assert "disabled={true} title={t('c.notWired')}" not in source
