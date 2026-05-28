from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_traces_page_mainline_no_longer_depends_on_mock_traces() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "MOCK.TRACES" not in source
    assert "/* global React, MOCK" not in source


def test_knowledge_page_mainline_no_longer_depends_on_mock_docs_or_chunks() -> None:
    source = _read("web/console/src/pages/knowledge.jsx")

    assert "MOCK.KNOWLEDGE" not in source
    assert "MOCK.CHUNKS_002" not in source
    assert "/* global React, MOCK" not in source


def test_trace_and_knowledge_detail_reset_stale_state_on_route_change() -> None:
    traces_source = _read("web/console/src/pages/traces.jsx")
    knowledge_source = _read("web/console/src/pages/knowledge.jsx")

    assert "uE(() => {\n    let done = false;\n    setRun(null);" in traces_source
    assert "uKE(() => {\n    let done = false;\n    setDoc(null);" in knowledge_source


def test_trace_detail_duration_fallback_is_status_aware() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "resolvedRun.status === 'running' ? t('tr.stillRunning') : '—'" in source
