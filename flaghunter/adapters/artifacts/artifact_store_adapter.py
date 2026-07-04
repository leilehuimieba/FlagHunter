"""Artifact store adapter skeletons."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.ports import ArtifactStorePort


class ArtifactStoreAdapter:
    """Delegate artifact access through an injected artifact store port."""

    def __init__(self, store: ArtifactStorePort) -> None:
        self._store = store

    def register_artifact(
        self,
        artifact: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return self._store.register_artifact(artifact)

    def get_artifact(self, artifact_id: str) -> Mapping[str, Any] | None:
        return self._store.get_artifact(artifact_id)
