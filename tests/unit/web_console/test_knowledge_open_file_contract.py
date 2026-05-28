from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_api_layer_exposes_open_knowledge_document_function() -> None:
    source = _read("web/console/src/api.js")

    assert "async function openKnowledgeDocument(docKey)" in source
    assert "return apiFetch('/api/knowledge/' + encodeURIComponent(docKey) + '/open');" in source
    assert "openKnowledgeDocument," in source


def test_knowledge_detail_binds_open_file_button_to_live_action() -> None:
    source = _read("web/console/src/pages/knowledge.jsx")

    assert "const openFileAvailable = ['connected', 'degraded'].includes(connection.status)" in source
    assert "&& typeof window.API?.openKnowledgeDocument === 'function';" in source
    assert "const openResult = await window.API.openKnowledgeDocument(resolvedDoc.docKey);" in source
    assert "if (openResult?.openUrl) {" in source
    assert "title={!openFileAvailable ? openFileUnavailableReason : ''}" in source
