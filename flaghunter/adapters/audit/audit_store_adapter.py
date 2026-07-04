"""Audit store adapter skeletons."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from flaghunter.ports import AuditStorePort


class AuditStoreAdapter:
    """Delegate audit event access through an injected audit store port."""

    def __init__(self, store: AuditStorePort) -> None:
        self._store = store

    def append_event(
        self,
        event: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return self._store.append_event(event)

    def query_events(
        self,
        filters: Mapping[str, Any] | None = None,
    ) -> Iterable[Mapping[str, Any]]:
        return self._store.query_events(filters)
