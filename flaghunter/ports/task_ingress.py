"""Task ingress boundary contracts."""

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class TaskIngressPort(Protocol):
    async def submit_task(
        self,
        request: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...
