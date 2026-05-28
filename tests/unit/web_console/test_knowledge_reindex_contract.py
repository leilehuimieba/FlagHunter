from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_api_layer_exposes_reindex_knowledge_function() -> None:
    source = _read("web/console/src/api.js")

    assert "async function reindexKnowledge()" in source
    assert "return apiFetch('/api/knowledge/reindex', { method: 'POST' });" in source
    assert "reindexKnowledge," in source


def test_settings_page_binds_knowledge_rebuild_button_to_live_action() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "const rebuildAvailable = ['connected', 'degraded'].includes(connection?.status)" in source
    assert "&& typeof window.API?.reindexKnowledge === 'function';" in source
    assert "const rebuildResult = await window.API.reindexKnowledge();" in source
    assert "title={!rebuildAvailable ? rebuildUnavailableReason : ''}" in source


def test_knowledge_page_binds_reindex_buttons_to_live_action() -> None:
    source = _read("web/console/src/pages/knowledge.jsx")

    assert "const reindexAvailable = ['connected', 'degraded'].includes(connection.status)" in source
    assert "&& typeof window.API?.reindexKnowledge === 'function';" in source
    assert "const reindexResult = await window.API.reindexKnowledge();" in source
    assert "title={!reindexAvailable ? reindexUnavailableReason : ''}" in source
