from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list
from .sanitization import preview_text, sanitize_metadata


SCHEMA_VERSION = "challenge.artifact_manifest.v1"
ARTIFACT_RECORD_SCHEMA_VERSION = "challenge.artifact_record.v1"


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    artifact_ref: str
    artifact_kind: str = "generic"
    media_type: str = ""
    label: str = ""
    content_preview: str = ""
    claim_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": ARTIFACT_RECORD_SCHEMA_VERSION,
            "artifactId": _clean(self.artifact_id),
            "artifactRef": preview_text(self.artifact_ref),
            "artifactKind": _clean(self.artifact_kind) or "generic",
            "mediaType": _clean(self.media_type),
            "labelPreview": preview_text(self.label),
            "contentPreview": preview_text(self.content_preview),
            "claimIds": _str_refs(self.claim_ids),
            "evidenceIds": _str_refs(self.evidence_ids),
            "taskIds": _str_refs(self.task_ids),
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactRecord":
        return cls(
            artifact_id=str(payload.get("artifactId", "")),
            artifact_ref=str(payload.get("artifactRef", "")),
            artifact_kind=str(payload.get("artifactKind", "generic")),
            media_type=str(payload.get("mediaType", "")),
            label=str(payload.get("labelPreview", "")),
            content_preview=str(payload.get("contentPreview", "")),
            claim_ids=[str(item) for item in coerce_json_list(payload.get("claimIds"))],
            evidence_ids=[
                str(item) for item in coerce_json_list(payload.get("evidenceIds"))
            ],
            task_ids=[str(item) for item in coerce_json_list(payload.get("taskIds"))],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class ArtifactManifest:
    run_id: str
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        artifact_payloads = [_coerce_artifact(item).to_dict() for item in self.artifacts]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "runId": _clean(self.run_id),
            "artifacts": artifact_payloads,
            "summary": {
                "artifactCount": len(artifact_payloads),
                "kindCounts": _counts(
                    item.get("artifactKind") for item in artifact_payloads
                ),
                "mediaTypeCounts": _counts(
                    item.get("mediaType") for item in artifact_payloads
                ),
            },
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactManifest":
        return cls(
            run_id=str(payload.get("runId", "")),
            artifacts=[
                ArtifactRecord.from_dict(item)
                for item in coerce_json_list(payload.get("artifacts"))
                if isinstance(item, dict)
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


def _coerce_artifact(value: ArtifactRecord | Mapping[str, Any]) -> ArtifactRecord:
    if isinstance(value, ArtifactRecord):
        return value
    return ArtifactRecord.from_dict(value)


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
