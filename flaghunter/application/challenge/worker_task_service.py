"""Dispatch neutral worker tasks through injected ports."""

from __future__ import annotations

from flaghunter.domain.challenge.contracts._serialization import JsonValue, coerce_json_dict
from flaghunter.ports.crew_bridge import CrewBridgePort


SCHEMA_VERSION = 1


class DispatchWorkerTask:
    def __init__(self, *, crew_bridge: CrewBridgePort | None = None) -> None:
        self._crew_bridge = crew_bridge

    async def dispatch(
        self,
        *,
        task_id: str,
        task_type: str,
        instructions: str,
        run_id: str | None = None,
        metadata: dict[str, JsonValue] | None = None,
    ) -> dict[str, JsonValue]:
        request = {
            "schemaVersion": SCHEMA_VERSION,
            "taskId": task_id,
            "taskType": task_type,
            "instructions": instructions,
            "runId": run_id,
            "metadata": coerce_json_dict(metadata),
        }
        dispatch_result: dict[str, JsonValue] = {}
        if self._crew_bridge is not None:
            dispatch_result = coerce_json_dict(
                await self._crew_bridge.dispatch_task(request)
            )
        return {
            "schemaVersion": SCHEMA_VERSION,
            "taskId": task_id,
            "request": request,
            "dispatch": dispatch_result,
        }
