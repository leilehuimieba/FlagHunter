"""State store adapter skeletons."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.ports import StateStorePort


class StateStoreAdapter:
    """Delegate run snapshot access through an injected state store port."""

    def __init__(self, store: StateStorePort) -> None:
        self._store = store

    def load_snapshot(self, run_id: str) -> Mapping[str, Any] | None:
        return self._store.load_snapshot(run_id)

    def save_snapshot(
        self,
        run_id: str,
        snapshot: Mapping[str, Any],
    ) -> None:
        self._store.save_snapshot(run_id, snapshot)
