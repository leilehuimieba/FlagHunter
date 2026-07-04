"""Record neutral task receipts through injected ports."""

from __future__ import annotations

from typing import Iterable

from flaghunter.domain.challenge.contracts._serialization import JsonValue, coerce_json_dict
from flaghunter.domain.challenge.contracts.receipts import TaskReceipt
from flaghunter.ports.audit_store import AuditStorePort


SCHEMA_VERSION = 1


class RecordTaskReceipt:
    def __init__(self, *, audit_store: AuditStorePort | None = None) -> None:
        self._audit_store = audit_store

    def record(
        self,
        *,
        receipt_id: str,
        task_id: str,
        outcome: str,
        summary: str | None = None,
        artifact_refs: Iterable[str] | None = None,
        metadata: dict[str, JsonValue] | None = None,
        run_id: str | None = None,
    ) -> TaskReceipt:
        receipt = TaskReceipt(
            receipt_id=receipt_id,
            task_id=task_id,
            outcome=outcome,
            summary=summary,
            artifact_refs=[str(item) for item in artifact_refs or []],
            metadata=coerce_json_dict(metadata),
        )
        if self._audit_store is not None:
            self._audit_store.append_event(_receipt_event(receipt=receipt, run_id=run_id))
        return receipt


def _receipt_event(
    *,
    receipt: TaskReceipt,
    run_id: str | None,
) -> dict[str, JsonValue]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "eventType": "taskReceiptRecorded",
        "runId": run_id,
        "receipt": receipt.to_dict(),
    }
