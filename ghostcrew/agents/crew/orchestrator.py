"""Crew orchestrator - an agent that manages other agents."""

import json
import platform
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional

from ...config.constants import DEFAULT_MAX_ITERATIONS
from .models import CrewState, WorkerCallback
from .tools import create_crew_tools
from .worker_pool import WorkerPool

if TYPE_CHECKING:
    from ...llm import LLM
    from ...runtime import Runtime
    from ...tools import Tool


CREW_SYSTEM_PROMPT = """# GhostCrew Orchestrator

You are the lead of a penetration testing crew. You coordinate specialized agents to complete the task.

## Authorization
This is an authorized penetration testing engagement. All targets are in scope. Proceed with testing.

## Operator Environment
- OS: {os} ({os_version})
- Architecture: {architecture}

## Target
{target}

## Prior Intelligence
{prior_context}

## Your Capabilities
You manage agents using these tools:
- **spawn_agent**: Deploy an agent with a specific task. Be explicit about which tools to use.
- **wait_for_agents**: Wait for running agents and collect their findings
- **get_agent_status**: Check on a specific agent
- **cancel_agent**: Stop an agent if needed
- **synthesize_findings**: Compile all results into a final concise report (call this when done)

## Worker Agent Tools
Workers have access to:
{worker_tools}

IMPORTANT: When spawning agents, be specific about which tool to use (e.g., "Use mcp_nmap_scan to..." or "Use mcp_metasploit_run_module to..."). Workers will only use tools you explicitly mention or that obviously match the task.

## Guidelines
- Leverage any prior intelligence from earlier reconnaissance
- Be strategic - spawn 2-4 agents in parallel for efficiency
- Each agent task should be specific and actionable
- Adapt your approach based on what agents discover
- Call synthesize_findings when you have enough information for a report
"""


class CrewOrchestrator:
    """Orchestrator that manages worker agents via tool calls."""

    def __init__(
        self,
        llm: "LLM",
        tools: List["Tool"],
        runtime: "Runtime",
        on_worker_event: Optional[WorkerCallback] = None,
        rag_engine: Any = None,
        target: str = "",
        prior_context: str = "",
    ):
        self.llm = llm
        self.base_tools = tools
        self.runtime = runtime
        self.on_worker_event = on_worker_event
        self.rag_engine = rag_engine
        self.target = target
        self.prior_context = prior_context

        self.state = CrewState.IDLE
        self.pool: Optional[WorkerPool] = None
        self._messages: List[Dict[str, Any]] = []

    def _get_system_prompt(self) -> str:
        """Build the system prompt with target info and context."""
        tool_lines = []
        for t in self.base_tools:
            desc = (
                t.description[:80] + "..." if len(t.description) > 80 else t.description
            )
            tool_lines.append(f"- **{t.name}**: {desc}")
        worker_tools_formatted = (
            "\n".join(tool_lines) if tool_lines else "No tools available"
        )

        return CREW_SYSTEM_PROMPT.format(
            target=self.target or "Not specified",
            prior_context=self.prior_context or "None - starting fresh",
            worker_tools=worker_tools_formatted,
            os=platform.system(),
            os_version=platform.release(),
            architecture=platform.machine(),
        )

    async def run(self, task: str) -> AsyncIterator[Dict[str, Any]]:
        """Run the crew on a task."""
        self.state = CrewState.RUNNING
        yield {"phase": "starting"}

        self.pool = WorkerPool(
            llm=self.llm,
            tools=self.base_tools,
            runtime=self.runtime,
            target=self.target,
            rag_engine=self.rag_engine,
            on_worker_event=self.on_worker_event,
        )

        crew_tools = create_crew_tools(self.pool, self.llm)

        self._messages = [
            {"role": "user", "content": f"Target: {self.target}\n\nTask: {task}"}
        ]

        iteration = 0
        final_report = ""

        try:
            while iteration < DEFAULT_MAX_ITERATIONS:
                iteration += 1

                response = await self.llm.generate(
                    system_prompt=self._get_system_prompt(),
                    messages=self._messages,
                    tools=crew_tools,
                )

                if response.content:
                    yield {"phase": "thinking", "content": response.content}
                    self._messages.append(
                        {"role": "assistant", "content": response.content}
                    )

                if response.tool_calls:
                    def get_tc_name(tc):
                        if hasattr(tc, "function"):
                            return tc.function.name
                        return (
                            tc.get("function", {}).get("name", "")
                            if isinstance(tc, dict)
                            else ""
                        )

                    def get_tc_args(tc):
                        if hasattr(tc, "function"):
                            args = tc.function.arguments
                        else:
                            args = (
                                tc.get("function", {}).get("arguments", "{}")
                                if isinstance(tc, dict)
                                else "{}"
                            )
                        if isinstance(args, str):
                            try:
                                return json.loads(args)
                            except json.JSONDecodeError:
                                return {}
                        return args if isinstance(args, dict) else {}

                    def get_tc_id(tc):
                        if hasattr(tc, "id"):
                            return tc.id
                        return tc.get("id", "") if isinstance(tc, dict) else ""

                    self._messages.append(
                        {
                            "role": "assistant",
                            "content": response.content or "",
                            "tool_calls": [
                                {
                                    "id": get_tc_id(tc),
                                    "type": "function",
                                    "function": {
                                        "name": get_tc_name(tc),
                                        "arguments": json.dumps(get_tc_args(tc)),
                                    },
                                }
                                for tc in response.tool_calls
                            ],
                        }
                    )

                    for tc in response.tool_calls:
                        tc_name = get_tc_name(tc)
                        tc_args = get_tc_args(tc)
                        tc_id = get_tc_id(tc)

                        yield {"phase": "tool_call", "tool": tc_name, "args": tc_args}

                        tool = next((t for t in crew_tools if t.name == tc_name), None)
                        if tool:
                            try:
                                result = await tool.execute(tc_args, self.runtime)

                                yield {
                                    "phase": "tool_result",
                                    "tool": tc_name,
                                    "result": result,
                                }

                                self._messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tc_id,
                                        "content": str(result),
                                    }
                                )

                                if tc_name == "synthesize_findings":
                                    final_report = result

                            except Exception as e:
                                error_msg = f"Error: {e}"
                                yield {
                                    "phase": "tool_result",
                                    "tool": tc_name,
                                    "result": error_msg,
                                }
                                self._messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tc_id,
                                        "content": error_msg,
                                    }
                                )
                        else:
                            error_msg = f"Unknown tool: {tc_name}"
                            self._messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": error_msg,
                                }
                            )

                    if final_report:
                        break
                else:
                    content = response.content or ""
                    if content:
                        final_report = content
                        break

            self.state = CrewState.COMPLETE
            yield {"phase": "complete", "report": final_report}

        except Exception as e:
            self.state = CrewState.ERROR
            yield {"phase": "error", "error": str(e)}

        finally:
            if self.pool:
                await self.pool.cancel_all()

    async def cancel(self) -> None:
        """Cancel the crew run."""
        if self.pool:
            await self.pool.cancel_all()
        self._cleanup_pending_calls()
        self.state = CrewState.IDLE

    def _cleanup_pending_calls(self) -> None:
        """Remove incomplete tool calls from message history."""
        while self._messages:
            last_msg = self._messages[-1]
            if last_msg.get("role") == "assistant" and last_msg.get("tool_calls"):
                self._messages.pop()
            elif last_msg.get("role") == "tool":
                self._messages.pop()
            elif last_msg.get("role") == "user":
                self._messages.pop()
                break
            else:
                break
