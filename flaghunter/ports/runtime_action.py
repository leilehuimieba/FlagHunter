"""Runtime action boundary contracts."""

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class RuntimeActionPort(Protocol):
    async def run_command(
        self,
        command: str,
        *,
        timeout_seconds: float | None = None,
    ) -> Mapping[str, Any]:
        ...
