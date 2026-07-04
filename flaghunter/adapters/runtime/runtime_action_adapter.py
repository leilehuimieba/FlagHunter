"""Runtime action adapter skeletons."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.ports import RuntimeActionPort


class RuntimeActionAdapter:
    """Delegate runtime actions through an injected runtime action port."""

    def __init__(self, runtime: RuntimeActionPort) -> None:
        self._runtime = runtime

    async def run_command(
        self,
        command: str,
        *,
        timeout_seconds: float | None = None,
    ) -> Mapping[str, Any]:
        return await self._runtime.run_command(
            command,
            timeout_seconds=timeout_seconds,
        )
