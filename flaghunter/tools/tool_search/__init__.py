"""Tool search — lets the agent find tools by capability description.

Phase 2: When the agent doesn't know which tool provides a specific
capability (e.g. "SSRF detection" or "subdomain enumeration"), it can
call this tool to discover matching tools from the registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..registry import ToolSchema, get_all_tools, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


@register_tool(
    name="tool_search",
    description=(
        "Search available tools by capability or attack type description. "
        "Use this when you need a specific capability (e.g., 'SSRF scanning', "
        "'subdomain enumeration', 'port scanning') but don't know which tool "
        "provides it. Returns the top matching tools with their descriptions."
    ),
    schema=ToolSchema(
        properties={
            "query": {
                "type": "string",
                "description": (
                    "What capability or attack type to search for. "
                    "Examples: 'SSRF detection', 'port scan', 'subdomain enumeration', "
                    "'SQL injection', 'directory brute force'"
                ),
            },
        },
        required=["query"],
    ),
    category="meta",
)
async def tool_search(arguments: dict, runtime: "Runtime") -> str:
    query = str(arguments.get("query", "")).strip().lower()
    if not query:
        return "Error: 'query' is required and must be non-empty"

    all_tools = get_all_tools()
    if not all_tools:
        return "No tools registered."

    scored: list[tuple[int, object]] = []
    tokens = query.split()

    for tool in all_tools:
        if not tool.enabled:
            continue
        name_lower = tool.name.lower()
        desc_lower = tool.description.lower() if tool.description else ""
        cat_lower = tool.category.lower()
        combined = f"{name_lower} {desc_lower} {cat_lower}"

        score = 0
        # exact name match
        if query in name_lower:
            score += 100
        elif name_lower in query:
            score += 60
        # description keyword match
        for token in tokens:
            if token in desc_lower:
                score += 20
            if token in name_lower:
                score += 25
        # category match
        if query in cat_lower:
            score += 15
        # substring fallback
        if score == 0 and any(t in combined for t in tokens):
            score += 5

        if score > 0:
            scored.append((score, tool))

    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[:5]

    if not top:
        # fuzzy: try individual characters for acronym-like searches
        for tool in all_tools:
            if not tool.enabled:
                continue
            name_lower = tool.name.lower()
            if len(query) <= 4 and all(c in name_lower for c in query):
                scored.append((2, tool))
        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[:5]

    if not top:
        return f"No tools matched query '{arguments.get('query', '')}'. Try broader terms (e.g., 'scan' instead of a specific tool name) or check available categories."

    lines = [f"Top {len(top)} tool(s) matching '{arguments.get('query', '')}':"]
    for score, tool in top:
        desc = tool.description or "(no description)"
        desc_short = desc[:120] + "..." if len(desc) > 120 else desc
        lines.append(f"- **{tool.name}** [{tool.category}] (relevance: {score}): {desc_short}")
    return "\n".join(lines)
