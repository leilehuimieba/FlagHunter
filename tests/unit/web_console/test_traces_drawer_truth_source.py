from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_traces_event_drawer_no_longer_uses_doc_chunk_demo_fallback() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "doc_002" not in source
    assert "chunk_002" not in source
    assert "Detect backend dialect via timing" not in source


def test_traces_event_drawer_no_longer_gates_knowledge_excerpt_on_window_is_live() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "{window.IS_LIVE ? (e.output || e.summary || 'no observed chunk excerpt') :" not in source


def test_traces_event_drawer_no_longer_uses_window_is_live_in_tool_io_fallbacks() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "if (window.IS_LIVE) return t('tr.dr.noOutput');" not in source
