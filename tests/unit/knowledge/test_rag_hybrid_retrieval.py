"""Tests for hybrid vector/BM25 retrieval in RAGEngine."""

from __future__ import annotations

import numpy as np

from flaghunter.knowledge.rag import Document, RAGEngine


class FakeBM25Okapi:
    """Tiny BM25 stand-in that scores exact token overlap."""

    def __init__(self, corpus: list[list[str]]):
        self.corpus = corpus

    def get_scores(self, query_tokens: list[str]) -> np.ndarray:
        return np.array(
            [
                sum(1 for token in query_tokens if token in document_tokens)
                for document_tokens in self.corpus
            ],
            dtype=float,
        )


def test_search_rrf_fuses_bm25_exact_token_hit_into_top_k(monkeypatch):
    query = "FLAGHUNTER-RARE-TOKEN 49152"
    exact_token_doc = (
        "Service crash note: rare listener on port 49152 exposes "
        "FLAGHUNTER-RARE-TOKEN via /debug."
    )
    docs = [
        Document("General SQL injection notes for login bypass and cookies.", "a.md"),
        Document("Apache Tomcat manager defaults and deployment notes.", "b.md"),
        Document(exact_token_doc, "rare.md"),
    ]
    vectors = {
        docs[0].content: np.array([0.99, 0.0, 0.0]),
        docs[1].content: np.array([0.98, 0.0, 0.0]),
        docs[2].content: np.array([0.50, 0.0, 0.0]),
        query: np.array([1.0, 0.0, 0.0]),
    }

    def fake_embeddings(texts, model=None):
        return np.array([vectors[text] for text in texts])

    monkeypatch.setattr(
        "flaghunter.knowledge.rag.BM25Okapi", FakeBM25Okapi, raising=False
    )
    monkeypatch.setattr("flaghunter.knowledge.rag.get_embeddings", fake_embeddings)

    engine = RAGEngine(use_local_embeddings=False)
    engine.add_documents(docs)
    engine._indexed = True

    results = engine.search(query, k=2, threshold=0.35)

    assert exact_token_doc in results
