"""Build neutral evidence snapshots from injected read ports."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.domain.challenge.contracts._serialization import (
    JsonValue,
    coerce_json_value,
)
from flaghunter.domain.challenge.contracts.evidence_snapshot import EvidenceSnapshot
from flaghunter.ports.audit_store import AuditStorePort


SCHEMA_VERSION = 1


class BuildEvidenceSnapshot:
    def __init__(self, *, audit_store: AuditStorePort | None = None) -> None:
        self._audit_store = audit_store

    def build(
        self,
        *,
        run_id: str | None = None,
        trace_limit: int = 50,
        claim_evidence_limit: int = 50,
    ) -> EvidenceSnapshot:
        if self._audit_store is None:
            return EvidenceSnapshot()
        events = self._load_events(run_id=run_id)
        trace_refs = _collect_refs(events, key="traceRef")
        claim_evidence_refs = _collect_refs(events, key="claimEvidenceRef")
        trace_kinds = _collect_trace_kinds(events)
        return EvidenceSnapshot(
            trace_refs=trace_refs[: max(0, trace_limit)],
            claim_evidence_refs=claim_evidence_refs[: max(0, claim_evidence_limit)],
            audit_evidence_export={
                "schemaVersion": SCHEMA_VERSION,
                "summary": {
                    "claimCount": len(claim_evidence_refs),
                    "executionTraceCount": len(trace_refs),
                    "verificationRecordCount": 0,
                },
            },
            trace_kinds=trace_kinds,
        )

    def _load_events(self, *, run_id: str | None) -> list[Mapping[str, Any]]:
        if self._audit_store is None:
            return []
        filters = {"runId": run_id} if run_id is not None else None
        return [
            event
            for event in self._audit_store.query_events(filters=filters)
            if isinstance(event, Mapping)
        ]


def _collect_refs(events: list[Mapping[str, Any]], *, key: str) -> list[JsonValue]:
    refs: list[JsonValue] = []
    for event in events:
        if key not in event:
            continue
        refs.append(coerce_json_value(event.get(key)))
    return refs


def _collect_trace_kinds(events: list[Mapping[str, Any]]) -> set[str]:
    kinds: set[str] = set()
    for event in events:
        kind = event.get("traceKind")
        if kind is not None:
            kinds.add(str(kind))
    return kinds
