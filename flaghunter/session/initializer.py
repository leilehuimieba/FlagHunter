"""Shared agent component initialization logic.

Used by both the TUI and the MCP server so the startup sequence is defined
in exactly one place.  Callers supply an optional *on_progress* callback
that receives ``(level: str, message: str)`` notifications; if omitted the
messages are silently discarded.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional


def has_ssh_runtime_config() -> bool:
    """Return True when enough SSH runtime config exists to attempt auto-connect."""
    return bool(os.getenv("KALI_SSH_HOST"))


def activate_workspace_for_target(
    target: Optional[str],
    *,
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> Optional[str]:
    """Create/select the workspace derived from *target* and make it active."""
    if not target:
        return None

    from ..workspaces.manager import WorkspaceManager

    workspace_name = re.sub(
        r"[^\w.-]",
        "_",
        target.replace("http://", "").replace("https://", ""),
    ).strip("._-")
    workspace_name = (workspace_name or "target")[:64]

    wm = WorkspaceManager()
    if not wm.workspace_path(workspace_name).exists():
        wm.create(workspace_name)
    wm.set_active(workspace_name)
    wm.set_last_target(workspace_name, target)

    if on_progress:
        on_progress("info", f"Workspace activated: {workspace_name}")

    return workspace_name


def build_challenge_snapshot_service(
    *,
    state_store: Any = None,
    read_model_store: Any = None,
) -> Any:
    """Build the challenge snapshot service with session-owned adapter wiring."""
    from ..adapters.storage.state_store_adapter import StateStoreAdapter
    from ..application.challenge.snapshot_service import BuildChallengeRunSnapshot

    wired_state_store = (
        StateStoreAdapter(state_store)
        if state_store is not None
        else None
    )
    return BuildChallengeRunSnapshot(
        state_store=wired_state_store,
        read_model_store=read_model_store,
    )


def build_challenge_claim_store(
    *,
    claim_store: Any = None,
) -> Any:
    """Build the challenge claim store with session-owned adapter wiring."""
    from ..adapters.storage.claim_store_adapter import ClaimStoreAdapter

    if claim_store is None:
        return None
    return ClaimStoreAdapter(claim_store)


async def build_runtime(
    *,
    docker: bool = False,
    ssh: bool = False,
    auto_ssh: bool = True,
    on_progress: Optional[Callable[[str, str], None]] = None,
):
    """Resolve, start, and describe the runtime to use."""

    def _log(msg: str, level: str = "info") -> None:
        if on_progress:
            on_progress(level, msg)

    runtime_info: dict[str, Any] = {
        "requested": "docker" if docker else "ssh" if ssh else "auto",
        "selected": "local",
        "auto_selected": False,
        "connected": False,
        "host": None,
        "port": None,
        "user": None,
        "label": "Local",
        "status_text": "Local runtime active",
        "fallback_reason": None,
    }

    if docker:
        from ..config.settings import get_settings
        from ..runtime.docker_runtime import DockerConfig, DockerRuntime
        from ..runtime.hybrid_runtime import HybridBrowserRuntime

        settings = get_settings()
        runtime: Any = HybridBrowserRuntime(
            primary=DockerRuntime(
                config=DockerConfig(
                    image=settings.docker_image,
                    container_name=settings.container_name,
                )
            )
        )
        _log(f"Using DockerRuntime (image: {settings.docker_image}).")
        await runtime.start()
        runtime_info.update(
            {
                "selected": "docker",
                "connected": True,
                "label": "Docker",
                "status_text": f"Docker runtime active ({settings.docker_image})",
            }
        )
        return runtime, runtime_info

    if ssh:
        from ..runtime.hybrid_runtime import HybridBrowserRuntime
        from ..runtime.ssh_runtime import SSHRuntime

        runtime = HybridBrowserRuntime(primary=SSHRuntime())
        _log("Using SSHRuntime — connecting to Kali VM.")
        await runtime.start()
        runtime_info.update(
            {
                "selected": "ssh",
                "connected": True,
                "host": runtime.host,
                "port": runtime.port,
                "user": runtime.user,
                "label": "SSH",
                "status_text": (
                    f"SSH connected: {runtime.user}@{runtime.host}:{runtime.port}"
                ),
            }
        )
        return runtime, runtime_info

    if auto_ssh and has_ssh_runtime_config():
        from ..runtime.hybrid_runtime import HybridBrowserRuntime
        from ..runtime.ssh_runtime import SSHRuntime

        runtime = HybridBrowserRuntime(primary=SSHRuntime())
        runtime_info.update(
            {
                "requested": "auto-ssh",
                "host": runtime.host,
                "port": runtime.port,
                "user": runtime.user,
            }
        )
        _log("Auto-detected Kali VM SSH configuration — testing SSHRuntime.")
        try:
            await runtime.start()
            _log("Using SSHRuntime — connected to Kali VM.")
            runtime_info.update(
                {
                    "selected": "ssh",
                    "auto_selected": True,
                    "connected": True,
                    "label": "SSH (auto)",
                    "status_text": (
                        f"SSH connected: {runtime.user}@{runtime.host}:{runtime.port}"
                    ),
                }
            )
            return runtime, runtime_info
        except Exception as exc:
            runtime_info.update(
                {
                    "selected": "local",
                    "connected": False,
                    "label": "Local",
                    "status_text": "SSH unavailable — fell back to LocalRuntime",
                    "fallback_reason": str(exc),
                }
            )
            _log(
                f"SSHRuntime auto-detect failed, falling back to LocalRuntime: {exc}",
                "warning",
            )

    from ..runtime.runtime import LocalRuntime

    runtime = LocalRuntime()
    _log("Using LocalRuntime.")
    await runtime.start()
    return runtime, runtime_info


async def build_agent_components(
    target: Optional[str] = None,
    scope: Optional[list[str]] = None,
    model: Optional[str] = None,
    docker: bool = False,
    ssh: bool = False,
    no_rag: bool = False,
    no_mcp: bool = False,
    on_progress: Optional[Callable[[str, str], None]] = None,
    after_mcp_load: Optional[Callable[[], None]] = None,
    prebuilt_rag=None,
) -> dict[str, Any]:
    """Build every shared agent component in the standard order.

    Returns a dict with keys:
        ``agent``           – FlagHunterAgent instance
        ``runtime``         – SSHRuntime, DockerRuntime, or LocalRuntime
        ``runtime_info``    – runtime selection + connection status metadata
        ``rag_engine``      – RAGEngine (or None)
        ``all_tools``       – list of all registered Tool objects
        ``mcp_manager``     – MCPManager (or None)
        ``rag_doc_count``   – int
        ``mcp_server_count``– int
        ``model``           – resolved model string
    """
    from ..agents.pa_agent import FlagHunterAgent
    from ..knowledge import RAGEngine
    from ..llm import LLM, ModelConfig
    from ..tools import get_all_tools, register_tool_instance

    scope = list(scope or [])

    def _log(msg: str, level: str = "info") -> None:
        if on_progress:
            on_progress(level, msg)

    if target:
        activate_workspace_for_target(target, on_progress=on_progress)

    # ------------------------------------------------------------------
    # 1. RAG Engine
    # ------------------------------------------------------------------
    rag_engine: Optional[RAGEngine] = None
    rag_doc_count = 0

    if prebuilt_rag is not None:
        rag_engine = prebuilt_rag
        rag_doc_count = rag_engine.get_document_count()
        _log(f"RAG engine ready — {rag_doc_count} documents indexed.")
    elif not no_rag:
        local_knowledge = Path("knowledge")
        bundled_path = Path(__file__).parent.parent / "knowledge" / "sources"
        knowledge_path: Optional[Path] = None

        if local_knowledge.exists() and any(local_knowledge.rglob("*.*")):
            knowledge_path = local_knowledge
        elif bundled_path.exists():
            knowledge_path = bundled_path

        if knowledge_path:
            try:
                from ..knowledge.embeddings import should_use_local_embeddings
                use_local = should_use_local_embeddings()

                rag_engine = RAGEngine(
                    knowledge_path=knowledge_path,
                    use_local_embeddings=use_local,
                )
                # Load a persisted index if present rather than force-rebuilding the
                # whole corpus on every startup (a multi-minute CPU job that has hung
                # for >25min on a heavy local model and blocked the run). Cold builds
                # skip the inline local-dense encode (see rag._local_dense_build_enabled)
                # so startup never blocks; BM25 / a prebuilt dense index still serve.
                await asyncio.to_thread(rag_engine.index, force=False)
                rag_doc_count = rag_engine.get_document_count()
                _log(f"RAG engine ready — {rag_doc_count} documents indexed.")
            except Exception as exc:
                _log(f"RAG engine failed, continuing without it: {exc}", "warning")
                rag_engine = None

    # ------------------------------------------------------------------
    # 2. Runtime
    # ------------------------------------------------------------------
    runtime, runtime_info = await build_runtime(
        docker=docker,
        ssh=ssh,
        auto_ssh=not docker and not ssh,
        on_progress=on_progress,
    )

    # === CPA M1 HOOK BEGIN ===
    try:
        from flaghunter.cpa_modules.m1_api_hub import init_m1, is_m1_enabled

        if is_m1_enabled():
            await init_m1()
            _log("[CPA M1] API Hub initialized.")
    except Exception as exc:
        _log(f"[CPA M1] Init failed, continuing without it: {exc}", "warning")
    # === CPA M1 HOOK END ===

    # === CPA M2 HOOK BEGIN ===
    if os.getenv("CPA_M2_CTF_KIT", "true").lower() != "false":
        try:
            from flaghunter.cpa_modules.m2_ctf_kit import init_m2
            await init_m2()
            _log("[CPA M2] CTF Kit initialized.")
        except Exception as exc:
            _log(f"[CPA M2] Init failed, continuing without it: {exc}", "warning")
    # === CPA M2 HOOK END ===

    # === CPA M3 HOOK BEGIN ===
    try:
        from flaghunter.cpa_modules.m3_reporter import init_m3, is_m3_enabled

        if is_m3_enabled():
            await init_m3()
            _log("[CPA M3] Reporter initialized.")
    except Exception as exc:
        _log(f"[CPA M3] Init failed, continuing without it: {exc}", "warning")
    # === CPA M3 HOOK END ===

    # === CPA M4 HOOK BEGIN ===
    try:
        from flaghunter.cpa_modules.m4_audit_guard import init_m4, is_m4_enabled

        if is_m4_enabled():
            await init_m4()
            _log("[CPA M4] Audit Guard initialized.")
    except Exception as exc:
        _log(f"[CPA M4] Init failed, continuing without it: {exc}", "warning")
    # === CPA M4 HOOK END ===

    # === CPA M5 HOOK BEGIN ===
    if os.getenv("CPA_M5_SWARM_LINK", "false").lower() == "true":
        try:
            from flaghunter.cpa_modules.m5_swarm_link import init_m5
            await init_m5()
            _log("[CPA M5] Swarm Link initialized.")
        except Exception as exc:
            _log(f"[CPA M5] Init failed, continuing without it: {exc}", "warning")
    # === CPA M5 HOOK END ===

    # === CPA M6 HOOK BEGIN ===
    try:
        from flaghunter.cpa_modules.m6_turbo import init_m6, is_m6_enabled

        if is_m6_enabled():
            await init_m6()
            _log("[CPA M6] Turbo initialized.")
    except Exception as exc:
        _log(f"[CPA M6] Init failed, continuing without it: {exc}", "warning")
    # === CPA M6 HOOK END ===

    # ------------------------------------------------------------------
    # 3. Model / LLM
    # ------------------------------------------------------------------
    if not model:
        model = os.getenv("FLAGHUNTER_MODEL")
    if not model:
        raise RuntimeError(
            "No model configured. Pass --model or set FLAGHUNTER_MODEL."
        )

    # Publish the resolved model to the settings singleton — the write-side of
    # the single-source-of-truth invariant. This is the one assembly path
    # (invariant I2), so whatever model the main agent runs (CLI --model, env,
    # or a caller override) lands in get_settings(); the singleton's readers
    # (delegate_task sub-agents, web_server, mcp_tools) then converge on the
    # SAME model instead of silently falling back to FLAGHUNTER_MODEL. Without
    # this, --model only reached the main LLM and sub-agents drifted to env.
    from ..config.settings import get_settings, update_settings

    update_settings(model=model)

    # Honour the configured temperature instead of hardcoding it, so the
    # settings singleton is the single source of truth (H15). Falls back to
    # DEFAULT_TEMPERATURE via the Settings dataclass default.
    llm = LLM(
        model=model,
        config=ModelConfig(
            temperature=get_settings().temperature,
            max_tokens=get_settings().max_tokens,
        ),
        rag_engine=rag_engine,
    )
    _log(f"LLM initialised: {model}")

    # ------------------------------------------------------------------
    # 4. Tools
    # ------------------------------------------------------------------
    all_tools = get_all_tools()
    _log(f"Built-in tools loaded: {len(all_tools)}")

    # ------------------------------------------------------------------
    # 5. Primary FlagHunterAgent
    # ------------------------------------------------------------------
    agent = FlagHunterAgent(
        llm=llm,
        tools=all_tools,
        runtime=runtime,
        target=target,
        scope=scope,
        rag_engine=rag_engine,
    )
    _log(f"FlagHunterAgent ready — target={target} scope={scope}")

    # ------------------------------------------------------------------
    # 6. Session persistence + Metrics (Phase 3 & 4)
    # ------------------------------------------------------------------
    try:
        from ..session.session_store import SessionStore
        agent._session_store = SessionStore()
        _log("Session store ready.")
    except Exception as exc:
        _log(f"Session store unavailable: {exc}", "warning")

    try:
        from ..observability import MetricsCollector
        agent._metrics = MetricsCollector()
        _log("Metrics collector ready.")
    except Exception as exc:
        _log(f"Metrics collector unavailable: {exc}", "warning")

    # ------------------------------------------------------------------
    # 7. External MCP servers (background task)
    # ------------------------------------------------------------------
    mcp_manager = None
    mcp_server_count = 0

    if not no_mcp:
        try:
            from ..mcp import MCPManager

            mcp_manager = MCPManager()
            mcp_server_count = len(mcp_manager.list_configured_servers())

            async def _load_mcp() -> None:
                try:
                    tools = await mcp_manager.connect_all()
                    agent.add_tools(tools)
                    for tool in tools:
                        register_tool_instance(tool)
                    _log(f"External MCP tools loaded: {len(tools)}")
                    if after_mcp_load:
                        after_mcp_load()
                except Exception as exc:
                    _log(f"External MCP connect failed: {exc}", "warning")

            asyncio.get_event_loop().create_task(_load_mcp())
            _log(f"External MCP servers: {mcp_server_count} configured.")
        except Exception as exc:
            _log(f"MCPManager unavailable: {exc}", "warning")

    return {
        "agent": agent,
        "runtime": runtime,
        "runtime_info": runtime_info,
        "rag_engine": rag_engine,
        "all_tools": all_tools,
        "mcp_manager": mcp_manager,
        "rag_doc_count": rag_doc_count,
        "mcp_server_count": mcp_server_count,
        "model": model,
    }
