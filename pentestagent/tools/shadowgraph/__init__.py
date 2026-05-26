"""ShadowGraph — query the knowledge graph derived from session notes for strategic insights and attack paths."""

import logging

from ...knowledge.graph import ShadowGraph
from ...runtime.runtime import Runtime
from ...tools.notes import get_all_notes_sync
from ...tools.registry import ToolSchema, register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="shadowgraph",
    description="Query the ShadowGraph knowledge graph built from session notes. Provides strategic insights (unused credentials, high-value targets, attack paths) and Mermaid diagram export. Use this to understand the big picture of discovered infrastructure and plan next moves.",
    schema=ToolSchema(
        type="object",
        properties={
            "action": {
                "type": "string",
                "description": "Action to perform: insights (strategic analysis), mermaid (generate diagram), paths (multi-hop attack paths), stats (node counts)",
                "enum": ["insights", "mermaid", "paths", "stats"],
                "default": "insights",
            },
        },
        required=[],
    ),
    category="knowledge",
)
async def shadowgraph(arguments: dict, runtime: Runtime) -> str:
    action = arguments.get("action", "insights")

    try:
        notes = get_all_notes_sync()
        if not notes:
            return "ShadowGraph: No notes found in session. Discover hosts, credentials, and vulnerabilities first to build the graph."

        graph = ShadowGraph()
        graph.update_from_notes(notes)
    except Exception as exc:
        logger.warning("shadowgraph build failed: %s", exc, exc_info=True)
        return f"ShadowGraph build failed: {exc}"

    if action == "insights":
        try:
            insights = graph.get_strategic_insights()
        except Exception as exc:
            return f"Failed to generate insights: {exc}"

        if not insights:
            return "ShadowGraph: No strategic insights available yet. The graph may be too sparse (need more notes with target/services/credentials)."

        lines = ["ShadowGraph Strategic Insights", "=" * 40]
        for i, insight in enumerate(insights, 1):
            lines.append(f"\n[{i}] {insight}")
        return "\n".join(lines)

    elif action == "mermaid":
        try:
            mermaid = graph.to_mermaid()
        except Exception as exc:
            return f"Failed to generate Mermaid diagram: {exc}"

        if not mermaid or mermaid == "graph TD":
            return "ShadowGraph: Graph is empty. No nodes to visualize yet."

        return (
            "ShadowGraph Mermaid Diagram\n"
            "=" * 40 + "\n\n"
            "Render this at https://mermaid.live/ or in any Markdown viewer:\n\n"
            "```mermaid\n"
            f"{mermaid}\n"
            "```"
        )

    elif action == "paths":
        try:
            paths = graph._find_attack_paths()
        except Exception as exc:
            return f"Failed to find attack paths: {exc}"

        if not paths:
            return "ShadowGraph: No multi-hop attack paths found. Need at least: credential → host → (another credential or vulnerability)."

        lines = ["ShadowGraph Multi-Hop Attack Paths", "=" * 40]
        for i, path in enumerate(paths[:10], 1):
            path_str = " → ".join(str(node) for node in path)
            lines.append(f"\n[{i}] {path_str}")
        return "\n".join(lines)

    elif action == "stats":
        try:
            import networkx as nx
            node_count = graph.graph.number_of_nodes()
            edge_count = graph.graph.number_of_edges()
            components = list(nx.weakly_connected_components(graph.graph))
        except Exception as exc:
            return f"Failed to compute stats: {exc}"

        lines = [
            "ShadowGraph Statistics",
            "=" * 40,
            f"Nodes: {node_count}",
            f"Edges: {edge_count}",
            f"Connected Components: {len(components)}",
        ]
        for i, comp in enumerate(components[:5], 1):
            lines.append(f"  Component {i}: {len(comp)} nodes")
        return "\n".join(lines)

    return f"Unknown action: {action}. Use: insights, mermaid, paths, stats"
