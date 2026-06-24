"""Delegate task tool — spawns permission-restricted sub-agents.

Phase 2: Exposes the SubagentRunner as a callable tool so the LLM can
delegate subtasks to specialized workers (Recon, VulnScan, Exploit, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Agent-orchestration meta-tool: it spawns sub-agents, so depending on agents/
# is intentional. The tools-layer "no agents import" rule targets capability
# tools (terminal/browser/sqlmap/...), NOT orchestration meta-tools like this.
# SUBAGENT_CONFIGS is needed at import time for the schema enum below;
# SubagentRunner is imported lazily in the tool body to keep the import-time
# surface minimal. See H9.
from ...agents.subagent import SUBAGENT_CONFIGS
from ...runtime.permission_enforcer import PermissionMode
from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


@register_tool(
    name="delegate_task",
    description=(
        "Delegate a subtask to a specialized sub-agent with restricted tools "
        "and permissions. Sub-agents run independently and return a summary. "
        "Use this to parallelize work — for example, delegate recon to 'Recon' "
        "while you analyze existing results, or delegate scanning to 'VulnScan' "
        "while you work on exploitation. Sub-agent types: "
        "Recon (port scan, subdomain enum), "
        "VulnScan (nuclei, nikto, sqlmap detection), "
        "Exploit (active exploitation), "
        "Analysis (read/search/summarize), "
        "General (all tools, full access)."
    ),
    schema=ToolSchema(
        properties={
            "task": {
                "type": "string",
                "description": "Task description for the sub-agent (e.g. 'Scan ports on 10.0.0.1')",
            },
            "subagent_type": {
                "type": "string",
                "enum": list(SUBAGENT_CONFIGS),
                "description": "Type of sub-agent to spawn",
            },
        },
        required=["task", "subagent_type"],
    ),
    category="agent",
    required_permission=PermissionMode.RECON_ONLY,
)
async def delegate_task(arguments: dict, runtime: "Runtime") -> str:
    task = str(arguments.get("task") or "").strip()
    subagent_type = str(arguments.get("subagent_type") or "General").strip()
    if not task:
        return "Error: 'task' is required"

    target = getattr(runtime, "target", "")

    from ...agents.subagent import SubagentRunner
    from ...config.settings import get_settings
    from ...llm.config import ModelConfig
    from ...llm.llm import LLM

    # Honour the configured model + temperature + max_tokens (settings singleton =
    # single source, H15) rather than letting the delegated subagent silently run
    # on ModelConfig() hardcoded defaults (temperature 0.7).
    settings = get_settings()
    llm = LLM(
        model=settings.model,
        config=ModelConfig(
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        ),
    )

    from ..registry import get_all_tools

    all_tools = get_all_tools()

    return await SubagentRunner.run(
        task=task,
        subagent_type=subagent_type,
        llm=llm,
        tools=list(all_tools),
        runtime=runtime,
        target=target,
    )
