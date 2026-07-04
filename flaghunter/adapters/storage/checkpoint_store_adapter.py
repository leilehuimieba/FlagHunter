"""Checkpoint store adapter skeletons."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.ports import CheckpointStorePort


class CheckpointStoreAdapter:
    """Delegate checkpoint access through an injected checkpoint store port."""

    def __init__(self, store: CheckpointStorePort) -> None:
        self._store = store

    def create_checkpoint(
        self,
        run_id: str,
        snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return self._store.create_checkpoint(run_id, snapshot)

    def load_checkpoint(self, checkpoint_id: str) -> Mapping[str, Any] | None:
        return self._store.load_checkpoint(checkpoint_id)
