"""Tests for RAG indexing of session markdown files."""

from __future__ import annotations

import numpy as np

from pentestagent.knowledge.rag import RAGEngine


def test_rag_index_includes_sibling_sessions_directory(tmp_path, monkeypatch):
    knowledge_base = tmp_path / "knowledge"
    sources_dir = knowledge_base / "sources"
    sessions_dir = knowledge_base / "sessions"
    sources_dir.mkdir(parents=True)
    sessions_dir.mkdir(parents=True)

    (sources_dir / "baseline.md").write_text("# Baseline\n\nGeneral methodology", encoding="utf-8")
    (sessions_dir / "20260522_010101_127.0.0.1.md").write_text(
        "# Session: 127.0.0.1\n\n## http_ports (finding)\nFound port 8080 open",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "pentestagent.knowledge.rag.get_embeddings",
        lambda texts, model=None: np.ones((len(texts), 4)),
    )

    engine = RAGEngine(knowledge_path=sources_dir, use_local_embeddings=False)
    engine.index(force=True)

    assert len(engine.documents) >= 2
    assert any("sessions" in doc.source for doc in engine.documents)
    assert any("Found port 8080 open" in doc.content for doc in engine.documents)
