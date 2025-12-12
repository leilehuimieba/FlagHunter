"""GhostCrew main pentesting agent."""

from typing import TYPE_CHECKING, List, Optional

from ..base_agent import BaseAgent
from ..prompts import ghost_agent, ghost_assist

if TYPE_CHECKING:
    from ...knowledge import RAGEngine
    from ...llm import LLM
    from ...runtime import Runtime
    from ...tools import Tool


class GhostCrewAgent(BaseAgent):
    """Main pentesting agent for GhostCrew."""

    def __init__(
        self,
        llm: "LLM",
        tools: List["Tool"],
        runtime: "Runtime",
        target: Optional[str] = None,
        scope: Optional[List[str]] = None,
        rag_engine: Optional["RAGEngine"] = None,
        **kwargs,
    ):
        """
        Initialize the GhostCrew agent.

        Args:
            llm: The LLM instance for generating responses
            tools: List of tools available to the agent
            runtime: The runtime environment for tool execution
            target: Primary target for penetration testing
            scope: List of in-scope targets/networks
            rag_engine: RAG engine for knowledge retrieval
            **kwargs: Additional arguments passed to BaseAgent
        """
        super().__init__(llm, tools, runtime, **kwargs)
        self.target = target
        self.scope = scope or []
        self.rag_engine = rag_engine

    def get_system_prompt(self, mode: str = "agent") -> str:
        """Generate system prompt with context.

        Args:
            mode: 'agent' for autonomous mode, 'assist' for single-shot assist mode
        """
        # Get RAG context if available
        rag_context = ""
        if self.rag_engine and self.conversation_history:
            last_msg = self.conversation_history[-1].content
            # Ensure content is a string (could be list for multimodal)
            if isinstance(last_msg, list):
                last_msg = " ".join(
                    str(part.get("text", ""))
                    for part in last_msg
                    if isinstance(part, dict)
                )
            if last_msg:
                relevant = self.rag_engine.search(last_msg)
                if relevant:
                    rag_context = "\n\n".join(relevant)

        # Get saved notes if available
        notes_context = ""
        try:
            from ...tools.notes import get_all_notes_sync

            notes = get_all_notes_sync()
            if notes:
                notes_lines = [f"- {key}: {value}" for key, value in notes.items()]
                notes_context = "\n".join(notes_lines)
        except Exception:
            pass  # Notes not available

        # Get environment info from runtime
        env = self.runtime.environment

        # Select template based on mode
        template = ghost_assist if mode == "assist" else ghost_agent

        return template.render(
            target=self.target,
            scope=self.scope,
            environment=env,
            rag_context=rag_context,
            notes_context=notes_context,
            tools=self.tools,
            plan=self._task_plan if mode == "agent" else None,
        )

    def set_target(self, target: str, scope: Optional[List[str]] = None):
        """
        Set or update the target.

        Args:
            target: The primary target
            scope: Optional list of scope items
        """
        self.target = target
        if scope:
            self.scope = scope

    def add_to_scope(self, *items: str):
        """
        Add items to the scope.

        Args:
            *items: Items to add to scope
        """
        self.scope.extend(items)
