"""Task completion tool for GhostCrew agent loop control."""

from ..registry import ToolSchema, register_tool

# Sentinel value to signal task completion
TASK_COMPLETE_SIGNAL = "__TASK_COMPLETE__"


@register_tool(
    name="finish",
    description="Signal that the current task is finished. Call this when you have completed ALL steps of the user's request. Include a concise summary of what was accomplished.",
    schema=ToolSchema(
        properties={
            "summary": {
                "type": "string",
                "description": "Brief summary of what was accomplished and any key findings",
            },
        },
        required=["summary"],
    ),
    category="control",
)
async def finish(arguments: dict, runtime) -> str:
    """
    Signal task completion to the agent framework.

    This tool is called by the agent when it has finished all steps
    of the user's task. The framework uses this as an explicit
    termination signal rather than relying on LLM text output.

    Args:
        arguments: Dictionary with 'summary' key
        runtime: The runtime environment (unused)

    Returns:
        The completion signal with summary
    """
    summary = arguments.get("summary", "Task completed.")
    # Return special signal that the framework recognizes
    return f"{TASK_COMPLETE_SIGNAL}:{summary}"


def is_task_complete(result: str) -> bool:
    """Check if a tool result signals task completion."""
    return result.startswith(TASK_COMPLETE_SIGNAL)


def extract_completion_summary(result: str) -> str:
    """Extract the summary from a task_complete result."""
    if is_task_complete(result):
        return result[len(TASK_COMPLETE_SIGNAL) + 1:]  # +1 for the colon
    return result
