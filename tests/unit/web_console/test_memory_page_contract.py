from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_memory_page_no_longer_bare_calls_live_read_apis() -> None:
    source = _read("web/console/src/pages/memory.jsx")

    assert "window.API.getMemory({ status: filter === 'all' ? null : filter, sort_by: sortBy })" not in source
    assert "window.API.getMemoryStats()" not in source


def test_memory_page_no_longer_bare_calls_live_mutation_apis() -> None:
    source = _read("web/console/src/pages/memory.jsx")

    assert "window.API.muteMemoryEntry(id)" not in source
    assert "window.API.activateMemoryEntry(id)" not in source
    assert "window.API.deleteMemoryEntry(id)" not in source


def test_memory_page_introduces_honest_unavailable_copy_for_live_read_path() -> None:
    source = _read("web/console/src/pages/memory.jsx")

    assert "t('c.unavailable')" in source
