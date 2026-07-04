"""Crew bridge adapter skeletons."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.ports import CrewBridgePort


class CrewBridgeAdapter:
    """Delegate worker task dispatch through an injected crew bridge port."""

    def __init__(self, bridge: CrewBridgePort) -> None:
        self._bridge = bridge

    async def dispatch_task(
        self,
        request: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return await self._bridge.dispatch_task(request)
