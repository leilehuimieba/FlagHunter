"""
Shadow Graph implementation for GhostCrew.

This module provides a lightweight knowledge graph that is built automatically
from agent notes. It is used by the Orchestrator to compute strategic insights
(e.g., "we have creds for X but haven't scanned it") without burdening the
agents with graph management.

Architecture:
    Notes (Source of Truth) -> Shadow Graph (Derived View) -> Insights (Strategic Hints)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """A node in the shadow graph."""

    id: str
    type: str  # host, service, credential, finding, artifact
    label: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.id)


@dataclass
class GraphEdge:
    """An edge in the shadow graph."""

    source: str
    target: str
    type: str  # CONNECTS_TO, HAS_SERVICE, AUTH_ACCESS, RELATED_TO
    metadata: Dict[str, Any] = field(default_factory=dict)


class ShadowGraph:
    """
    A NetworkX-backed knowledge graph that derives its state from notes.
    """

    def __init__(self):
        self.graph = nx.DiGraph()
        self._processed_notes: Set[str] = set()

        # Regex patterns for entity extraction
        self._ip_pattern = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        self._port_pattern = re.compile(r"(\d{1,5})/(tcp|udp)")
        self._user_pattern = re.compile(r"user[:\s]+([a-zA-Z0-9_.-]+)", re.IGNORECASE)

    def update_from_notes(self, notes: Dict[str, Dict[str, Any]]) -> None:
        """
        Update the graph based on new notes.

        This method is idempotent and incremental. It only processes notes
        that haven't been seen before (based on key).
        """
        for key, note_data in notes.items():
            if key in self._processed_notes:
                continue

            # Handle legacy format
            if isinstance(note_data, str):
                content = note_data
                category = "info"
            else:
                content = note_data.get("content", "")
                category = note_data.get("category", "info")

            self._process_note(key, content, category)
            self._processed_notes.add(key)

    def _process_note(self, key: str, content: str, category: str) -> None:
        """Extract entities and relationships from a single note."""

        # 1. Extract IPs (Hosts)
        ips = self._ip_pattern.findall(content)
        hosts = []
        for ip in ips:
            node_id = f"host:{ip}"
            self._add_node(node_id, "host", ip)
            hosts.append(node_id)

        # 2. Handle specific categories
        if category == "credential":
            self._process_credential(key, content, hosts)
        elif category == "finding":
            self._process_finding(key, content, hosts)
        elif category == "vulnerability":
            self._process_vulnerability(key, content, hosts)

        # 3. Link note to hosts (provenance)
        # We don't add the note itself as a node usually, but we could.
        # For now, we just use the note to build Host-to-Host or Host-to-Service links.

    def _add_node(self, node_id: str, node_type: str, label: str, **kwargs) -> None:
        """Add a node if it doesn't exist."""
        if not self.graph.has_node(node_id):
            self.graph.add_node(node_id, type=node_type, label=label, **kwargs)

    def _add_edge(self, source: str, target: str, edge_type: str, **kwargs) -> None:
        """Add an edge."""
        if self.graph.has_node(source) and self.graph.has_node(target):
            self.graph.add_edge(source, target, type=edge_type, **kwargs)

    def _process_credential(
        self, key: str, content: str, related_hosts: List[str]
    ) -> None:
        """Process a credential note."""
        # Extract username
        user_match = self._user_pattern.search(content)
        username = user_match.group(1) if user_match else "unknown"

        cred_id = f"cred:{key}"
        self._add_node(cred_id, "credential", f"Creds ({username})")

        # Link cred to hosts it belongs to (or works on)
        for host_id in related_hosts:
            # If the note says "ssh", assume SSH access
            protocol = "ssh" if "ssh" in content.lower() else "unknown"
            self._add_edge(cred_id, host_id, "AUTH_ACCESS", protocol=protocol)

    def _process_finding(
        self, key: str, content: str, related_hosts: List[str]
    ) -> None:
        """Process a finding note (e.g., open ports)."""
        # Extract ports
        ports = self._port_pattern.findall(content)
        for port, proto in ports:
            for host_id in related_hosts:
                service_id = f"service:{host_id}:{port}"
                self._add_node(service_id, "service", f"{port}/{proto}")
                self._add_edge(host_id, service_id, "HAS_SERVICE", protocol=proto)

    def _process_vulnerability(
        self, key: str, content: str, related_hosts: List[str]
    ) -> None:
        """Process a vulnerability note."""
        vuln_id = f"vuln:{key}"
        # Try to extract CVE
        cve_match = re.search(r"CVE-\d{4}-\d{4,7}", content, re.IGNORECASE)
        label = cve_match.group(0) if cve_match else "Vulnerability"

        self._add_node(vuln_id, "vulnerability", label)

        for host_id in related_hosts:
            self._add_edge(host_id, vuln_id, "AFFECTED_BY")

    def get_strategic_insights(self) -> List[str]:
        """
        Analyze the graph and return natural language insights for the Orchestrator.
        """
        insights = []

        # Insight 1: Unused Credentials
        # Find credentials that have AUTH_ACCESS to a host, but we haven't "explored" that host fully?
        # Or simply list valid access paths.
        for node, data in self.graph.nodes(data=True):
            if data.get("type") == "credential":
                # Find what it connects to
                targets = [v for u, v in self.graph.out_edges(node)]
                if targets:
                    target_labels = [
                        self.graph.nodes[t].get("label", t) for t in targets
                    ]
                    insights.append(
                        f"We have credentials that provide access to: {', '.join(target_labels)}"
                    )

        # Insight 2: High Value Targets (Hosts with many open ports/vulns)
        for node, data in self.graph.nodes(data=True):
            if data.get("type") == "host":
                # Count services
                services = [
                    v
                    for u, v in self.graph.out_edges(node)
                    if self.graph.nodes[v].get("type") == "service"
                ]
                vulns = [
                    v
                    for u, v in self.graph.out_edges(node)
                    if self.graph.nodes[v].get("type") == "vulnerability"
                ]

                if len(services) > 0 or len(vulns) > 0:
                    insights.append(
                        f"Host {data['label']} has {len(services)} services and {len(vulns)} known vulnerabilities."
                    )

        # Insight 3: Potential Pivots (Host A -> Cred -> Host B)
        # This is harder without explicit "source" of creds, but we can infer.

        return insights

    def export_summary(self) -> str:
        """Export a text summary of the graph state."""
        stats = {
            "hosts": len(
                [n for n, d in self.graph.nodes(data=True) if d["type"] == "host"]
            ),
            "creds": len(
                [n for n, d in self.graph.nodes(data=True) if d["type"] == "credential"]
            ),
            "vulns": len(
                [
                    n
                    for n, d in self.graph.nodes(data=True)
                    if d["type"] == "vulnerability"
                ]
            ),
        }
        return f"Graph State: {stats['hosts']} Hosts, {stats['creds']} Credentials, {stats['vulns']} Vulnerabilities"
