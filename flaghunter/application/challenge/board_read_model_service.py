"""Build neutral challenge board read models from domain snapshots."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.domain.challenge.contracts import (
    BoardItem,
    ChallengeBoardReadModel,
    ChallengeRunSnapshot,
)
from flaghunter.domain.challenge.contracts._serialization import (
    JsonValue,
    coerce_json_dict,
    coerce_json_list,
)


class BuildChallengeBoardReadModel:
    def build(
        self,
        snapshot: ChallengeRunSnapshot | Mapping[str, Any],
    ) -> ChallengeBoardReadModel:
        run_snapshot = _normalize_snapshot(snapshot)
        metadata = coerce_json_dict(run_snapshot.metadata)
        return ChallengeBoardReadModel(
            run_id=run_snapshot.run_id,
            challenge_id=run_snapshot.challenge_id,
            facts=_claim_items(run_snapshot),
            evidence=_evidence_items(run_snapshot),
            receipts=_receipt_items(run_snapshot),
            tasks=_task_items(run_snapshot),
            surface_refs=_surface_refs(metadata.get("surfaceRefs")),
            metadata={
                key: value
                for key, value in metadata.items()
                if key != "surfaceRefs"
            },
        )


def _normalize_snapshot(
    snapshot: ChallengeRunSnapshot | Mapping[str, Any],
) -> ChallengeRunSnapshot:
    if isinstance(snapshot, ChallengeRunSnapshot):
        return snapshot
    return ChallengeRunSnapshot.from_dict(snapshot)


def _claim_items(snapshot: ChallengeRunSnapshot) -> list[BoardItem]:
    return [
        BoardItem(
            item_id=claim.claim_id,
            item_type=f"claim:{claim.claim_type}",
            value=claim.claim_value,
            metadata={
                "artifactRefs": [str(item) for item in claim.artifact_refs],
                "evidenceRefs": [str(item) for item in claim.evidence_refs],
                "status": claim.status,
            },
        )
        for claim in snapshot.claims
    ]


def _evidence_items(snapshot: ChallengeRunSnapshot) -> list[BoardItem]:
    return [
        BoardItem(
            item_id=record.evidence_id,
            item_type=record.evidence_type,
            value=record.evidence_value,
            source_ref=record.source_ref,
            metadata={
                "artifactRef": record.artifact_ref,
                "claimId": record.claim_id,
                "tags": [str(item) for item in record.tags],
                **coerce_json_dict(record.metadata),
            },
        )
        for record in snapshot.evidence
    ]


def _receipt_items(snapshot: ChallengeRunSnapshot) -> list[BoardItem]:
    return [
        BoardItem(
            item_id=receipt.receipt_id,
            item_type=f"receipt:{receipt.outcome}",
            value=receipt.summary if receipt.summary is not None else receipt.outcome,
            metadata={
                "artifactRefs": [str(item) for item in receipt.artifact_refs],
                "outcome": receipt.outcome,
                "taskId": receipt.task_id,
                **coerce_json_dict(receipt.metadata),
            },
        )
        for receipt in snapshot.receipts
    ]


def _task_items(snapshot: ChallengeRunSnapshot) -> list[BoardItem]:
    return [
        BoardItem(
            item_id=node.node_id,
            item_type="task",
            value=node.title,
            source_ref=node.task_ref,
            metadata={
                "dependsOn": [str(item) for item in node.depends_on],
                "strategyRef": node.strategy_ref,
                **coerce_json_dict(node.metadata),
            },
        )
        for node in snapshot.task_nodes
    ]


def _surface_refs(value: JsonValue) -> list[dict[str, JsonValue]]:
    return [
        coerce_json_dict(item)
        for item in coerce_json_list(value if isinstance(value, list) else None)
        if isinstance(item, Mapping)
    ]
