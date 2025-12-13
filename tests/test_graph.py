"""Tests for the Shadow Graph knowledge system."""

import pytest
import networkx as nx
from ghostcrew.knowledge.graph import ShadowGraph, GraphNode, GraphEdge

class TestShadowGraph:
    """Tests for ShadowGraph class."""

    @pytest.fixture
    def graph(self):
        """Create a fresh ShadowGraph for each test."""
        return ShadowGraph()

    def test_initialization(self, graph):
        """Test graph initialization."""
        assert isinstance(graph.graph, nx.DiGraph)
        assert len(graph.graph.nodes) == 0
        assert len(graph._processed_notes) == 0

    def test_extract_host_from_note(self, graph):
        """Test extracting host IP from a note."""
        notes = {
            "scan_result": {
                "content": "Nmap scan for 192.168.1.10 shows open ports.",
                "category": "info"
            }
        }
        graph.update_from_notes(notes)
        
        assert graph.graph.has_node("host:192.168.1.10")
        node = graph.graph.nodes["host:192.168.1.10"]
        assert node["type"] == "host"
        assert node["label"] == "192.168.1.10"

    def test_extract_service_finding(self, graph):
        """Test extracting services from a finding note."""
        notes = {
            "ports_scan": {
                "content": "Found open ports: 80/tcp, 443/tcp on 10.0.0.5",
                "category": "finding"
            }
        }
        graph.update_from_notes(notes)
        
        # Check host exists
        assert graph.graph.has_node("host:10.0.0.5")
        
        # Check services exist
        assert graph.graph.has_node("service:host:10.0.0.5:80")
        assert graph.graph.has_node("service:host:10.0.0.5:443")
        
        # Check edges
        assert graph.graph.has_edge("host:10.0.0.5", "service:host:10.0.0.5:80")
        edge = graph.graph.edges["host:10.0.0.5", "service:host:10.0.0.5:80"]
        assert edge["type"] == "HAS_SERVICE"
        assert edge["protocol"] == "tcp"

    def test_extract_credential(self, graph):
        """Test extracting credentials and linking to host."""
        notes = {
            "ssh_creds": {
                "content": "Found user: admin with password 'password123' for SSH on 192.168.1.20",
                "category": "credential"
            }
        }
        graph.update_from_notes(notes)
        
        cred_id = "cred:ssh_creds"
        host_id = "host:192.168.1.20"
        
        assert graph.graph.has_node(cred_id)
        assert graph.graph.has_node(host_id)
        
        # Check edge
        assert graph.graph.has_edge(cred_id, host_id)
        edge = graph.graph.edges[cred_id, host_id]
        assert edge["type"] == "AUTH_ACCESS"
        assert edge["protocol"] == "ssh"

    def test_legacy_note_format(self, graph):
        """Test handling legacy string-only notes."""
        notes = {
            "legacy_note": "Just a simple note about 10.10.10.10"
        }
        graph.update_from_notes(notes)
        
        assert graph.graph.has_node("host:10.10.10.10")

    def test_idempotency(self, graph):
        """Test that processing the same note twice doesn't duplicate or error."""
        notes = {
            "scan": {
                "content": "Host 192.168.1.1 is up.",
                "category": "info"
            }
        }
        
        # First pass
        graph.update_from_notes(notes)
        assert len(graph.graph.nodes) == 1
        
        # Second pass
        graph.update_from_notes(notes)
        assert len(graph.graph.nodes) == 1
        
        # Modify note (simulate update - though currently graph only processes new keys, 
        # in a real scenario we might want to handle updates, but for now we test it ignores processed keys)
        notes["scan"]["content"] = "Host 192.168.1.1 is down."
        graph.update_from_notes(notes)
        # Should still be based on first pass if we strictly check processed keys
        # The current implementation uses a set of processed keys, so it won't re-process.
        assert len(graph.graph.nodes) == 1

    def test_multiple_ips_in_one_note(self, graph):
        """Test a single note referencing multiple hosts."""
        notes = {
            "subnet_scan": {
                "content": "Scanning 192.168.1.1, 192.168.1.2, and 192.168.1.3",
                "category": "info"
            }
        }
        graph.update_from_notes(notes)
        
        assert graph.graph.has_node("host:192.168.1.1")
        assert graph.graph.has_node("host:192.168.1.2")
        assert graph.graph.has_node("host:192.168.1.3")
