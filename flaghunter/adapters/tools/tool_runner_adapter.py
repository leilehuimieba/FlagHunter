"""Tool runner adapter skeletons."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.ports import ToolRunnerPort


class ToolRunnerAdapter:
    """Delegate tool runs through an injected tool runner port."""

    def __init__(self, runner: ToolRunnerPort) -> None:
        self._runner = runner

    async def run_tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return await self._runner.run_tool(name, arguments)
