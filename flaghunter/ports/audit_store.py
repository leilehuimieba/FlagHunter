"""Audit, artifact, checkpoint, and read model boundary contracts."""

from typing import Any, Iterable, Mapping, Protocol, runtime_checkable


@runtime_checkable
class AuditStorePort(Protocol):
    def append_event(
        self,
        event: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...

    def query_events(
        self,
        filters: Mapping[str, Any] | None = None,
    ) -> Iterable[Mapping[str, Any]]:
        ...


@runtime_checkable
class ArtifactStorePort(Protocol):
    def register_artifact(
        self,
        artifact: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...

    def get_artifact(self, artifact_id: str) -> Mapping[str, Any] | None:
        ...


@runtime_checkable
class CheckpointStorePort(Protocol):
    def create_checkpoint(
        self,
        run_id: str,
        snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...

    def load_checkpoint(self, checkpoint_id: str) -> Mapping[str, Any] | None:
        ...


@runtime_checkable
class ReadModelStorePort(Protocol):
    def get_read_model(
        self,
        name: str,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        ...

    def list_read_models(self) -> Iterable[Mapping[str, Any]]:
        ...
