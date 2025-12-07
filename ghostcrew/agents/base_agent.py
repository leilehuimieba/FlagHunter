"""Base agent class for GhostCrew."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator, List, Optional

from ..config.constants import DEFAULT_MAX_ITERATIONS
from .state import AgentState, AgentStateManager

if TYPE_CHECKING:
    from ..llm import LLM
    from ..runtime import Runtime
    from ..tools import Tool


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""

    id: str
    name: str
    arguments: dict


@dataclass
class ToolResult:
    """Result from a tool execution."""

    tool_call_id: str
    tool_name: str
    result: Optional[str] = None
    error: Optional[str] = None
    success: bool = True


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


class BaseAgent(ABC):
    """Base class for all agents."""

    def __init__(
        self,
        llm: "LLM",
        tools: List["Tool"],
        runtime: "Runtime",
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ):
        """
        Initialize the base agent.

        Args:
            llm: The LLM instance for generating responses
            tools: List of tools available to the agent
            runtime: The runtime environment for tool execution
            max_iterations: Maximum iterations before forcing stop (safety limit)
        """
        self.llm = llm
        self.tools = tools
        self.runtime = runtime
        self.max_iterations = max_iterations
        self.state_manager = AgentStateManager()
        self.conversation_history: List[AgentMessage] = []

    @property
    def state(self) -> AgentState:
        """Get current agent state."""
        return self.state_manager.current_state

    @state.setter
    def state(self, value: AgentState):
        """Set agent state."""
        self.state_manager.transition_to(value)

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

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        pass

    async def agent_loop(self, initial_message: str) -> AsyncIterator[AgentMessage]:
        """
        Main agent execution loop.

        Simple control flow:
        - Tool calls: Execute tools, continue loop
        - Text response (no tools): Done
        - Max iterations reached: Force stop with warning

        Args:
            initial_message: The initial user message to process

        Yields:
            AgentMessage objects as the agent processes
        """
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

    async def _run_loop(self) -> AsyncIterator[AgentMessage]:
        """
        Core agent loop logic - shared by agent_loop and continue_conversation.

        Termination conditions:
        1. finish tool is called -> clean exit with summary
        2. max_iterations reached -> forced exit with warning
        3. error -> exit with error state

        Text responses WITHOUT tool calls are treated as "thinking out loud"
        and do NOT terminate the loop. This prevents premature stopping.

        Yields:
            AgentMessage objects as the agent processes
        """
        from ..tools.completion import extract_completion_summary, is_task_complete

        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1

            response = await self.llm.generate(
                system_prompt=self.get_system_prompt(),
                messages=self._format_messages_for_llm(),
                tools=self.tools,
            )

            if response.tool_calls:
                # Build tool calls list FIRST (before execution)
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

                # Yield early - show tool calls before execution starts
                early_msg = AgentMessage(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=tool_calls,
                    tool_results=[],  # No results yet
                    usage=response.usage,
                )
                yield early_msg

                # Now execute tools
                self.state_manager.transition_to(AgentState.EXECUTING)
                tool_results = await self._execute_tools(response.tool_calls)

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

                # Check for explicit task_complete signal
                for result in tool_results:
                    if result.success and result.result and is_task_complete(result.result):
                        summary = extract_completion_summary(result.result)
                        # Yield results with completion summary
                        display_msg = AgentMessage(
                            role="assistant",
                            content=summary,
                            tool_calls=tool_calls,
                            tool_results=tool_results,
                            usage=response.usage,
                            metadata={"task_complete": True},
                        )
                        yield display_msg
                        self.state_manager.transition_to(AgentState.COMPLETE)
                        return

                # Yield results for display update (no completion yet)
                display_msg = AgentMessage(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    usage=response.usage,
                )
                yield display_msg
                self.state_manager.transition_to(AgentState.THINKING)
            else:
                # Text response WITHOUT tool calls = thinking/intermediate output
                # Store it but DON'T terminate - wait for task_complete
                if response.content:
                    thinking_msg = AgentMessage(
                        role="assistant",
                        content=response.content,
                        usage=response.usage,
                        metadata={"intermediate": True},
                    )
                    self.conversation_history.append(thinking_msg)
                    yield thinking_msg
                # Continue loop - only task_complete or max_iterations stops us

        # Max iterations reached - force stop
        warning_msg = AgentMessage(
            role="assistant",
            content=f"[!] Reached maximum iterations ({self.max_iterations}). Stopping to prevent infinite loop. You can continue the conversation if needed.",
            metadata={"max_iterations_reached": True},
        )
        self.conversation_history.append(warning_msg)
        yield warning_msg
        self.state_manager.transition_to(AgentState.COMPLETE)

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

    async def _execute_tools(self, tool_calls: List[Any]) -> List[ToolResult]:
        """
        Execute tool calls and return results.

        Args:
            tool_calls: List of tool calls from the LLM

        Returns:
            List of ToolResult objects
        """
        results = []

        for i, call in enumerate(tool_calls):
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
                continue

            tool = self._find_tool(name)

            if tool:
                try:
                    result = await tool.execute(arguments, self.runtime)
                    results.append(
                        ToolResult(
                            tool_call_id=tool_call_id,
                            tool_name=name,
                            result=result,
                            success=True,
                        )
                    )
                except Exception as e:
                    results.append(
                        ToolResult(
                            tool_call_id=tool_call_id,
                            tool_name=name,
                            error=str(e),
                            success=False,
                        )
                    )
            else:
                results.append(
                    ToolResult(
                        tool_call_id=tool_call_id,
                        tool_name=name,
                        error=f"Tool '{name}' not found",
                        success=False,
                    )
                )

        return results

    def _find_tool(self, name: str) -> Optional["Tool"]:
        """
        Find a tool by name.

        Args:
            name: The tool name to find

        Returns:
            The Tool if found, None otherwise
        """
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def reset(self):
        """Reset the agent state for a new conversation."""
        self.state_manager.reset()
        self.conversation_history.clear()

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

        # Filter out 'finish' tool - not needed for single-shot assist mode
        assist_tools = [t for t in self.tools if t.name != "finish"]

        # Single LLM call with tools available
        response = await self.llm.generate(
            system_prompt=self.get_system_prompt(),
            messages=self._format_messages_for_llm(),
            tools=assist_tools,
        )

        # If LLM wants to use tools, execute and return result
        if response.tool_calls:
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

            # Yield tool calls IMMEDIATELY (before execution) for UI display
            # Include any thinking/planning content from the LLM
            thinking_msg = AgentMessage(
                role="assistant", content=response.content or "", tool_calls=tool_calls
            )
            yield thinking_msg

            # NOW execute the tools (this can take a while)
            self.state_manager.transition_to(AgentState.EXECUTING)
            tool_results = await self._execute_tools(response.tool_calls)

            # Store in history (minimal content to save tokens)
            assistant_msg = AgentMessage(
                role="assistant", content="", tool_calls=tool_calls
            )
            self.conversation_history.append(assistant_msg)

            tool_result_msg = AgentMessage(
                role="tool_result", content="", tool_results=tool_results
            )
            self.conversation_history.append(tool_result_msg)

            # Yield tool results for display
            results_msg = AgentMessage(
                role="assistant", content="", tool_results=tool_results
            )
            yield results_msg

            # Format tool results as final response
            result_text = self._format_tool_results(tool_results)
            final_msg = AgentMessage(role="assistant", content=result_text)
            self.conversation_history.append(final_msg)
            yield final_msg
        else:
            # Direct response, no tools needed
            assistant_msg = AgentMessage(
                role="assistant", content=response.content or ""
            )
            self.conversation_history.append(assistant_msg)
            yield assistant_msg

        self.state_manager.transition_to(AgentState.COMPLETE)

    def _format_tool_results(self, results: List[ToolResult]) -> str:
        """Format tool results as a simple response."""
        parts = []
        for r in results:
            if r.success:
                parts.append(r.result or "Done.")
            else:
                parts.append(f"Error: {r.error}")
        return "\n".join(parts)
