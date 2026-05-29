from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_logs_page_no_longer_bare_calls_get_logs() -> None:
    source = _read("web/console/src/pages/logs.jsx")

    assert "window.API.getLogs().then(data => {" not in source


def test_logs_page_no_longer_bare_calls_subscribe_events() -> None:
    source = _read("web/console/src/pages/logs.jsx")

    assert "window.API.subscribeEvents(ev => {" not in source


def test_logs_page_introduces_live_availability_guard() -> None:
    source = _read("web/console/src/pages/logs.jsx")

    assert "logsAvailable" in source
    assert "logsUnavailableReason" in source
    assert "t('c.unavailable')" in source
