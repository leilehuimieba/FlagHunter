"""AgentSession — the single facade between entrypoints and the agent engine.

Architecture joint A. Every entrypoint (TUI / CLI / web / MCP) is meant to:

    session = await AgentSession.create(target=..., model=...)
    unsubscribe = session.events().subscribe(my_render_callback)
    result = await session.run("enumerate example.com")

instead of each one separately constructing LLM / Tools / Runtime and wiring
its own event mechanism. This enforces two architecture invariants:

- **I2 (single assembly path).** ``create`` funnels through the shared
  ``build_agent_components`` composition root, so the CPA module hooks
  (M1–M6) run for *every* entrypoint — fixing the bug where CLI and
  web_server skipped them.
- **I3 (single event source).** All run-time events go through one neutral
  :class:`~flaghunter.session.event_bus.EventBus`.

``build_agent_components`` lives in ``flaghunter.session.initializer``, below
the entry/interface layer, so this facade never imports UI/server code while
assembling the engine.  ``interface.initializer`` remains as a compatibility
re-export for older callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .event_bus import EventBus


@dataclass(slots=True)
class RunResult:
    """Outcome of a single :meth:`AgentSession.run` invocation."""

    status: str = "completed"  # "completed" | "error" | "stopped"
    output: str = ""           # last plain assistant message
    flag: Optional[str] = None  # CTF flag, when applicable
    findings: list = field(default_factory=list)
    tokens: int = 0
    iterations: int = 0
    session_id: Optional[str] = None
    messages: list = field(default_factory=list)
    error: Optional[str] = None


# A builder returns the build_agent_components-style component dict.
ComponentBuilder = Callable[..., Awaitable[dict[str, Any]]]


class AgentSession:
    """Unifying facade: assemble once, expose components, run with one event bus."""

    def __init__(self, components: dict[str, Any], bus: Optional[EventBus] = None) -> None:
        self._components = components
        self._bus = bus or EventBus()

    # ------------------------------------------------------------------
    # Construction (I2: single assembly path)
    # ------------------------------------------------------------------
    @classmethod
    async def create(
        cls,
        *,
        target: Optional[str] = None,
        scope: Optional[list[str]] = None,
        model: Optional[str] = None,
        docker: bool = False,
        ssh: bool = False,
        no_rag: bool = False,
        no_mcp: bool = False,
        on_progress: Optional[Callable[[str, str], None]] = None,
        after_mcp_load: Optional[Callable[[], None]] = None,
        prebuilt_rag: Any = None,
        builder: Optional[ComponentBuilder] = None,
    ) -> "AgentSession":
        """Build all shared components via the composition root, then wrap them.

        *builder* lets callers (and tests) inject the component builder. When
        omitted, ``build_agent_components`` is imported lazily from the
        session-owned composition root.

        *after_mcp_load* and *prebuilt_rag* are forwarded to the builder so the
        TUI (which refreshes its header after external MCP tools load, and may
        hand in a RAG engine warmed up on a background thread) can adopt this
        single assembly path instead of calling ``build_agent_components``
        directly (architecture invariant I2).
        """
        if builder is None:
            from .initializer import build_agent_components as builder

        components = await builder(
            target=target,
            scope=scope,
            model=model,
            docker=docker,
            ssh=ssh,
            no_rag=no_rag,
            no_mcp=no_mcp,
            on_progress=on_progress,
            after_mcp_load=after_mcp_load,
            prebuilt_rag=prebuilt_rag,
        )
        return cls(components)

    # ------------------------------------------------------------------
    # Component accessors
    # ------------------------------------------------------------------
    @property
    def components(self) -> dict[str, Any]:
        return self._components

    @property
    def agent(self) -> Any:
        return self._components.get("agent")

    @property
    def runtime(self) -> Any:
        return self._components.get("runtime")

    @property
    def runtime_info(self) -> dict[str, Any]:
        return self._components.get("runtime_info", {})

    @property
    def llm(self) -> Any:
        # build_agent_components builds the LLM inside the agent; expose it.
        agent = self.agent
        return getattr(agent, "llm", None) if agent is not None else None

    @property
    def tools(self) -> Any:
        return self._components.get("all_tools")

    @property
    def rag_engine(self) -> Any:
        return self._components.get("rag_engine")

    @property
    def mcp_manager(self) -> Any:
        return self._components.get("mcp_manager")

    @property
    def model(self) -> Optional[str]:
        return self._components.get("model")

    # ------------------------------------------------------------------
    # Events (I3: single event source)
    # ------------------------------------------------------------------
    def events(self) -> EventBus:
        return self._bus

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    async def run(self, task: str) -> RunResult:
        """Drive the default agent loop, mirroring each step onto the bus.

        Token accounting here is a naive sum of reported ``total_tokens``;
        callers that need de-duplicated counts may track their own via the
        event subscription (reconciled in P1-b).

        Adoption note (H11): this is the facade's *programmatic* execution path
        — a thin "assemble → run → RunResult" convenience for headless/embedding
        callers. The interactive entrypoints (TUI / CLI / web) intentionally do
        NOT use it: they iterate ``session.agent.agent_loop(...)`` themselves so
        each can render per-message with its own richly-shaped events (e.g. web's
        SSE ``tool_call`` carrying task_id/run_id). They still adopt the facade's
        *assembly* half via :meth:`create` (invariant I2). run() is retained as
        the clean programmatic entry, not dead code.
        """
        agent = self.agent
        if agent is None:
            raise RuntimeError("AgentSession has no agent; build it via create().")

        result = RunResult(status="completed")
        self._bus.emit("run_start", {"task": task}, source="session")
        try:
            async for message in agent.agent_loop(task):
                result.iterations += 1
                result.messages.append(message)

                usage = getattr(message, "usage", None)
                if usage and usage.get("total_tokens"):
                    result.tokens += usage["total_tokens"]

                role = getattr(message, "role", "")
                content = getattr(message, "content", "") or ""
                tool_calls = getattr(message, "tool_calls", None)
                if role == "assistant" and content and not tool_calls:
                    result.output = content

                self._bus.emit(
                    "agent_message",
                    {
                        "role": role,
                        "content": content,
                        "tool_calls": tool_calls,
                        "usage": usage,
                        "metadata": getattr(message, "metadata", {}),
                    },
                    source="agent",
                )
        except Exception as exc:
            # Facade contract: always return a RunResult; report errors via
            # status + the bus rather than propagating loop internals to the
            # entrypoint.
            result.status = "error"
            result.error = str(exc)
            self._bus.emit("run_error", {"error": str(exc)}, source="session")
            return result

        self._bus.emit(
            "run_complete",
            {"status": result.status, "iterations": result.iterations, "tokens": result.tokens},
            source="session",
        )
        return result
