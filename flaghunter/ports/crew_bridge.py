"""Worker and task graph boundary contracts."""

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class CrewBridgePort(Protocol):
    async def dispatch_task(
        self,
        request: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...


@runtime_checkable
class TaskDAGRunnerPort(Protocol):
    async def run_ready_task(
        self,
        plan: Mapping[str, Any],
        state_snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...
