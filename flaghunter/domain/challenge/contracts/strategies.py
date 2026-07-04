from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list
from .sanitization import preview_text, sanitize_metadata


SCHEMA_VERSION = "challenge.strategy_catalog.v1"
STRATEGY_REF_SCHEMA_VERSION = "challenge.strategy_ref.v1"
STRATEGY_SELECTION_SCHEMA_VERSION = "challenge.strategy_selection.v1"


@dataclass(frozen=True)
class StrategyRef:
    strategy_id: str
    name: str = ""
    strategy_kind: str = "generic"
    status: str = "available"
    capability_refs: list[str] = field(default_factory=list)
    policy_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": STRATEGY_REF_SCHEMA_VERSION,
            "strategyId": _clean(self.strategy_id),
            "namePreview": preview_text(self.name),
            "strategyKind": _clean(self.strategy_kind) or "generic",
            "status": _clean(self.status) or "available",
            "capabilityRefs": _str_refs(self.capability_refs),
            "policyRefs": _str_refs(self.policy_refs),
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyRef":
        return cls(
            strategy_id=str(payload.get("strategyId", "")),
            name=str(payload.get("namePreview", "")),
            strategy_kind=str(payload.get("strategyKind", "generic")),
            status=str(payload.get("status", "available")),
            capability_refs=[
                str(item) for item in coerce_json_list(payload.get("capabilityRefs"))
            ],
            policy_refs=[
                str(item) for item in coerce_json_list(payload.get("policyRefs"))
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class StrategySelection:
    run_id: str
    selected_strategy_id: str
    reason_preview: str = ""
    score: float | None = None
    candidate_strategy_ids: list[str] = field(default_factory=list)
    policy_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": STRATEGY_SELECTION_SCHEMA_VERSION,
            "runId": _clean(self.run_id),
            "selectedStrategyId": _clean(self.selected_strategy_id),
            "reasonPreview": preview_text(self.reason_preview),
            "score": _optional_float(self.score),
            "candidateStrategyIds": _str_refs(self.candidate_strategy_ids),
            "policyRefs": _str_refs(self.policy_refs),
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategySelection":
        return cls(
            run_id=str(payload.get("runId", "")),
            selected_strategy_id=str(payload.get("selectedStrategyId", "")),
            reason_preview=str(payload.get("reasonPreview", "")),
            score=_optional_float(payload.get("score")),
            candidate_strategy_ids=[
                str(item)
                for item in coerce_json_list(payload.get("candidateStrategyIds"))
            ],
            policy_refs=[
                str(item) for item in coerce_json_list(payload.get("policyRefs"))
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class StrategyCatalog:
    run_id: str
    strategies: list[StrategyRef] = field(default_factory=list)
    selections: list[StrategySelection] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        strategy_payloads = [_coerce_strategy(item).to_dict() for item in self.strategies]
        selection_payloads = [
            _coerce_selection(item).to_dict() for item in self.selections
        ]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "runId": _clean(self.run_id),
            "strategies": strategy_payloads,
            "selections": selection_payloads,
            "summary": {
                "strategyCount": len(strategy_payloads),
                "selectionCount": len(selection_payloads),
                "kindCounts": _counts(
                    item.get("strategyKind") for item in strategy_payloads
                ),
                "statusCounts": _counts(item.get("status") for item in strategy_payloads),
            },
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyCatalog":
        return cls(
            run_id=str(payload.get("runId", "")),
            strategies=[
                StrategyRef.from_dict(item)
                for item in coerce_json_list(payload.get("strategies"))
                if isinstance(item, dict)
            ],
            selections=[
                StrategySelection.from_dict(item)
                for item in coerce_json_list(payload.get("selections"))
                if isinstance(item, dict)
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


def _coerce_strategy(value: StrategyRef | Mapping[str, Any]) -> StrategyRef:
    if isinstance(value, StrategyRef):
        return value
    return StrategyRef.from_dict(value)


def _coerce_selection(
    value: StrategySelection | Mapping[str, Any],
) -> StrategySelection:
    if isinstance(value, StrategySelection):
        return value
    return StrategySelection.from_dict(value)


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = _clean(value)
        if key:
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str_refs(values: Any) -> list[str]:
    return [_clean(item) for item in coerce_json_list(values) if _clean(item)]


def _clean(value: Any) -> str:
    return str(value or "").strip()
