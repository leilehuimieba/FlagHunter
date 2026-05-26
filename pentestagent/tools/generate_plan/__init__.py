"""Optional plan-generation tool — LLM decides when to create a plan."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..finish import PlanStep
from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


@register_tool(
    name="generate_plan",
    description=(
        "Create a step-by-step plan for the current task. "
        "Use this when the task is complex and you want to track progress "
        "through explicit steps. Each step should describe one concrete tool action. "
        "After creating a plan, mark steps complete/skip/fail with the finish tool."
    ),
    schema=ToolSchema(
        properties={
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of actionable steps (one tool action per step, 2-6 steps typical)",
            },
        },
        required=["steps"],
    ),
    category="planning",
)
async def generate_plan(arguments: dict, runtime: "Runtime") -> str:
    """Create a plan from LLM-provided step descriptions."""
    plan = getattr(runtime, "plan", None)
    if plan is None:
        return "Error: no plan object available on runtime"

    steps_raw = arguments.get("steps", [])
    if not steps_raw:
        return "Error: 'steps' must be a non-empty list of step descriptions"

    plan.steps.clear()
    for i, desc in enumerate(steps_raw, 1):
        plan.steps.append(PlanStep(id=i, description=str(desc)))

    lines = [f"Plan created with {len(plan.steps)} steps:"]
    for step in plan.steps:
        lines.append(f"  {step.id}. {step.description}")
    return "\n".join(lines)
