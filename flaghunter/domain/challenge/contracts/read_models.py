from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .claims import ChallengeClaim
from .evidence import EvidenceRecord
from .proof import ProofRecord
from .receipts import TaskReceipt
from .task_graph import TaskGraphNode
from ._serialization import (
    JsonValue,
    coerce_json_dict,
    coerce_json_list,
)
from .sanitization import preview_text, sanitize_json_value, sanitize_metadata


SCHEMA_VERSION = 1
BOARD_ITEM_SCHEMA_VERSION = "challenge.board_item.v1"
BOARD_READ_MODEL_SCHEMA_VERSION = "challenge.board_read_model.v1"


@dataclass(frozen=True)
class BoardItem:
    item_id: str
    item_type: str
    value: JsonValue
    source_ref: str | None = None
    confidence: float | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": BOARD_ITEM_SCHEMA_VERSION,
            "itemId": self.item_id,
            "itemType": self.item_type,
            "value": sanitize_json_value(self.value),
            "sourceRef": (
                preview_text(self.source_ref)
                if self.source_ref is not None
                else None
            ),
            "confidence": self.confidence,
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BoardItem":
        confidence = payload.get("confidence")
        return cls(
            item_id=str(payload.get("itemId", "")),
            item_type=str(payload.get("itemType", "")),
            value=sanitize_json_value(payload.get("value")),
            source_ref=(
                str(payload["sourceRef"])
                if payload.get("sourceRef") is not None
                else None
            ),
            confidence=float(confidence) if confidence is not None else None,
            metadata=coerce_json_dict(payload.get("metadata")),
        )


def _coerce_mapping_list(value: Any) -> list[dict[str, JsonValue]]:
    return [
        coerce_json_dict(item)
        for item in coerce_json_list(value)
        if isinstance(item, Mapping)
    ]


def _coerce_board_items(value: Any) -> list[BoardItem]:
    return [
        BoardItem.from_dict(item)
        for item in coerce_json_list(value)
        if isinstance(item, Mapping)
    ]


@dataclass(frozen=True)
class ChallengeBoardReadModel:
    run_id: str
    challenge_id: str
    facts: list[BoardItem] = field(default_factory=list)
    evidence: list[BoardItem] = field(default_factory=list)
    receipts: list[BoardItem] = field(default_factory=list)
    tasks: list[BoardItem] = field(default_factory=list)
    decisions: list[dict[str, JsonValue]] = field(default_factory=list)
    candidates: list[dict[str, JsonValue]] = field(default_factory=list)
    action_results: list[dict[str, JsonValue]] = field(default_factory=list)
    recommended_task: dict[str, JsonValue] = field(default_factory=dict)
    surface_refs: list[dict[str, JsonValue]] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": BOARD_READ_MODEL_SCHEMA_VERSION,
            "runId": self.run_id,
            "challengeId": self.challenge_id,
            "facts": [item.to_dict() for item in self.facts],
            "evidence": [item.to_dict() for item in self.evidence],
            "receipts": [item.to_dict() for item in self.receipts],
            "tasks": [item.to_dict() for item in self.tasks],
            "decisions": [
                sanitize_metadata(coerce_json_dict(item)) for item in self.decisions
            ],
            "candidates": [
                sanitize_metadata(coerce_json_dict(item)) for item in self.candidates
            ],
            "actionResults": [
                sanitize_metadata(coerce_json_dict(item))
                for item in self.action_results
            ],
            "recommendedTask": sanitize_metadata(
                coerce_json_dict(self.recommended_task)
            ),
            "surfaceRefs": [
                sanitize_metadata(coerce_json_dict(item)) for item in self.surface_refs
            ],
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ChallengeBoardReadModel":
        return cls(
            run_id=str(payload.get("runId", "")),
            challenge_id=str(payload.get("challengeId", "")),
            facts=_coerce_board_items(payload.get("facts")),
            evidence=_coerce_board_items(payload.get("evidence")),
            receipts=_coerce_board_items(payload.get("receipts")),
            tasks=_coerce_board_items(payload.get("tasks")),
            decisions=_coerce_mapping_list(payload.get("decisions")),
            candidates=_coerce_mapping_list(payload.get("candidates")),
            action_results=_coerce_mapping_list(payload.get("actionResults")),
            recommended_task=coerce_json_dict(payload.get("recommendedTask")),
            surface_refs=_coerce_mapping_list(payload.get("surfaceRefs")),
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class ReadModelRef:
    model_id: str
    model_type: str
    run_id: str | None = None
    version: int = 1
    label: str | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "modelId": self.model_id,
            "modelType": self.model_type,
            "runId": self.run_id,
            "version": self.version,
            "label": self.label,
            "metadata": coerce_json_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReadModelRef":
        return cls(
            model_id=str(payload.get("modelId", "")),
            model_type=str(payload.get("modelType", "")),
            run_id=str(payload["runId"]) if payload.get("runId") is not None else None,
            version=int(payload.get("version", 1)),
            label=str(payload["label"]) if payload.get("label") is not None else None,
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class ChallengeRunSnapshot:
    run_id: str
    challenge_id: str
    claims: list[ChallengeClaim] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    receipts: list[TaskReceipt] = field(default_factory=list)
    task_nodes: list[TaskGraphNode] = field(default_factory=list)
    read_models: list[ReadModelRef] = field(default_factory=list)
    proof_records: list[ProofRecord] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "runId": self.run_id,
            "challengeId": self.challenge_id,
            "claims": [claim.to_dict() for claim in self.claims],
            "evidence": [record.to_dict() for record in self.evidence],
            "receipts": [receipt.to_dict() for receipt in self.receipts],
            "taskNodes": [node.to_dict() for node in self.task_nodes],
            "readModels": [model.to_dict() for model in self.read_models],
            "proofRecords": [record.to_dict() for record in self.proof_records],
            "metadata": coerce_json_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ChallengeRunSnapshot":
        return cls(
            run_id=str(payload.get("runId", "")),
            challenge_id=str(payload.get("challengeId", "")),
            claims=[
                ChallengeClaim.from_dict(item)
                for item in coerce_json_list(payload.get("claims"))
                if isinstance(item, dict)
            ],
            evidence=[
                EvidenceRecord.from_dict(item)
                for item in coerce_json_list(payload.get("evidence"))
                if isinstance(item, dict)
            ],
            receipts=[
                TaskReceipt.from_dict(item)
                for item in coerce_json_list(payload.get("receipts"))
                if isinstance(item, dict)
            ],
            task_nodes=[
                TaskGraphNode.from_dict(item)
                for item in coerce_json_list(payload.get("taskNodes"))
                if isinstance(item, dict)
            ],
            read_models=[
                ReadModelRef.from_dict(item)
                for item in coerce_json_list(payload.get("readModels"))
                if isinstance(item, dict)
            ],
            proof_records=[
                ProofRecord.from_dict(item)
                for item in coerce_json_list(payload.get("proofRecords"))
                if isinstance(item, dict)
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )
