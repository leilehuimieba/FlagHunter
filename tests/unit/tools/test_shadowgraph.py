"""Tests for the shadowgraph tool."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from flaghunter.tools.shadowgraph import shadowgraph


class TestShadowgraph:
    @patch("flaghunter.tools.shadowgraph.get_all_notes_sync")
    def test_no_notes(self, mock_get_notes):
        mock_get_notes.return_value = {}
        result = asyncio.run(shadowgraph({"action": "insights"}, None))
        assert "No notes found in session" in result

    @patch("flaghunter.tools.shadowgraph.get_all_notes_sync")
    @patch("flaghunter.tools.shadowgraph.ShadowGraph")
    def test_insights(self, mock_graph_cls, mock_get_notes):
        mock_get_notes.return_value = {"note1": {"host": "192.168.1.1", "service": "ssh"}}
        mock_graph = MagicMock()
        mock_graph.get_strategic_insights.return_value = [
            "Unused credential: admin@192.168.1.1",
            "High-value target: 192.168.1.1:22",
        ]
        mock_graph_cls.return_value = mock_graph

        result = asyncio.run(shadowgraph({"action": "insights"}, None))
        assert "ShadowGraph Strategic Insights" in result
        assert "Unused credential" in result
        assert "High-value target" in result
        mock_graph.update_from_notes.assert_called_once()

    @patch("flaghunter.tools.shadowgraph.get_all_notes_sync")
    @patch("flaghunter.tools.shadowgraph.ShadowGraph")
    def test_insights_empty(self, mock_graph_cls, mock_get_notes):
        mock_get_notes.return_value = {"note1": {"host": "192.168.1.1"}}
        mock_graph = MagicMock()
        mock_graph.get_strategic_insights.return_value = []
        mock_graph_cls.return_value = mock_graph

        result = asyncio.run(shadowgraph({"action": "insights"}, None))
        assert "No strategic insights available" in result

    @patch("flaghunter.tools.shadowgraph.get_all_notes_sync")
    @patch("flaghunter.tools.shadowgraph.ShadowGraph")
    def test_mermaid(self, mock_graph_cls, mock_get_notes):
        mock_get_notes.return_value = {"note1": {"host": "192.168.1.1"}}
        mock_graph = MagicMock()
        mock_graph.to_mermaid.return_value = "graph TD\n  A[192.168.1.1] --> B[ssh]"
        mock_graph_cls.return_value = mock_graph

        result = asyncio.run(shadowgraph({"action": "mermaid"}, None))
        assert "ShadowGraph Mermaid Diagram" in result
        assert "graph TD" in result
        assert "mermaid.live" in result

    @patch("flaghunter.tools.shadowgraph.get_all_notes_sync")
    @patch("flaghunter.tools.shadowgraph.ShadowGraph")
    def test_mermaid_empty(self, mock_graph_cls, mock_get_notes):
        mock_get_notes.return_value = {"note1": {"host": "192.168.1.1"}}
        mock_graph = MagicMock()
        mock_graph.to_mermaid.return_value = "graph TD"
        mock_graph_cls.return_value = mock_graph

        result = asyncio.run(shadowgraph({"action": "mermaid"}, None))
        assert "Graph is empty" in result

    @patch("flaghunter.tools.shadowgraph.get_all_notes_sync")
    @patch("flaghunter.tools.shadowgraph.ShadowGraph")
    def test_paths(self, mock_graph_cls, mock_get_notes):
        mock_get_notes.return_value = {"note1": {"credential": "admin:pass", "host": "192.168.1.1"}}
        mock_graph = MagicMock()
        mock_graph._find_attack_paths.return_value = [
            ["credential_admin", "host_192.168.1.1", "service_ssh"],
        ]
        mock_graph_cls.return_value = mock_graph

        result = asyncio.run(shadowgraph({"action": "paths"}, None))
        assert "ShadowGraph Multi-Hop Attack Paths" in result
        assert "credential_admin" in result
        assert "host_192.168.1.1" in result

    @patch("flaghunter.tools.shadowgraph.get_all_notes_sync")
    @patch("flaghunter.tools.shadowgraph.ShadowGraph")
    def test_paths_empty(self, mock_graph_cls, mock_get_notes):
        mock_get_notes.return_value = {"note1": {"host": "192.168.1.1"}}
        mock_graph = MagicMock()
        mock_graph._find_attack_paths.return_value = []
        mock_graph_cls.return_value = mock_graph

        result = asyncio.run(shadowgraph({"action": "paths"}, None))
        assert "No multi-hop attack paths found" in result

    @patch("flaghunter.tools.shadowgraph.get_all_notes_sync")
    @patch("flaghunter.tools.shadowgraph.ShadowGraph")
    def test_stats(self, mock_graph_cls, mock_get_notes):
        mock_get_notes.return_value = {"note1": {"host": "192.168.1.1"}}
        mock_graph = MagicMock()
        mock_graph.graph.number_of_nodes.return_value = 5
        mock_graph.graph.number_of_edges.return_value = 3
        mock_graph_cls.return_value = mock_graph

        # nx is imported inside the function; patch the already-loaded networkx module
        with patch("networkx.weakly_connected_components") as mock_wcc:
            mock_wcc.return_value = [{"a", "b"}, {"c"}]
            result = asyncio.run(shadowgraph({"action": "stats"}, None))

        assert "ShadowGraph Statistics" in result
        assert "Nodes: 5" in result
        assert "Edges: 3" in result
        assert "Connected Components: 2" in result

    @patch("flaghunter.tools.shadowgraph.get_all_notes_sync")
    def test_unknown_action(self, mock_get_notes):
        mock_get_notes.return_value = {"note1": {"host": "192.168.1.1"}}
        result = asyncio.run(shadowgraph({"action": "unknown"}, None))
        assert "Unknown action" in result
        assert "insights, mermaid, paths, stats" in result

    @patch("flaghunter.tools.shadowgraph.get_all_notes_sync")
    def test_default_action_is_insights(self, mock_get_notes):
        mock_get_notes.return_value = {"note1": {"host": "192.168.1.1"}}
        with patch("flaghunter.tools.shadowgraph.ShadowGraph") as mock_graph_cls:
            mock_graph = MagicMock()
            mock_graph.get_strategic_insights.return_value = ["test insight"]
            mock_graph_cls.return_value = mock_graph

            result = asyncio.run(shadowgraph({}, None))
            assert "ShadowGraph Strategic Insights" in result

    @patch("flaghunter.tools.shadowgraph.get_all_notes_sync")
    def test_notes_exception(self, mock_get_notes):
        mock_get_notes.side_effect = RuntimeError("notes db locked")
        result = asyncio.run(shadowgraph({"action": "insights"}, None))
        assert "ShadowGraph build failed" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
