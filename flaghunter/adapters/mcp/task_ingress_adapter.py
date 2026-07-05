"""Task ingress adapter skeletons."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.ports import TaskIngressPort


class TaskIngressAdapter:
    """Delegate task ingress through an injected task ingress port."""

    def __init__(self, ingress: TaskIngressPort) -> None:
        self._ingress = ingress

    async def submit_task(
        self,
        request: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return await self._ingress.submit_task(request)
