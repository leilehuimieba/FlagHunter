"""Tests for the knowledge_search tool."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from pentestagent.tools import knowledge_search as ks_module
from pentestagent.tools.knowledge_search import knowledge_search


class TestKnowledgeSearch:
    def setup_method(self):
        # Clear module-level RAG engine cache between tests
        ks_module._rag_engine = None

    def teardown_method(self):
        ks_module._rag_engine = None
    def test_empty_query(self):
        result = asyncio.run(knowledge_search({"query": ""}, None))
        assert "Error: query is required" in result

    def test_missing_query_key(self):
        result = asyncio.run(knowledge_search({}, None))
        assert "Error: query is required" in result

    @patch("pentestagent.tools.knowledge_search.RAGEngine")
    def test_successful_search(self, mock_engine_cls):
        mock_engine = MagicMock()
        mock_engine.document_count = 42
        mock_engine.search.return_value = [
            "SQL injection is a code injection technique...",
            "Use parameterized queries to prevent SQLi...",
        ]
        mock_engine_cls.return_value = mock_engine

        result = asyncio.run(knowledge_search({"query": "SQL injection"}, None))
        assert "Knowledge Search Results for: 'SQL injection'" in result
        assert "Indexed Documents: 42" in result
        assert "SQL injection is a code injection technique" in result
        assert "Use parameterized queries" in result
        mock_engine.index.assert_called_once()
        mock_engine.search.assert_called_once_with("SQL injection", k=5, threshold=0.35, max_tokens=1500)

    @patch("pentestagent.tools.knowledge_search.RAGEngine")
    def test_custom_params(self, mock_engine_cls):
        mock_engine = MagicMock()
        mock_engine.document_count = 10
        mock_engine.search.return_value = ["Result 1"]
        mock_engine_cls.return_value = mock_engine

        result = asyncio.run(knowledge_search({
            "query": "XSS",
            "k": 3,
            "threshold": 0.5,
            "max_tokens": 800,
        }, None))
        mock_engine.search.assert_called_once_with("XSS", k=3, threshold=0.5, max_tokens=800)

    @patch("pentestagent.tools.knowledge_search.RAGEngine")
    def test_no_results(self, mock_engine_cls):
        mock_engine = MagicMock()
        mock_engine.document_count = 100
        mock_engine.search.return_value = []
        mock_engine_cls.return_value = mock_engine

        result = asyncio.run(knowledge_search({"query": "obscure topic"}, None))
        assert "No relevant knowledge found" in result
        assert "obscure topic" in result
        assert "Tips:" in result

    @patch("pentestagent.tools.knowledge_search.RAGEngine")
    def test_engine_exception(self, mock_engine_cls):
        mock_engine_cls.side_effect = ImportError("No module named 'sentence_transformers'")

        result = asyncio.run(knowledge_search({"query": "test"}, None))
        assert "Knowledge search failed" in result
        assert "sentence-transformers" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
