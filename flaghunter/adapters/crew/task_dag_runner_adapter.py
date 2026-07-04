"""Task graph runner adapter skeletons."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.ports import TaskDAGRunnerPort


class TaskDAGRunnerAdapter:
    """Delegate ready task execution through an injected task graph runner port."""

    def __init__(self, runner: TaskDAGRunnerPort) -> None:
        self._runner = runner

    async def run_ready_task(
        self,
        plan: Mapping[str, Any],
        state_snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return await self._runner.run_ready_task(plan, state_snapshot)
