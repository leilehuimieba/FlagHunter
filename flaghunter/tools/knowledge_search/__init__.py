"""Knowledge Search — RAG-powered search over the local security knowledge base."""

import logging
from pathlib import Path

from ...knowledge.rag import RAGEngine
from ...runtime.runtime import Runtime
from ...tools.registry import ToolSchema, register_tool

logger = logging.getLogger(__name__)

# Module-level RAGEngine cache to avoid re-indexing on every call
_rag_engine: RAGEngine | None = None


def _get_rag_engine() -> RAGEngine:
    """Get or create the cached RAGEngine instance.

    The engine is created once per process and reused across calls.
    index() is idempotent — it skips if already indexed.
    """
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine(
            knowledge_path=Path("knowledge"),
            use_local_embeddings=True,
        )
    return _rag_engine


@register_tool(
    name="knowledge_search",
    description="Search the local security knowledge base (RAG) for relevant information about vulnerabilities, exploits, CTF techniques, penetration testing methodologies, and platform behaviors. Use this when you need specific technical knowledge rather than relying on LLM pre-training.",
    schema=ToolSchema(
        type="object",
        properties={
            "query": {"type": "string", "description": "Search query (e.g., 'how to exploit SQL injection in MySQL', 'JWT authentication bypass techniques')"},
            "k": {"type": "integer", "description": "Number of top results to return (default: 5)", "default": 5},
            "threshold": {"type": "number", "description": "Similarity threshold 0-1, higher = more strict (default: 0.35)", "default": 0.35},
            "max_tokens": {"type": "integer", "description": "Max total tokens for results (default: 1500)", "default": 1500},
        },
        required=["query"],
    ),
    category="knowledge",
)
async def knowledge_search(arguments: dict, runtime: Runtime) -> str:
    query = arguments.get("query", "").strip()
    k = arguments.get("k", 5)
    threshold = arguments.get("threshold", 0.35)
    max_tokens = arguments.get("max_tokens", 1500)

    if not query:
        return "Error: query is required"

    try:
        engine = _get_rag_engine()
        # index() is idempotent: skips if _indexed=True or loads persisted pickle
        engine.index()

        results = engine.search(query, k=k, threshold=threshold, max_tokens=max_tokens)
    except Exception as exc:
        logger.warning("knowledge_search failed: %s", exc, exc_info=True)
        return f"Knowledge search failed: {exc}. Ensure 'sentence-transformers' is installed (pip install -e '.[rag]')."

    if not results:
        return (
            f"No relevant knowledge found for query: '{query}'\n\n"
            f"Tips:\n"
            f"- Try rephrasing with more specific terms\n"
            f"- Lower threshold (current: {threshold}) to get broader matches\n"
            f"- The knowledge base may not cover this topic yet"
        )

    lines = [
        f"Knowledge Search Results for: '{query}'",
        f"Threshold: {threshold} | Top-{k} | Max Tokens: {max_tokens}",
        f"Indexed Documents: {engine.document_count}",
        "",
        "=" * 50,
    ]

    for i, doc in enumerate(results, 1):
        lines.append(f"\n[{i}] Relevant Knowledge:\n{doc}\n")

    lines.append("=" * 50)
    return "\n".join(lines)
