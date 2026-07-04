from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .claims import ChallengeClaim
from .evidence import EvidenceRecord
from .proof import ProofRecord
from .receipts import TaskReceipt
from .task_graph import TaskGraphNode
from ._serialization import JsonValue, coerce_json_dict, coerce_json_list


SCHEMA_VERSION = 1


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
