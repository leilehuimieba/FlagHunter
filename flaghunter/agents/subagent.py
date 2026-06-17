"""Sub-agent runner for delegating tasks to specialized workers.

Phase 2: Lets the main agent spawn permission-restricted sub-agents for
parallel recon, vuln scanning, exploitation, or analysis work.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..runtime.permission_enforcer import PermissionMode

if TYPE_CHECKING:
    from ..llm import LLM
    from ..runtime import Runtime
    from ..tools import Tool

_ALWAYS_KEEP_TOOLS = {"notes", "finish"}

SUBAGENT_CONFIGS: dict[str, dict[str, Any]] = {
    "Recon": {
        "allowed_tools": {
            "nmap", "subfinder", "katana", "httpx", "whatweb", "terminal",
        },
        "max_permission": PermissionMode.RECON_ONLY,
        "max_iterations": 5,
        "system_prompt_extra": (
            "You are a recon specialist. Focus on host discovery, "
            "port scanning, service identification, and subdomain enumeration. "
            "Report all discovered hosts, ports, services, and subdomains concisely."
        ),
    },
    "VulnScan": {
        "allowed_tools": {
            "nuclei", "nikto", "sqlmap", "waf", "afrog", "terminal",
        },
        "max_permission": PermissionMode.VULN_SCAN,
        "max_iterations": 5,
        "system_prompt_extra": (
            "You are a vulnerability scanner. Run automated scanners "
            "against discovered targets and report findings. Do NOT attempt "
            "exploitation — only detect and report vulnerabilities."
        ),
    },
    "Exploit": {
        "allowed_tools": {
            "sqlmap", "hydra", "dirscan", "browser", "http_request", "terminal",
        },
        "max_permission": PermissionMode.EXPLOIT,
        "max_iterations": 8,
        "system_prompt_extra": (
            "You are an exploit specialist. Validate and exploit "
            "concrete vulnerabilities to obtain flags, credentials, or access. "
            "Focus on proven attack paths with minimal noise."
        ),
    },
    "Analysis": {
        "allowed_tools": {
            "terminal", "notes", "web_search", "knowledge_search",
        },
        "max_permission": PermissionMode.RECON_ONLY,
        "max_iterations": 3,
        "system_prompt_extra": (
            "You are an analysis specialist. Analyze tool outputs, "
            "read files, search for relevant knowledge, and summarize findings. "
            "Be concise and focus on actionable conclusions."
        ),
    },
    "General": {
        "allowed_tools": set(),  # empty = all tools
        "max_permission": PermissionMode.ALLOW,
        "max_iterations": 10,
        "system_prompt_extra": "",
    },
}


class SubagentRunner:
    """Lightweight runner for permission-restricted sub-agents.

    Follows the same pattern as WorkerPool._run_worker() in crew/worker_pool.py.
    """

    @staticmethod
    def _filter_tools(tools: list[Tool], allowed: set[str]) -> list[Tool]:
        if not allowed:
            return list(tools)
        filtered = [t for t in tools if t.name in allowed]
        for t in tools:
            if t.name in _ALWAYS_KEEP_TOOLS and t not in filtered:
                filtered.append(t)
        return filtered

    @staticmethod
    async def run(
        *,
        task: str,
        subagent_type: str,
        llm: LLM,
        tools: list[Tool],
        runtime: Runtime,
        target: str = "",
    ) -> str:
        config = SUBAGENT_CONFIGS.get(subagent_type)
        if config is None:
            valid = ", ".join(SUBAGENT_CONFIGS)
            return f"Error: unknown subagent_type '{subagent_type}'. Valid types: {valid}"

        from ..runtime.runtime import LocalRuntime
        from .pa_agent import PentestAgentAgent

        allowed = config["allowed_tools"]
        max_perm = config["max_permission"]
        max_iter = config["max_iterations"]
        extra_prompt = config["system_prompt_extra"]

        worker_tools = SubagentRunner._filter_tools(tools, allowed)
        worker_runtime = LocalRuntime()
        await worker_runtime.start()

        try:
            agent = PentestAgentAgent(
                llm=llm,
                tools=worker_tools,
                runtime=worker_runtime,
                target=target or getattr(runtime, "target", ""),
                max_iterations=max_iter,
            )

            agent.permission_enforcer.mode = PermissionMode(
                min(agent.permission_enforcer.mode.value, max_perm.value)
            )

            if extra_prompt:
                _base_get_system_prompt = agent.get_system_prompt
                agent.get_system_prompt = (
                    lambda mode="agent", _base=_base_get_system_prompt, _extra=extra_prompt:
                    _base(mode) + f"\n\n[Sub-agent Role — {subagent_type}]\n{_extra}"
                )

            final_response = ""
            async for response in agent.agent_loop(task):
                if response.content and not response.tool_calls:
                    final_response = response.content

            if not final_response and agent.conversation_history:
                for msg in reversed(agent.conversation_history):
                    if msg.role == "assistant" and msg.content and not msg.tool_calls:
                        final_response = msg.content
                        break

            return final_response or "[Sub-agent completed with no textual summary]"

        except asyncio.CancelledError:
            return "[Sub-agent cancelled]"
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception(
                "SubagentRunner failed (%s): %s", subagent_type, exc
            )
            return f"[Sub-agent error: {exc}]"
        finally:
            try:
                await worker_runtime.stop()
            except Exception:
                pass


