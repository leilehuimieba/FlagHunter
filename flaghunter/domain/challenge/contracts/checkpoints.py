from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list
from .sanitization import preview_text, sanitize_metadata


SCHEMA_VERSION = "challenge.checkpoint_manifest.v1"
CHECKPOINT_RECORD_SCHEMA_VERSION = "challenge.checkpoint_record.v1"
RESUME_CONTEXT_REF_SCHEMA_VERSION = "challenge.resume_context_ref.v1"


@dataclass(frozen=True)
class CheckpointRecord:
    checkpoint_id: str
    run_id: str
    label: str = ""
    stop_reason: str = ""
    summary_preview: str = ""
    artifact_refs: list[str] = field(default_factory=list)
    read_model_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": CHECKPOINT_RECORD_SCHEMA_VERSION,
            "checkpointId": _clean(self.checkpoint_id),
            "runId": _clean(self.run_id),
            "label": preview_text(self.label),
            "stopReason": preview_text(self.stop_reason),
            "summaryPreview": preview_text(self.summary_preview),
            "artifactRefs": [preview_text(item) for item in _str_refs(self.artifact_refs)],
            "readModelRefs": _str_refs(self.read_model_refs),
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CheckpointRecord":
        return cls(
            checkpoint_id=str(payload.get("checkpointId", "")),
            run_id=str(payload.get("runId", "")),
            label=str(payload.get("label", "")),
            stop_reason=str(payload.get("stopReason", "")),
            summary_preview=str(payload.get("summaryPreview", "")),
            artifact_refs=[
                str(item) for item in coerce_json_list(payload.get("artifactRefs"))
            ],
            read_model_refs=[
                str(item) for item in coerce_json_list(payload.get("readModelRefs"))
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class ResumeContextRef:
    run_id: str
    checkpoint_id: str
    next_action: str = ""
    summary_preview: str = ""
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": RESUME_CONTEXT_REF_SCHEMA_VERSION,
            "runId": _clean(self.run_id),
            "checkpointId": _clean(self.checkpoint_id),
            "nextAction": _clean(self.next_action),
            "summaryPreview": preview_text(self.summary_preview),
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResumeContextRef":
        return cls(
            run_id=str(payload.get("runId", "")),
            checkpoint_id=str(payload.get("checkpointId", "")),
            next_action=str(payload.get("nextAction", "")),
            summary_preview=str(payload.get("summaryPreview", "")),
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class CheckpointManifest:
    run_id: str
    checkpoints: list[CheckpointRecord] = field(default_factory=list)
    resume_contexts: list[ResumeContextRef] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        checkpoint_payloads = [
            _coerce_checkpoint(item).to_dict() for item in self.checkpoints
        ]
        resume_payloads = [
            _coerce_resume_context(item).to_dict() for item in self.resume_contexts
        ]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "runId": _clean(self.run_id),
            "checkpoints": checkpoint_payloads,
            "resumeContexts": resume_payloads,
            "summary": {
                "checkpointCount": len(checkpoint_payloads),
                "resumeContextCount": len(resume_payloads),
                "labelCounts": _counts(item.get("label") for item in checkpoint_payloads),
                "nextActionCounts": _counts(
                    item.get("nextAction") for item in resume_payloads
                ),
            },
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CheckpointManifest":
        return cls(
            run_id=str(payload.get("runId", "")),
            checkpoints=[
                CheckpointRecord.from_dict(item)
                for item in coerce_json_list(payload.get("checkpoints"))
                if isinstance(item, dict)
            ],
            resume_contexts=[
                ResumeContextRef.from_dict(item)
                for item in coerce_json_list(payload.get("resumeContexts"))
                if isinstance(item, dict)
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


def _coerce_checkpoint(
    value: CheckpointRecord | Mapping[str, Any],
) -> CheckpointRecord:
    if isinstance(value, CheckpointRecord):
        return value
    return CheckpointRecord.from_dict(value)


def _coerce_resume_context(
    value: ResumeContextRef | Mapping[str, Any],
) -> ResumeContextRef:
    if isinstance(value, ResumeContextRef):
        return value
    return ResumeContextRef.from_dict(value)


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = _clean(value)
        if key:
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _str_refs(values: Any) -> list[str]:
    return [_clean(item) for item in coerce_json_list(values) if _clean(item)]


def _clean(value: Any) -> str:
    return str(value or "").strip()
