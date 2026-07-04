"""Tool execution boundary contracts."""

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class ToolRunnerPort(Protocol):
    async def run_tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...
