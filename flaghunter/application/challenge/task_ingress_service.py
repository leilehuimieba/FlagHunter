"""Submit neutral task ingress payloads through injected ports."""

from __future__ import annotations

from flaghunter.domain.challenge.contracts._serialization import JsonValue, coerce_json_dict
from flaghunter.ports.task_ingress import TaskIngressPort


SCHEMA_VERSION = 1


class SubmitTaskIngress:
    def __init__(self, *, task_ingress: TaskIngressPort | None = None) -> None:
        self._task_ingress = task_ingress

    async def submit(
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
        ingress_result: dict[str, JsonValue] = {}
        if self._task_ingress is not None:
            ingress_result = coerce_json_dict(
                await self._task_ingress.submit_task(request)
            )
        return {
            "schemaVersion": SCHEMA_VERSION,
            "taskId": task_id,
            "request": request,
            "ingress": ingress_result,
        }
