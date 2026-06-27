"""Base agent class for FlagHunter."""

import asyncio
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator, List, Optional

from ..config.constants import AGENT_MAX_ITERATIONS
from ..runtime.permission_enforcer import PermissionEnforcer, PermissionMode
from ..workspaces import validation
from ..workspaces.manager import WorkspaceManager
from .state import AgentState, AgentStateManager

if TYPE_CHECKING:
    from ..llm import LLM
    from ..runtime import Runtime
    from ..tools import Tool

_TOOL_LIMIT = 128


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""

    id: str
    name: str
    arguments: dict

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}

    @classmethod
    def from_dict(cls, data: dict) -> "ToolCall":
        return cls(
            id=data["id"], name=data["name"], arguments=data.get("arguments", {})
        )


@dataclass
class ToolResult:
    """Result from a tool execution."""

    tool_call_id: str
    tool_name: str
    result: Optional[str] = None
    error: Optional[str] = None
    success: bool = True
    suggested_tools: Optional[List["Tool"]] = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "result": self.result,
            "error": self.error,
            "success": self.success,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolResult":
        return cls(
            tool_call_id=data["tool_call_id"],
            tool_name=data["tool_name"],
            result=data.get("result"),
            error=data.get("error"),
            success=data.get("success", True),
            duration_ms=data.get("duration_ms", 0.0),
        )


@dataclass
class AgentMessage:
    """A message in the agent conversation."""

    role: str  # "user", "assistant", "tool_result", "system"
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    tool_results: Optional[List[ToolResult]] = None
    metadata: dict = field(default_factory=dict)
    usage: Optional[dict] = None  # Token usage from LLM response

    def to_llm_format(self) -> dict:
        """Convert to LLM message format."""
        import json

        msg = {"role": self.role, "content": self.content}

        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": (
                            json.dumps(tc.arguments)
                            if isinstance(tc.arguments, dict)
                            else tc.arguments
                        ),
                    },
                }
                for tc in self.tool_calls
            ]

        return msg

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "tool_calls": (
                [tc.to_dict() for tc in self.tool_calls] if self.tool_calls else None
            ),
            "tool_results": (
                [tr.to_dict() for tr in self.tool_results]
                if self.tool_results
                else None
            ),
            "metadata": self.metadata,
            "usage": self.usage,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMessage":
        tool_calls = None
        if data.get("tool_calls"):
            tool_calls = [ToolCall.from_dict(tc) for tc in data["tool_calls"]]
        tool_results = None
        if data.get("tool_results"):
            tool_results = [ToolResult.from_dict(tr) for tr in data["tool_results"]]
        return cls(
            role=data["role"],
            content=data.get("content", ""),
            tool_calls=tool_calls,
            tool_results=tool_results,
            metadata=data.get("metadata", {}),
            usage=data.get("usage"),
        )


class BaseAgent(ABC):
    """Base class for all agents."""

    def __init__(
        self,
        llm: "LLM",
        tools: List["Tool"],
        runtime: "Runtime",
        max_iterations: int = AGENT_MAX_ITERATIONS,
        **kwargs,
    ):
        """
        Initialize base agent state.

        Args:
            llm: LLM instance used for generation
            tools: Available tool list
            runtime: Runtime used for tool execution
            max_iterations: Safety limit for iterations
        """
        self.llm = llm
        self.tools = tools
        self.runtime = runtime
        self.max_iterations = max_iterations

        self.suggested_tools: List[Tool] = []

        # Permission enforcer (reads mode from FLAGHUNTER_PERMISSION_MODE env var)
        self.permission_enforcer = PermissionEnforcer.from_env()

        # Unified tool executor (replaces direct tool.execute() calls)
        from ..tools.executor import ToolExecutor

        self.tool_executor = ToolExecutor(runtime)

        # Agent runtime state
        self.state_manager = AgentStateManager()
        self.conversation_history: List[AgentMessage] = []

        # Task planning structure (used by finish tool)
        try:
            from ..tools.finish import TaskPlan

            self._task_plan = TaskPlan()
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception("Failed importing TaskPlan: %s", e)
            try:
                from flaghunter.session.notifier import notify

                notify("warning", f"Failed to import TaskPlan: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about TaskPlan import failure"
                )

            # Fallback simple plan structure
            class _SimplePlan:
                def __init__(self):
                    self.steps = []
                    self.original_request = ""

                def clear(self):
                    self.steps.clear()

                def is_complete(self):
                    return True

                def has_failure(self):
                    return False

            self._task_plan = _SimplePlan()

        # Expose plan to runtime so tools like `finish` can access it
        try:
            self.runtime.plan = self._task_plan
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(
                "Failed to attach plan to runtime: %s", e
            )
            try:
                from flaghunter.session.notifier import notify

                notify("warning", f"Failed to attach plan to runtime: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about runtime plan attach failure"
                )

        # Session persistence (Phase 3)
        self._session_store = None
        self._session_id: str | None = None
        self._auto_save_interval = 5  # snapshot every N iterations

        # Hook system (Phase 4)
        from ..hooks import get_hook_runner
        self.hooks = get_hook_runner()

        # Metrics collector (Phase 4)
        self._metrics = None

        # Ensure agent starts idle
        self.state_manager.transition_to(AgentState.IDLE)

    @abstractmethod
    def get_system_prompt(self, mode: str = "agent") -> str:
        """Return the system prompt for this agent.

        Args:
            mode: 'agent' for autonomous mode, 'assist' for single-shot assist mode
        """
        pass

    async def agent_loop(self, initial_message: str) -> AsyncIterator[AgentMessage]:
        """
        Main agent execution loop.

        Starts a new task session, resetting previous state and history.

        Simple control flow:
        - Tool calls: Execute tools, continue loop
        - Text response (no tools): Done
        - Max iterations reached: Force stop with warning

        Args:
            initial_message: The initial user message to process

        Yields:
            AgentMessage objects as the agent processes
        """
        # Always reset for a new agent loop task to ensure clean state
        self.reset()
        self._task_plan.clear()

        self.state_manager.transition_to(AgentState.THINKING)
        self.conversation_history.append(
            AgentMessage(role="user", content=initial_message)
        )

        async for msg in self._run_loop():
            yield msg

    async def continue_conversation(
        self, user_message: str
    ) -> AsyncIterator[AgentMessage]:
        """
        Continue the conversation with a new user message.

        Args:
            user_message: The new user message

        Yields:
            AgentMessage objects as the agent processes
        """
        self.conversation_history.append(
            AgentMessage(role="user", content=user_message)
        )
        self.state_manager.transition_to(AgentState.THINKING)

        async for msg in self._run_loop():
            yield msg

    async def wake_up(self, mode: str = "agent") -> AsyncIterator[AgentMessage]:
        """Re-enter processing to handle a pending push notification.

        The notification has already been injected into conversation_history by
        the watcher.  Dispatches to the loop matching the active TUI mode so
        the agent resumes in the same style it was using before going idle:
          - "assist"   → single LLM call + one tool round
          - "interact" → streaming chat loop until natural stop
          - "agent"    → autonomous _run_loop() (no plan reset)
        """
        self.state_manager.transition_to(AgentState.THINKING)
        if mode == "assist":
            async for msg in self._assist_loop():
                yield msg
        elif mode == "interact":
            async for msg in self._interact_loop():
                yield msg
        else:
            async for msg in self._run_loop():
                yield msg

    async def _run_loop(self) -> AsyncIterator[AgentMessage]:
        """
        Core agent loop logic - shared by agent_loop, continue_conversation and wake_up.

        Termination conditions:
        1. finish tool is called AND plan complete -> clean exit with summary
        2. max_iterations reached -> forced exit with warning
        3. error -> exit with error state

        Text responses WITHOUT tool calls are treated as "thinking out loud"
        and do NOT terminate the loop. This prevents premature stopping.

        Plan creation is optional — LLM decides whether to call generate_plan.
        When a plan exists, completion is enforced before allowing finish.

        Yields:
            AgentMessage objects as the agent processes
        """
        # Allow subclasses to set up mode-specific context (CTF, etc.)
        await self._prepare_context()

        iteration = 0
        pending_plan_context = False

        # Phase 4: start metrics session
        if self._metrics is not None:
            if not self._session_id:
                self._session_id = uuid.uuid4().hex[:12]
            self._metrics.start_session(self._session_id)

        while iteration < self.max_iterations:
            iteration += 1

            # Phase 4: per-turn timing
            _turn_t0 = __import__("time").monotonic()

            # Phase 3: auto-save session every N iterations
            if (
                self._session_store is not None
                and iteration % self._auto_save_interval == 0
                and iteration > 0
            ):
                try:
                    self._session_id = self._session_store.save(
                        self, session_id=self._session_id
                    )
                except Exception:
                    pass

            agent_tools = [t for t in self.tools if t.enabled]

            # Plan generation is now an optional tool (generate_plan) —
            # LLM decides when/if to create a plan. No forced planning.

            has_tool_results_pending = bool(
                self.conversation_history
                and self.conversation_history[-1].role == "tool_result"
                and self.conversation_history[-1].tool_results
            )
            if has_tool_results_pending:
                task_hint = "tool_parse"
            elif pending_plan_context:
                task_hint = "planning"
            else:
                task_hint = "analysis"

            # ── Reasoning-layer hint injection ───────────────────────────────
            system_prompt = self.get_system_prompt()
            reasoning_layer = getattr(self, "reasoning_layer", None)
            hint = ""
            if reasoning_layer and has_tool_results_pending:
                hint = reasoning_layer.get_next_action_hint(
                    last_tool_results=[
                        getattr(msg, "tool_results", None)
                        for msg in self.conversation_history[-1:]
                        if getattr(msg, "role", "") == "tool_result"
                    ],
                    conversation_summary=self.conversation_history[-6:],
                )
                if hint:
                    system_prompt += f"\n\n[Reasoning Guidance]\n{hint}\n"

            # Phase 2: recommend delegate_task when reasoning suggests delegation
            if hint and "delegat" in hint.lower():
                for t in self.tools:
                    if t.name == "delegate_task" and t not in self.suggested_tools:
                        self.suggested_tools.append(t)

            response = await self.llm.generate(task_hint=task_hint,
                system_prompt=system_prompt,
                messages=self._format_messages_for_llm(),
                tools=agent_tools
                + self.suggested_tools,  # Only, enabled tools + suggested tools.
            )
            pending_plan_context = False

            # Case 1: Empty response (Error)
            if not response.tool_calls and not response.content:
                stuck_msg = AgentMessage(
                    role="assistant",
                    content="Agent returned empty response. Exiting gracefully.",
                    metadata={"empty_response": True},
                )
                self.conversation_history.append(stuck_msg)
                yield stuck_msg
                self.state_manager.transition_to(AgentState.COMPLETE)
                self._export_metrics()
                return

            # Case 2: Thinking / Intermediate Output (Content but no tools)
            if not response.tool_calls:
                has_reasoning = bool(getattr(response, "reasoning_content", None))
                thinking_msg = AgentMessage(
                    role="assistant",
                    content=response.content,
                    usage=response.usage,
                    metadata={
                        "intermediate": True,
                        "is_reasoning": has_reasoning,
                    },
                )
                self.conversation_history.append(thinking_msg)
                yield thinking_msg
                continue

            # Case 3: Tool Execution
            # Yield reasoning/thinking content before tool calls (separate display)
            reasoning = getattr(response, "reasoning_content", None)
            if reasoning:
                reasoning_msg = AgentMessage(
                    role="assistant",
                    content=reasoning,
                    metadata={"intermediate": True, "is_reasoning": True},
                )
                yield reasoning_msg

            # Build tool calls list
            tool_calls = [
                ToolCall(
                    id=tc.id if hasattr(tc, "id") else str(i),
                    name=(
                        tc.function.name
                        if hasattr(tc, "function")
                        else tc.get("name", "")
                    ),
                    arguments=self._parse_arguments(tc),
                )
                for i, tc in enumerate(response.tool_calls)
            ]

            # Execute tools
            self.state_manager.transition_to(AgentState.EXECUTING)

            # Yield thinking message if content exists (before execution)
            if response.content:
                thinking_msg = AgentMessage(
                    role="assistant",
                    content=response.content,
                    usage=response.usage,
                    metadata={"intermediate": True},
                )
                yield thinking_msg

            tool_results = await self._execute_tools(response.tool_calls)
            await self._handle_tool_results(tool_results)

            # ── Loop-budget optimization: pure finish calls don't cost iterations ──
            # When the LLM only emits finish tool calls (no actual work tools),
            # we decrement the iteration counter so these administrative calls
            # don't consume the agent's action budget.
            _all_finish = bool(tool_calls) and all(
                tc.name == "finish" for tc in tool_calls
            )
            if _all_finish and iteration > 0:
                iteration -= 1
            # ── End loop-budget optimization ─────────────────────────────────────

            for tool_result in tool_results:
                # If there are suggested tools to inject (from RAG optimizer, inject them)
                if tool_result.suggested_tools:
                    self.suggested_tools += (
                        tool_result.suggested_tools
                    )  # The suggested tools list is overwritten everytime that the RAG optimizer is called
                    self.deduplicate_suggested_tools()  # Deduplicate

            # Purge excess suggested tools if total exceeds 128
            total_tools = len(agent_tools) + len(self.suggested_tools)
            if total_tools > _TOOL_LIMIT:
                allowed_suggested = max(0, _TOOL_LIMIT - len(agent_tools))
                self.suggested_tools = (
                    self.suggested_tools[-allowed_suggested:]
                    if allowed_suggested > 0
                    else []
                )

            # Record in history
            assistant_msg = AgentMessage(
                role="assistant",
                content=response.content or "",
                tool_calls=tool_calls,
                usage=response.usage,
            )
            self.conversation_history.append(assistant_msg)

            tool_result_msg = AgentMessage(
                role="tool_result", content="", tool_results=tool_results
            )
            self.conversation_history.append(tool_result_msg)

            # Phase 4: record turn metrics
            if self._metrics is not None:
                _turn_duration = (__import__("time").monotonic() - _turn_t0) * 1000
                _usage = response.usage or {}
                from ..observability import TurnMetrics
                self._metrics.record_turn(TurnMetrics(
                    iteration=iteration,
                    tool_calls=[tc.name for tc in tool_calls],
                    tool_durations_ms=[getattr(tr, "duration_ms", 0.0) for tr in tool_results],
                    tool_success=[tr.success for tr in tool_results],
                    input_tokens=_usage.get("input_tokens", 0),
                    output_tokens=_usage.get("output_tokens", 0),
                    wall_time_ms=_turn_duration,
                    findings_count=sum(1 for tr in tool_results if tr.success and tr.result),
                ))

            # Yield results for display update immediately
            display_msg = AgentMessage(
                role="assistant",
                content="",  # Suppress content here as it was already yielded as thinking
                tool_calls=tool_calls,
                tool_results=tool_results,
                usage=response.usage,
            )
            yield display_msg

            # ── Discovery-driven plan expansion ──────────────────────────────────
            _scan_tools = {"nmap", "fscan", "subfinder"}
            for _tr in tool_results:
                if getattr(_tr, "tool_name", "") not in _scan_tools:
                    continue
                if not _tr.success or not _tr.result:
                    continue
                try:
                    import json as _json

                    _scan_data = _json.loads(_tr.result)
                except Exception:
                    continue

                # Extract newly discovered ports not yet mentioned in any plan step
                _existing_plan_text = " ".join(
                    s.description for s in self._task_plan.steps
                ).lower()

                _new_discoveries: list[dict] = []
                for _port_info in _scan_data.get("ports", []):
                    _port = str(_port_info.get("port", ""))
                    _svc = _port_info.get("service", "")
                    # Only care about non-trivial services
                    _HIGH_VALUE = {
                        "http",
                        "https",
                        "mysql",
                        "mssql",
                        "postgresql",
                        "redis",
                        "mongodb",
                        "smb",
                        "ftp",
                        "ssh",
                        "tomcat",
                        "jenkins",
                        "jboss",
                        "rdp",
                        "vnc",
                        "elasticsearch",
                        "memcached",
                    }
                    if _svc.lower() not in _HIGH_VALUE:
                        continue
                    # Skip if already covered (port number appears in some plan step desc)
                    if _port and _port in _existing_plan_text:
                        continue
                    _new_discoveries.append(_port_info)

                if _new_discoveries:
                    _expand_msg = await self._expand_plan(_new_discoveries)
                    if _expand_msg:
                        yield _expand_msg
                        pending_plan_context = True
            # ── End discovery expansion ──────────────────────────────────────────

            # Check for plan failure (Tactical Replanning)
            if (
                hasattr(self._task_plan, "has_failure")
                and self._task_plan.has_failure()
            ):
                # Find the failed step
                failed_step = None
                for s in self._task_plan.steps:
                    if s.status == "fail":
                        failed_step = s
                        break

                if failed_step:
                    await self._handle_failed_plan_step(failed_step)
                    replan_msg = await self._replan(failed_step)
                    if replan_msg:
                        self.conversation_history.append(replan_msg)
                        yield replan_msg

                        # Check if replan indicated impossibility
                        if replan_msg.metadata.get("replan_impossible"):
                            self.state_manager.transition_to(AgentState.COMPLETE)
                            self._export_metrics()
                            return

                        pending_plan_context = True
                        continue

            # Check if plan is now complete
            if self._task_plan.is_complete():
                # All steps done - generate final summary
                summary_response = await self.llm.generate(
                    system_prompt="You are a helpful assistant. Provide a brief, clear summary of what was accomplished.",
                    messages=self._format_messages_for_llm(),
                    tools=[
                        t for t in self.tools if t.enabled
                    ],  # Must provide tools if history contains tool calls
                    task_hint="tool_parse",
                )

                completion_msg = AgentMessage(
                    role="assistant",
                    content=summary_response.content or "Task complete.",
                    usage=summary_response.usage,
                    metadata={"task_complete": True},
                )
                self.conversation_history.append(completion_msg)
                yield completion_msg
                self.state_manager.transition_to(AgentState.COMPLETE)
                self._export_metrics()
                return

            self.state_manager.transition_to(AgentState.THINKING)

        # Max iterations reached - force stop
        warning_msg = AgentMessage(
            role="assistant",
            content=f"[!] Reached maximum iterations ({self.max_iterations}). Stopping to prevent infinite loop. You can continue the conversation if needed.",
            metadata={"max_iterations_reached": True},
        )
        self.conversation_history.append(warning_msg)
        yield warning_msg
        self.state_manager.transition_to(AgentState.COMPLETE)
        self._export_metrics()

    def _export_metrics(self) -> None:
        """Export session metrics to JSON if collector is active."""
        if self._metrics is not None:
            try:
                self._metrics.export_json()
            except Exception:
                pass

    def _format_messages_for_llm(self) -> List[dict]:
        """Format conversation history for LLM."""
        messages = []

        for msg in self.conversation_history:
            if msg.role == "tool_result" and msg.tool_results:
                # Format tool results as tool response messages
                for result in msg.tool_results:
                    messages.append(
                        {
                            "role": "tool",
                            "content": (
                                result.result
                                if result.success
                                else f"Error: {result.error}"
                            ),
                            "tool_call_id": result.tool_call_id,
                        }
                    )
            else:
                messages.append(msg.to_llm_format())

        return messages

    def _parse_arguments(self, tool_call: Any) -> dict:
        """Parse tool call arguments."""
        import json

        if hasattr(tool_call, "function"):
            args = tool_call.function.arguments
        elif isinstance(tool_call, dict):
            args = tool_call.get("arguments", {})
        else:
            args = {}

        if isinstance(args, str):
            try:
                return json.loads(args)
            except json.JSONDecodeError:
                return {"raw": args}
        return args

    async def _execute_single(self, i: int, call: Any) -> ToolResult:
        """Execute a single tool call and return the result."""
        # Extract tool call id, name and arguments
        if hasattr(call, "id"):
            tool_call_id = call.id
        elif isinstance(call, dict) and "id" in call:
            tool_call_id = call["id"]
        else:
            tool_call_id = f"call_{i}"

        if hasattr(call, "function"):
            name = call.function.name
            arguments = self._parse_arguments(call)
        elif isinstance(call, dict):
            name = call.get("name", "")
            arguments = call.get("arguments", {})
        else:
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name="unknown",
                error="Malformed tool call: missing name or function attribute",
                success=False,
            )

        # Phase 4: pre-tool hooks (fire before permission check)
        try:
            hook_result = await self.hooks.fire_pre_tool(name, arguments)
            if not hook_result.allow:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    tool_name=name,
                    error=f"[HOOK BLOCKED] {hook_result.reason}",
                    success=False,
                )
            if hook_result.modified_args:
                arguments = hook_result.modified_args
        except Exception:
            pass

        import time as _time
        _t0 = _time.monotonic()

        tool = self._find_tool(name)

        if tool:
            try:
                # ── Permission check ──────────────────────────────────────────
                perm_result = self.permission_enforcer.check(name, arguments)
                if not perm_result.allowed:
                    _duration_ms = (_time.monotonic() - _t0) * 1000
                    return ToolResult(
                        tool_call_id=tool_call_id,
                        tool_name=name,
                        error=f"[PERMISSION DENIED] {perm_result.reason}",
                        success=False,
                        duration_ms=_duration_ms,
                    )

                # ── Terminal tool → re-route to ToolExecutor ──────────────────
                if tool.name == "terminal" and name != "terminal":
                    if isinstance(arguments, dict) and "command" in arguments:
                        terminal_args = arguments
                    else:
                        cmd_parts = [name]
                        if isinstance(arguments, dict):
                            for k in ("target", "host", "hosts", "hosts_list", "hosts[]"):
                                if k in arguments:
                                    v = arguments[k]
                                    if isinstance(v, (list, tuple)):
                                        cmd_parts.extend([str(x) for x in v])
                                    else:
                                        cmd_parts.append(str(v))
                            for k, v in arguments.items():
                                if k in ("target", "host", "hosts", "hosts_list", "hosts[]"):
                                    continue
                                if v is True:
                                    cmd_parts.append(f"--{k}")
                                elif v is False or v is None:
                                    continue
                                elif isinstance(v, (list, tuple)):
                                    cmd_parts.extend([str(x) for x in v])
                                else:
                                    cmd_parts.append(str(v))
                        elif isinstance(arguments, (list, tuple)):
                            cmd_parts.extend([str(x) for x in arguments])
                        else:
                            cmd_parts.append(str(arguments))

                        arguments = {"command": " ".join(cmd_parts)}

                # ── Unified execution via ToolExecutor ────────────────────────
                exec_result = await self.tool_executor.execute(tool, arguments)
                _duration_ms = (_time.monotonic() - _t0) * 1000

                # Phase 4: post-tool hooks (enrich results, scan for flags/vulns)
                try:
                    post_hook = await self.hooks.fire_post_tool(name, exec_result, _duration_ms)
                    if post_hook.enriched_result:
                        exec_result.result = (exec_result.result or "") + "\n" + post_hook.enriched_result
                    if exec_result.result:
                        self.hooks.scan_for_flags(exec_result.result)
                        self.hooks.scan_for_vulns(exec_result.result, getattr(self, "target", "") or "")
                except Exception:
                    pass

                # Check for RAG optimizer suggested tools
                suggested_tools = None
                if tool.metadata.get("is_rag_optimizer", False):
                    suggested_tools = tool.metadata.get("top_k_tools", {}).get(
                        "retrieved_top_k_tools", None
                    )

                return ToolResult(
                    tool_call_id=tool_call_id,
                    tool_name=name,
                    result=exec_result.result,
                    error=exec_result.error,
                    success=exec_result.success,
                    suggested_tools=suggested_tools,
                    duration_ms=_duration_ms,
                )

            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(
                    "Error executing tool %s: %s", name, e
                )
                try:
                    from flaghunter.session.notifier import notify

                    notify("warning", f"Tool execution failed ({name}): {e}")
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Failed to notify operator about tool execution failure"
                    )
                _duration_ms = (_time.monotonic() - _t0) * 1000
                return ToolResult(
                    tool_call_id=tool_call_id,
                    tool_name=name,
                    error=str(e),
                    success=False,
                    duration_ms=_duration_ms,
                )
        else:
            _duration_ms = (_time.monotonic() - _t0) * 1000
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name=name,
                error=f"Tool '{name}' not found",
                success=False,
                duration_ms=_duration_ms,
            )

    async def _execute_tools(self, tool_calls: List[Any]) -> List[ToolResult]:
        """Execute tool calls concurrently and return all results."""
        tasks = [
            asyncio.ensure_future(self._execute_single(i, call))
            for i, call in enumerate(tool_calls)
        ]
        return list(await asyncio.gather(*tasks))

    def _find_tool(self, name: str) -> Optional["Tool"]:
        """
        Find a tool by name.

        Args:
            name: The tool name to find

        Returns:
            The Tool if found, None otherwise
        """
        for tool in self.tools + self.suggested_tools:
            if tool.name == name:
                return tool
        # Fallback: if tool not found, attempt to use a generic terminal tool
        # for commands. Some LLMs may emit semantic tool names (e.g. "network_scan")
        # instead of the actual registered tool name. Use the `terminal` tool
        # as a best-effort fallback when available.
        for tool in self.tools:
            if tool.name == "terminal":
                return tool
        return None

    def _can_finish(self) -> tuple[bool, str]:
        """Check if the agent can finish based on plan completion."""
        if len(self._task_plan.steps) == 0:
            return True, "No plan exists"

        pending = self._task_plan.get_pending_steps()
        if pending:
            pending_desc = ", ".join(
                f"Step {s.id}: {s.description}" for s in pending[:3]
            )
            more = f" (+{len(pending) - 3} more)" if len(pending) > 3 else ""
            return False, f"Incomplete: {pending_desc}{more}"

        return True, "All steps complete"

    async def _prepare_context(self) -> None:
        """Hook called once before the agent loop starts.

        Subclasses override this to set up mode-specific context (CTF detection,
        runtime fingerprinting, etc.) before the first LLM call.
        """
        return

    async def _auto_generate_plan(self) -> Optional[AgentMessage]:
        """
        Automatically generate a plan from the user's request (loop-enforced).

        This is called on iteration 1 to force plan creation before any tool execution.
        Uses function calling for reliable structured output.

        Returns:
            AgentMessage with plan display, or None if generation fails
        """
        from ..tools.finish import PlanStep
        from ..tools.registry import Tool, ToolSchema

        # Get the user's original request (last message)
        user_request = ""
        for msg in reversed(self.conversation_history):
            if msg.role == "user":
                user_request = msg.content
                break

        if not user_request:
            return None  # No request to plan

        # Create a temporary tool for plan generation (function calling)
        plan_generator_tool = Tool(
            name="create_plan",
            description="Create a step-by-step plan for the task. Call this with the steps needed.",
            schema=ToolSchema(
                properties={
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of actionable steps (one tool action each)",
                    },
                },
                required=["steps"],
            ),
            execute_fn=lambda args, runtime: None,  # Dummy - we parse args directly
            category="planning",
        )

        plan_prompt = f"""Break this request into minimal, actionable steps.

Request: {user_request}

Guidelines:
- Be concise (typically 2-4 steps)
- One tool action per step
- Don't include waiting/loading (handled automatically)
- Do NOT include a "finish", "complete", or "verify" step (handled automatically)

Call the create_plan tool with your steps."""

        try:
            response = await self.llm.generate(
                system_prompt="You are a task planning assistant. Always use the create_plan tool.",
                messages=[{"role": "user", "content": plan_prompt}],
                tools=[plan_generator_tool],
                task_hint="planning",
            )

            # Extract steps from tool call arguments
            steps = []
            if response.tool_calls:
                for tc in response.tool_calls:
                    args = self._parse_arguments(tc)
                    if args.get("steps"):
                        steps = args["steps"]
                        break

            # Fallback: if LLM didn't provide steps, create single-step plan
            if not steps:
                steps = [user_request]

            # Create the plan
            self._task_plan.original_request = user_request
            self._task_plan.steps = [
                PlanStep(id=i + 1, description=str(step).strip())
                for i, step in enumerate(steps)
            ]

            # Add a system message showing the generated plan
            plan_display = ["Plan:"]
            for step in self._task_plan.steps:
                plan_display.append(f"  {step.id}. {step.description}")

            plan_msg = AgentMessage(
                role="assistant",
                content="\n".join(plan_display),
                metadata={"auto_plan": True},
                usage=response.usage,
            )
            self.conversation_history.append(plan_msg)
            return plan_msg

        except Exception as e:
            # Plan generation failed - create fallback single-step plan
            self._task_plan.original_request = user_request
            self._task_plan.steps = [PlanStep(id=1, description=user_request)]

            error_msg = AgentMessage(
                role="assistant",
                content=f"Plan generation failed: {str(e)}\nUsing fallback: treating request as single step.",
                metadata={"auto_plan_failed": True},
            )
            self.conversation_history.append(error_msg)
            return error_msg
            return error_msg

    async def _replan(self, failed_step: Any) -> Optional[AgentMessage]:
        """
        Handle plan failure by generating a new plan (Tactical Replanning).
        """
        from ..tools.finish import PlanStep
        from ..tools.registry import Tool, ToolSchema

        # 1. Archive current plan (log it)
        old_plan_str = "\n".join(
            [f"{s.id}. {s.description} ({s.status})" for s in self._task_plan.steps]
        )

        # 2. Generate new plan
        # Create a temporary tool for plan generation
        plan_generator_tool = Tool(
            name="create_plan",
            description="Create a NEW step-by-step plan. Call this with the steps needed.",
            schema=ToolSchema(
                properties={
                    "feasible": {
                        "type": "boolean",
                        "description": "Can the task be completed with a new plan? Set false if impossible/out-of-scope.",
                    },
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of actionable steps (required if feasible=true).",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for the new plan OR reason why it's impossible.",
                    },
                },
                required=["feasible", "reason"],
            ),
            execute_fn=lambda args, runtime: None,
            category="planning",
        )

        replan_prompt = f"""The previous plan failed at step {failed_step.id}.

Failed Step: {failed_step.description}
Reason: {failed_step.result}

Previous Plan:
{old_plan_str}

Original Request: {self._task_plan.original_request}

Task: Generate a NEW plan (v2) that addresses this failure.
- If the failure invalidates the entire approach, try a different tactical approach.
- If the task is IMPOSSIBLE or OUT OF SCOPE (e.g., requires installing software on a remote target, physical access, or permissions you don't have), set feasible=False.
- Do NOT propose steps that violate standard pentest constraints (no installing agents/services on targets unless exploited).

Call create_plan with the new steps OR feasible=False."""

        try:
            response = await self.llm.generate(
                system_prompt="You are a tactical planning assistant. The previous plan failed. Create a new one or declare it impossible.",
                messages=[{"role": "user", "content": replan_prompt}],
                tools=[plan_generator_tool],
                task_hint="planning",
            )

            # Extract steps
            steps = []
            feasible = True
            reason = ""

            if response.tool_calls:
                for tc in response.tool_calls:
                    args = self._parse_arguments(tc)
                    feasible = args.get("feasible", True)
                    reason = args.get("reason", "")
                    if feasible and args.get("steps"):
                        steps = args["steps"]
                    break

            if not feasible:
                return AgentMessage(
                    role="assistant",
                    content=f"Task determined to be infeasible after failure.\nReason: {reason}",
                    metadata={"replan_impossible": True},
                )

            if not steps:
                return None

            # Update plan
            self._task_plan.steps = [
                PlanStep(id=i + 1, description=str(step).strip())
                for i, step in enumerate(steps)
            ]

            # Return message
            plan_display = [f"Plan v2 (Replanned) - {reason}:"]
            for step in self._task_plan.steps:
                plan_display.append(f"  {step.id}. {step.description}")

            return AgentMessage(
                role="assistant",
                content="\n".join(plan_display),
                metadata={"replanned": True},
            )

        except Exception as e:
            return AgentMessage(
                role="assistant",
                content=f"Replanning failed: {str(e)}",
                metadata={"replan_failed": True},
            )

    async def _expand_plan(
        self, discoveries: list[dict]
    ) -> Optional[AgentMessage]:
        """
        Append new steps to the current plan based on newly found services/ports.
        Only called when scan results reveal targets not yet covered by the plan.

        discoveries: list of dicts like
          [{"port": 8080, "service": "http", "product": "Tomcat"},
           {"port": 3306, "service": "mysql", "product": "MySQL"}]
        """
        from ..tools.finish import PlanStep

        if not discoveries:
            return None

        # Describe what we already have in the plan
        existing = "\n".join(
            f"  {s.id}. {s.description}" for s in self._task_plan.steps
        )

        discovery_text = "\n".join(
            f"  - port {d.get('port')}/{d.get('service', '?')}"
            f" ({d.get('product', '')} {d.get('version', '')})".strip()
            for d in discoveries
        )

        expand_prompt = f"""New services were discovered that are NOT yet covered by the plan:

{discovery_text}

Existing plan:
{existing}

For each newly discovered service, propose 1-2 additional steps.
Respond ONLY as JSON array of step description strings, e.g.:
["Enumerate MySQL on port 3306", "Test web app on port 8080 with dirscan"]
Output only the JSON array, no other text."""

        try:
            response = await self.llm.generate(
                system_prompt="You are a penetration test planning assistant. Output only a JSON array.",
                messages=[{"role": "user", "content": expand_prompt}],
                tools=[],
                task_hint="planning",
            )
            content = (response.content or "").strip()
            # parse JSON array
            import json as _json

            new_steps_raw = _json.loads(content)
            if not isinstance(new_steps_raw, list):
                return None
            new_steps_raw = [
                s for s in new_steps_raw if isinstance(s, str) and s.strip()
            ]
            if not new_steps_raw:
                return None
        except Exception:
            return None

        # Append to current plan (IDs continue from last existing)
        start_id = max((s.id for s in self._task_plan.steps), default=0) + 1
        added = []
        for i, desc in enumerate(new_steps_raw):
            step = PlanStep(id=start_id + i, description=desc.strip())
            self._task_plan.steps.append(step)
            added.append(step)

        display = ["Plan expanded (new discoveries):"] + [
            f"  {s.id}. {s.description}" for s in added
        ]
        msg = AgentMessage(
            role="assistant",
            content="\n".join(display),
            metadata={"plan_expanded": True, "added_steps": len(added)},
        )
        self.conversation_history.append(msg)
        return msg

    async def _handle_failed_plan_step(self, failed_step: Any) -> None:
        """Optional subclass hook invoked before tactical replanning."""
        return None

    async def _handle_tool_results(self, tool_results: List[ToolResult]) -> None:
        """Optional subclass hook invoked after agent-mode tool execution."""
        return None

    def reset(self):
        """Reset the agent state for a new conversation."""
        self.state_manager.reset()
        self.conversation_history.clear()

    def add_tools(self, tools: List["Tool"]):
        self.tools.extend(tools)

    def delete_tools(self, tools: List["Tool"]):
        """
        Remove tools from the agent by name.

        Args:
            tools: List of tool names to remove
        """
        self.tools = [
            t for t in self.tools if t.name not in [tool.name for tool in tools]
        ]

    def get_tools(self) -> List["Tool"]:
        retVal: List[Tool] = []
        for tool in self.tools:
            if tool.metadata.get(
                "is_rag_optimizer", False
            ):  # Expand tools if we are using the RAG optimizer, so all the tools are listed (although, the only exposed tool is the RAG optimizer tool)
                suggested_tools = tool.metadata.get("total_tools_indexed", [])
                retVal += suggested_tools
            else:
                retVal.append(tool)
        return retVal

    # Helper function to avoid duplicates
    def deduplicate_suggested_tools(self):
        # Deduplicate the same tools
        seen = set()
        deduped = []
        for tool in self.suggested_tools:
            if id(tool) not in seen:
                seen.add(id(tool))
                deduped.append(tool)
        self.suggested_tools = deduped

    async def _assist_loop(self) -> AsyncIterator[AgentMessage]:
        """Single LLM call + one tool round on the existing conversation history."""
        assist_tools = [t for t in self.tools if t.name != "finish" and t.enabled]

        response = await self.llm.generate(
            system_prompt=self.get_system_prompt(mode="assist"),
            messages=self._format_messages_for_llm(),
            tools=assist_tools + self.suggested_tools,
            task_hint="default",
        )

        if response.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id if hasattr(tc, "id") else str(i),
                    name=(
                        tc.function.name
                        if hasattr(tc, "function")
                        else tc.get("name", "")
                    ),
                    arguments=self._parse_arguments(tc),
                )
                for i, tc in enumerate(response.tool_calls)
            ]

            if response.content:
                thinking_msg = AgentMessage(
                    role="assistant",
                    content=response.content,
                    metadata={"intermediate": True},
                )
                yield thinking_msg

            self.state_manager.transition_to(AgentState.EXECUTING)
            tool_results = await self._execute_tools(response.tool_calls)

            for tool_result in tool_results:
                if tool_result.suggested_tools:
                    self.suggested_tools += tool_result.suggested_tools
                    self.deduplicate_suggested_tools()

            total_tools = len(assist_tools) + len(self.suggested_tools)
            if total_tools > _TOOL_LIMIT:
                allowed_suggested = max(0, _TOOL_LIMIT - len(assist_tools))
                self.suggested_tools = (
                    self.suggested_tools[-allowed_suggested:]
                    if allowed_suggested > 0
                    else []
                )

            assistant_msg = AgentMessage(
                role="assistant", content=response.content or "", tool_calls=tool_calls
            )
            self.conversation_history.append(assistant_msg)
            self.conversation_history.append(
                AgentMessage(role="tool_result", content="", tool_results=tool_results)
            )

            yield AgentMessage(
                role="assistant",
                content="",
                tool_calls=tool_calls,
                tool_results=tool_results,
            )

            result_text = self._format_tool_results(tool_results)
            final_msg = AgentMessage(role="assistant", content=result_text)
            self.conversation_history.append(final_msg)
            yield final_msg
        else:
            assistant_msg = AgentMessage(
                role="assistant", content=response.content or ""
            )
            self.conversation_history.append(assistant_msg)
            yield assistant_msg

        self.state_manager.transition_to(AgentState.COMPLETE)

    async def assist(self, message: str) -> AsyncIterator[AgentMessage]:
        """
        Assist mode - single LLM call, single tool execution if needed.

        Simple flow: LLM responds, optionally calls one tool, returns result.
        No looping, no retries. User can follow up if needed.

        Note: 'finish' tool is excluded - assist mode doesn't need explicit
        termination since it's single-shot by design.

        Args:
            message: The user message to respond to

        Yields:
            AgentMessage objects
        """
        self.state_manager.transition_to(AgentState.THINKING)
        self.conversation_history.append(AgentMessage(role="user", content=message))
        async for msg in self._assist_loop():
            yield msg

    async def _interact_loop(self) -> AsyncIterator[AgentMessage]:
        """Streaming chat loop on the existing conversation history."""
        while True:
            interact_tools = [t for t in self.tools if t.name != "finish" and t.enabled]

            response = await self.llm.generate(
                system_prompt=self.get_system_prompt(mode="interact"),
                messages=self._format_messages_for_llm(),
                tools=interact_tools + self.suggested_tools,
                task_hint="default",
            )

            if response.tool_calls:
                tool_calls = [
                    ToolCall(
                        id=tc.id if hasattr(tc, "id") else str(i),
                        name=(
                            tc.function.name
                            if hasattr(tc, "function")
                            else tc.get("name", "")
                        ),
                        arguments=self._parse_arguments(tc),
                    )
                    for i, tc in enumerate(response.tool_calls)
                ]

                assistant_msg = AgentMessage(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=tool_calls,
                )
                self.conversation_history.append(assistant_msg)
                yield assistant_msg

                self.state_manager.transition_to(AgentState.EXECUTING)

                tasks = [
                    asyncio.ensure_future(self._execute_single(i, tc))
                    for i, tc in enumerate(response.tool_calls)
                ]

                all_tool_results = []
                for coro in asyncio.as_completed(tasks):
                    tool_result = await coro
                    all_tool_results.append(tool_result)

                    if tool_result.suggested_tools:
                        self.suggested_tools += tool_result.suggested_tools
                        self.deduplicate_suggested_tools()

                    yield AgentMessage(
                        role="tool_result",
                        content="",
                        tool_results=[tool_result],
                    )

                total_tools = len(interact_tools) + len(self.suggested_tools)
                if total_tools > _TOOL_LIMIT:
                    allowed_suggested = max(0, _TOOL_LIMIT - len(interact_tools))
                    self.suggested_tools = (
                        self.suggested_tools[-allowed_suggested:]
                        if allowed_suggested > 0
                        else []
                    )

                self.conversation_history.append(
                    AgentMessage(
                        role="tool_result", content="", tool_results=all_tool_results
                    )
                )

            else:
                assistant_msg = AgentMessage(
                    role="assistant", content=response.content or ""
                )
                self.conversation_history.append(assistant_msg)
                yield assistant_msg

            finish_reason = getattr(response, "finish_reason", None)
            if finish_reason in ("length", "stop"):
                break

        self.state_manager.transition_to(AgentState.COMPLETE)

    async def interact(self, message: str) -> AsyncIterator[AgentMessage]:
        """
        Interactive mode

        Args:
            message: The user message to respond to

        Yields:
            AgentMessage objects
        """
        self.state_manager.transition_to(AgentState.THINKING)
        self.conversation_history.append(AgentMessage(role="user", content=message))
        async for msg in self._interact_loop():
            yield msg

    async def run_mcp(self, task: str) -> AsyncIterator["AgentMessage"]:
        """
        MCP autonomous execution loop.

        Purpose-built for programmatic callers (MCP server, orchestrating agents).
        Differences from interact():
        - Uses pa_mcp system prompt (dense, structured, no conversational filler)
        - Never stalls waiting for human confirmation
        - Terminates cleanly on natural stop (finish_reason == 'stop' with no tools)
        - No finish/plan tool dependency — lifecycle owned by the MCP layer
        - Saves findings via notes tool; final message is the structured summary

        Yields AgentMessage objects. The MCP driver (_drive_mcp) maps these to
        AgentEntry fields for retrieval via get_agent_result().

        Args:
            task: The fully-specified task string from the MCP caller.

        Yields:
            AgentMessage objects throughout execution.
        """
        self.reset()
        self.state_manager.transition_to(AgentState.THINKING)
        self.conversation_history.append(AgentMessage(role="user", content=task))

        # Exclude finish tool — MCP layer owns lifecycle, not the agent
        mcp_tools = [t for t in self.tools if t.name != "finish" and t.enabled]

        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1

            response = await self.llm.generate(
                system_prompt=self.get_system_prompt(mode="mcp"),
                messages=self._format_messages_for_llm(),
                tools=mcp_tools + self.suggested_tools,
            )

            # ── finish_reason: break early if LLM signals done or context full ──
            finish_reason = getattr(response, "finish_reason", None)
            if finish_reason == "length":
                break
            elif finish_reason == "stop" and not response.tool_calls:
                pass

            # ── Empty response ────────────────────────────────────────────────
            if not response.tool_calls and not response.content:
                empty_msg = AgentMessage(
                    role="assistant",
                    content="[mcp] Agent returned empty response. Stopping.",
                    metadata={"empty_response": True},
                )
                self.conversation_history.append(empty_msg)
                yield empty_msg
                self.state_manager.transition_to(AgentState.COMPLETE)
                return

            # ── Natural stop: text response with no tool calls ────────────────
            # Unlike interact(), we treat this as DONE — MCP tasks are
            # self-contained. The final text is the structured summary.
            if not response.tool_calls:
                final_msg = AgentMessage(
                    role="assistant",
                    content=response.content or "",
                    usage=response.usage,
                    metadata={"task_complete": True},
                )
                self.conversation_history.append(final_msg)
                yield final_msg
                self.state_manager.transition_to(AgentState.COMPLETE)
                return

            # ── Tool execution ────────────────────────────────────────────────
            self.state_manager.transition_to(AgentState.EXECUTING)

            # Yield thinking content before executing (if present)
            if response.content:
                thinking_msg = AgentMessage(
                    role="assistant",
                    content=response.content,
                    usage=response.usage,
                    metadata={"intermediate": True},
                )
                yield thinking_msg

            tool_calls = [
                ToolCall(
                    id=tc.id if hasattr(tc, "id") else str(i),
                    name=(
                        tc.function.name
                        if hasattr(tc, "function")
                        else tc.get("name", "")
                    ),
                    arguments=self._parse_arguments(tc),
                )
                for i, tc in enumerate(response.tool_calls)
            ]

            tool_results = await self._execute_tools(response.tool_calls)

            # Inject RAG-suggested tools if any tool returned them
            for tool_result in tool_results:
                if tool_result.suggested_tools:
                    self.suggested_tools += tool_result.suggested_tools
                    self.deduplicate_suggested_tools()

            # Enforce tool cap
            total_tools = len(mcp_tools) + len(self.suggested_tools)
            if total_tools > _TOOL_LIMIT:
                allowed = max(0, _TOOL_LIMIT - len(mcp_tools))
                self.suggested_tools = (
                    self.suggested_tools[-allowed:] if allowed > 0 else []
                )

            # Record in conversation history
            assistant_msg = AgentMessage(
                role="assistant",
                content=response.content or "",
                tool_calls=tool_calls,
                usage=response.usage,
            )
            self.conversation_history.append(assistant_msg)
            self.conversation_history.append(
                AgentMessage(role="tool_result", content="", tool_results=tool_results)
            )

            # Yield for the MCP driver to record
            yield AgentMessage(
                role="assistant",
                content="",
                tool_calls=tool_calls,
                tool_results=tool_results,
                usage=response.usage,
            )

            self.state_manager.transition_to(AgentState.THINKING)

        # ── Max iterations reached ────────────────────────────────────────────
        # Ask the LLM for a partial-results summary before stopping
        try:
            summary_response = await self.llm.generate(
                system_prompt=(
                    "You are a penetration testing assistant. "
                    "The task ran out of iterations before completing. "
                    "Summarize what was accomplished and what remains."
                ),
                messages=self._format_messages_for_llm(),
                tools=[],  # No tools — we need text output, not tool calls
                task_hint="tool_parse",
            )
            summary_content = (
                summary_response.content
                or "Max iterations reached — no summary available."
            )
        except Exception:
            summary_content = f"[mcp] Max iterations ({self.max_iterations}) reached. Partial results in notes."

        max_iter_msg = AgentMessage(
            role="assistant",
            content=summary_content,
            metadata={"max_iterations_reached": True, "task_complete": True},
        )
        self.conversation_history.append(max_iter_msg)
        yield max_iter_msg
        self.state_manager.transition_to(AgentState.COMPLETE)

    def save_session(self) -> str | None:
        """Save current agent state to the injected session store.

        The SESSION layer (AgentSession / initialize_session) injects
        ``_session_store`` when persistence is wanted. Without an injected
        store this degrades to a no-op instead of reaching UP into the SESSION
        layer to self-construct one (invariant I1: ORCHESTRATION must not
        import the SESSION facade).
        """
        if self._session_store is None:
            return None
        try:
            self._session_id = self._session_store.save(self, session_id=self._session_id)
            return self._session_id
        except Exception:
            return None

    def resume_session(self, session_id: str) -> bool:
        """Restore agent state from a saved session (no-op if no store injected)."""
        if self._session_store is None:
            return False
        ok = self._session_store.resume(self, session_id)
        if ok:
            self._session_id = session_id
        return ok

    def list_saved_sessions(self) -> list[dict]:
        """List saved sessions, newest first (empty if no store injected)."""
        if self._session_store is None:
            return []
        return self._session_store.list_sessions()

    def _format_tool_results(self, results: List[ToolResult]) -> str:
        """Format tool results as a simple response."""
        parts = []
        for r in results:
            if r.success:
                parts.append(r.result or "Done.")
            else:
                parts.append(f"Error: {r.error}")
        return "\n".join(parts)

    def get_state(self) -> AgentState:
        return self.state_manager.current_state

    def cleanup_after_cancel(self) -> None:
        """
        Clean up agent state after a cancellation.

        Removes the cancelled request and any pending tool calls from
        conversation history to prevent stale responses from contaminating
        the next conversation.
        """
        # Remove incomplete messages from the end of conversation
        while self.conversation_history:
            last_msg = self.conversation_history[-1]
            # Remove assistant message with tool calls (incomplete tool execution)
            if last_msg.role == "assistant" and last_msg.tool_calls:
                self.conversation_history.pop()
            # Remove orphaned tool_result messages
            elif last_msg.role == "tool":
                self.conversation_history.pop()
            # Remove the user message that triggered the cancelled request
            elif last_msg.role == "user":
                self.conversation_history.pop()
                break  # Stop after removing the user message
            else:
                break

        # Reset state to idle
        self.state_manager.transition_to(AgentState.IDLE)
