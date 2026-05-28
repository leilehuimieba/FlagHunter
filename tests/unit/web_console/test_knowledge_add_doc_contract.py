from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_api_layer_exposes_upload_knowledge_document_function() -> None:
    source = _read("web/console/src/api.js")

    assert "async function uploadKnowledgeDocument(file, onProgress)" in source
    assert "xhr.open('POST', '/api/knowledge/documents');" in source
    assert "fd.append('file', file);" in source
    assert "uploadKnowledgeDocument," in source


def test_knowledge_page_binds_add_doc_button_to_live_upload_action() -> None:
    source = _read("web/console/src/pages/knowledge.jsx")

    assert "const addDocAvailable = ['connected', 'degraded'].includes(connection.status)" in source
    assert "&& typeof window.API?.uploadKnowledgeDocument === 'function';" in source
    assert "const uploadResult = await window.API.uploadKnowledgeDocument(file);" in source
    assert "if (uploadResult?.ok) {" in source
    assert "title={!addDocAvailable ? addDocUnavailableReason : ''}" in source
