"""The cold local-dense build gate — RAG must never block startup on a CPU encode.

A cold ``index()`` with local embeddings used to synchronously encode the whole
corpus with the local model — a multi-minute CPU job that hung for >25min on a heavy
model (bge-m3) and burned a live target window. The gate makes that inline encode
opt-in (``FLAGHUNTER_RAG_LOCAL_DENSE=true``); by default a cold build leaves dense off
(BM25 index still built; a prebuilt/persisted index still loads) so the run proceeds.
See [[project_flaghunter_blackboard_pivot]].
"""

from __future__ import annotations

from pathlib import Path

from flaghunter.knowledge.rag import RAGEngine


def _seed_knowledge(tmp_path: Path) -> Path:
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "doc.md").write_text(
        "SQL injection login bypass notes; union select; sqlmap.", encoding="utf-8"
    )
    return kb


def test_cold_local_build_skips_inline_encode_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("FLAGHUNTER_RAG_LOCAL_DENSE", raising=False)
    # If the gate were open, this import target would be called and (in prod) load the
    # heavy model. Make it explode so the test fails loudly if the gate leaks.
    def _boom(_texts):
        raise AssertionError("cold local dense build must be skipped by default")

    monkeypatch.setattr(
        "flaghunter.knowledge.embeddings.get_embeddings_local", _boom, raising=False
    )

    engine = RAGEngine(knowledge_path=_seed_knowledge(tmp_path), use_local_embeddings=True)
    engine.index(force=True)

    # Indexed, BM25 built, but no dense vectors → never blocked on a CPU encode.
    assert engine._indexed is True
    assert engine.embeddings is None
    assert engine.get_document_count() >= 1
    # search() degrades to empty (no dense) rather than crashing on None embeddings.
    assert engine.search("sql injection", k=3) == []


def test_opt_in_flag_builds_local_dense_inline(tmp_path, monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_RAG_LOCAL_DENSE", "true")
    calls: list[list[str]] = []

    import numpy as np

    def _fake_local(texts):
        calls.append(list(texts))
        return np.ones((len(texts), 3), dtype=np.float32)

    monkeypatch.setattr(
        "flaghunter.knowledge.embeddings.get_embeddings_local", _fake_local, raising=False
    )

    engine = RAGEngine(knowledge_path=_seed_knowledge(tmp_path), use_local_embeddings=True)
    engine.index(force=True)

    assert calls, "opt-in flag must build dense inline"
    assert engine.embeddings is not None
    assert engine.embeddings.shape[0] == engine.get_document_count()
