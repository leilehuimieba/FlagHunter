from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_memory_graph_no_longer_bare_calls_live_graph_api() -> None:
    source = _read("web/console/src/pages/memory.jsx")

    assert "window.API.getMemoryGraph({ status: filter === 'all' ? null : filter }).then(data => {" not in source


def test_memory_graph_introduces_live_availability_guard() -> None:
    source = _read("web/console/src/pages/memory.jsx")

    assert "graphAvailable" in source
    assert "graphUnavailableReason" in source


def test_memory_graph_uses_honest_unavailable_copy_when_unavailable() -> None:
    source = _read("web/console/src/pages/memory.jsx")

    assert "t('c.unavailable')" in source
