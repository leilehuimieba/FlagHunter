from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_traces_page_no_longer_bare_calls_get_traces() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "window.API.getTraces({ window: windowFilter, target: targetFilter }).then(data => {" not in source


def test_traces_page_no_longer_bare_calls_subscribe_events() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "return window.API.subscribeEvents(ev => {" not in source


def test_traces_page_no_longer_bare_calls_get_trace_detail() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "window.API.getTrace(runId).then(data => {" not in source


def test_traces_page_introduces_live_availability_guard() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "tracesAvailable" in source
    assert "tracesUnavailableReason" in source
    assert "t('c.unavailable')" in source


def test_trace_detail_renders_tool_audit_panel_from_truthful_tool_events() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "Tool audit" in source
    assert "resolvedRun.toolEvents.map" in source


def test_trace_detail_links_tool_audit_rows_to_event_drawer() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "setDrawer(event)" in source
    assert "tool-audit-list" in source
