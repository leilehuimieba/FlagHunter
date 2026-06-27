"""关节C — KnowledgeMemory: a single front door over the knowledge/memory stores.

KnowledgeMemory coordinates the project's five knowledge stores so that callers
have ONE place to reach them instead of newing each store ad hoc:

  * ProjectMemory  — learned-rules / methodology / target-profile prompt block
  * RAG engine     — hybrid dense + BM25 retrieval
  * SessionLedger  — the harness run-event view (via SessionContextView)
  * StrategyMemory — cross-challenge strategy recall / persistence
  * ShadowGraph    — attack-graph insights derived from notes
  * Notes          — plain key/value findings sink

It is a *coordinator, not a store*: it owns NO state and persists NO second copy
of anything — every method delegates to the underlying store, which remains the
single source of truth. This is the antidote to scattered ``StoreX()`` newing,
not a new cache to keep in sync.

Why this module lives in ``agents/pa_agent`` (ORCHESTRATION) and NOT in
``knowledge/`` (CAPABILITY): it composes ORCHESTRATION-layer stores
(``strategy_memory``, ``session_context``). Placing it under ``knowledge/`` would
make a CAPABILITY module import upward into ORCHESTRATION, violating invariant I1
(now enforced by ``.importlinter``). From here it imports DOWN into
``flaghunter.knowledge`` and sideways within ``pa_agent`` — both legal.

Scope note (read-side收口 increment): the read/projection methods below are wired
into ``ContextAssembler``. The recall/write methods are defined as thin, faithful
delegations to the SAME canonical sinks the existing code uses (no divergent
second write path) but the three write chains (dispatcher / crew / session) are
NOT yet migrated to route through here — that is a later increment.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..base_agent import BaseAgent


class KnowledgeMemory:
    """Front door coordinating the five knowledge/memory stores."""

    def __init__(
        self,
        *,
        rag_engine: Any = None,
        project_root: Optional[Path] = None,
    ) -> None:
        self._rag_engine = rag_engine
        self._project_root = Path(project_root) if project_root else None

    @classmethod
    def from_agent(cls, agent: "BaseAgent") -> "KnowledgeMemory":
        """Build a facade from an agent's injected knowledge dependencies."""
        project_root = getattr(agent, "project_root", None)
        return cls(
            rag_engine=getattr(agent, "rag_engine", None),
            project_root=Path(project_root) if project_root else None,
        )

    # ------------------------------------------------------------------ #
    # READ / projection  (wired into ContextAssembler — keep sync)        #
    # ------------------------------------------------------------------ #
    def project_context(self, target: str = "", phase: str = "") -> str:
        """Project-level learned-rules / methodology / target-profile block.

        Delegates to ProjectMemory.get_context_for_prompt; returns "" on any
        failure (the prompt path must never raise)."""
        try:
            from flaghunter.knowledge.project_memory import ProjectMemory

            return ProjectMemory().get_context_for_prompt(target=target, phase=phase) or ""
        except Exception:
            return ""

    def rag_search(self, query: str) -> list:
        """Hybrid RAG hits for ``query`` ([] if no engine / empty query)."""
        engine = self._rag_engine
        if not engine or not query:
            return []
        try:
            return list(engine.search(query) or [])
        except Exception:
            return []

    # Front-door vocabulary alias for the same retrieval.
    def search_knowledge(self, query: str) -> list:
        return self.rag_search(query)

    def session_run_context(
        self,
        run_id: str,
        *,
        event_limit: int = 5,
        artifact_limit: int = 5,
    ) -> dict:
        """Raw harness session-ledger view for ``run_id`` ({} if unavailable).

        Returns the unformatted ``build_run_context`` dict; callers own their
        own projection/formatting (this method only收口 store access)."""
        run_id = str(run_id or "").strip()
        if not run_id or self._project_root is None:
            return {}
        try:
            from .session_context import SessionContextView

            root = self._project_root
            context = SessionContextView(
                ledger_root=root / "loot" / "session_ledgers",
                artifact_root=root / "loot" / "artifact_registry",
                checkpoint_root=root / "loot" / "checkpoints",
            ).build_run_context(
                run_id, event_limit=event_limit, artifact_limit=artifact_limit
            )
            return context or {}
        except Exception:
            return {}

    def attack_graph(self, notes: Optional[dict] = None):
        """Build a ShadowGraph from ``notes`` and return the graph object."""
        from flaghunter.knowledge.graph import ShadowGraph

        graph = ShadowGraph()
        if notes:
            graph.update_from_notes(notes)
        return graph

    # ------------------------------------------------------------------ #
    # RECALL / WRITE  (defined; 3 write chains NOT migrated this pass)    #
    # Thin delegations to the SAME canonical sinks — no second truth.     #
    # ------------------------------------------------------------------ #
    async def recall_strategy(self, fingerprint, *, top_k: int = 3):
        """Recall cross-challenge strategy entries for a challenge fingerprint.

        Delegates to StrategyMemoryStore.query (workspace-routed default path,
        see Bug2 fix). coordinator._apply_strategy_memory_contract is not yet
        migrated to call this."""
        from .strategy_memory import StrategyMemoryStore

        return await StrategyMemoryStore().query(fingerprint, top_k=top_k)

    async def record_learned(self, entry) -> None:
        """Persist a cross-challenge strategy entry → StrategyMemoryStore sink.

        Thin delegation to StrategyMemoryStore.save (same workspace-routed file
        the dispatcher writes). The dispatcher's build_entry/save loop is not
        migrated to route through here yet."""
        from .strategy_memory import StrategyMemoryStore

        await StrategyMemoryStore().save(entry)

    async def record_finding(
        self,
        *,
        runtime,
        key: str,
        value: str,
        category: str = "finding",
        confidence: str = "high",
        **metadata,
    ) -> None:
        """Record a plain key/value finding → the notes store sink.

        Delegates to the same ``notes`` tool sink that NoteStore.store_note
        ultimately calls, so there is no divergent write path. The dispatcher
        keeps NoteStore for its artifact-mirroring side effects; this is the
        front-door alias for code that only needs a plain note."""
        from flaghunter.tools.notes import notes as notes_tool

        await notes_tool(
            {
                "action": "update",
                "key": key,
                "value": value,
                "category": category,
                "confidence": confidence,
                **metadata,
            },
            runtime=runtime,
        )
