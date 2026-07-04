"""Read model store adapter skeletons."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from flaghunter.ports import ReadModelStorePort


class ReadModelStoreAdapter:
    """Delegate read model access through an injected read model store port."""

    def __init__(self, store: ReadModelStorePort) -> None:
        self._store = store

    def get_read_model(
        self,
        name: str,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        return self._store.get_read_model(name, filters=filters)

    def list_read_models(self) -> Iterable[Mapping[str, Any]]:
        return self._store.list_read_models()
