from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_tasks_page_no_longer_inlines_observed_empty_state_strings() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "no observed live events" not in source
    assert "no observed knowledge hits" not in source
    assert "knowledge tool usage was observed, but no snapshot-backed query / chunk detail is available" not in source
    assert "no observed notes" not in source
    assert "no observed plan snapshot" not in source


def test_traces_page_no_longer_inlines_trace_empty_state_strings() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "no observed trace timeline" not in source
    assert "waiting for first trace event" not in source
    assert "no observed trace graph events" not in source
    assert "no observed tool I/O snapshot for this event" not in source
    assert "no observed chunk excerpt" not in source


def test_i18n_defines_tasks_and_traces_empty_state_keys() -> None:
    source = _read("web/console/src/i18n.js")

    for key in [
        "td.obs.empty",
        "td.knowledge.empty",
        "td.knowledge.observedOnly",
        "td.notes.empty",
        "td.plan.empty",
        "tr.empty.timeline",
        "tr.empty.awaitingFirstEvent",
        "tr.empty.graph",
        "tr.empty.toolIo",
        "tr.empty.chunkExcerpt",
    ]:
        assert key in source
