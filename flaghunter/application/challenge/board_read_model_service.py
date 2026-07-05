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
            decisions=_mapping_list(metadata.get("decisions")),
            candidates=_mapping_list(metadata.get("candidates")),
            action_results=_mapping_list(metadata.get("actionResults")),
            recommended_task=coerce_json_dict(metadata.get("recommendedTask")),
            surface_refs=_surface_refs(metadata.get("surfaceRefs")),
            metadata={
                key: value
                for key, value in metadata.items()
                if key
                not in {
                    "actionResults",
                    "candidates",
                    "decisions",
                    "recommendedTask",
                    "surfaceRefs",
                }
            },
        )


def build_task_board_projection(
    read_model: ChallengeBoardReadModel | Mapping[str, Any] | None,
) -> dict[str, JsonValue]:
    board = _normalize_board(read_model)
    payload = board.to_dict()
    decisions = _mapping_list(payload.get("decisions"))
    candidates = _candidate_list(payload.get("candidates"))
    action_results = _action_result_list(payload.get("actionResults"))
    active_decision = _first_mapping(payload.get("decisions"))
    evidence_items = [
        item
        for item in _mapping_list(payload.get("evidence"))
        if _is_projectable_board_item(item)
        and _item_bucket(item) != "pendingVerification"
    ]
    pending_items = [
        item
        for item in _mapping_list(payload.get("evidence"))
        if _is_projectable_board_item(item)
        and _item_bucket(item) == "pendingVerification"
    ]
    return {
        "facts": [
            _board_item_projection(item)
            for item in _mapping_list(payload.get("facts"))
            if _is_projectable_board_item(item)
        ]
        + [_board_item_projection(item) for item in evidence_items],
        "hypotheses": _mapping_list(payload.get("metadata", {}).get("hypotheses")),
        "pending_verifications": [
            _board_item_projection(item) for item in pending_items
        ],
        "decisions": decisions,
        "candidates": candidates,
        "active_decision": active_decision,
        "action_results": action_results,
        "recommended_action": _recommended_action_projection(
            explicit=coerce_json_dict(payload.get("recommendedTask")),
            candidates=candidates,
            active_decision=active_decision,
            action_results=action_results,
        ),
        "attack_surfaces": _mapping_list(payload.get("surfaceRefs")),
    }


def _normalize_snapshot(
    snapshot: ChallengeRunSnapshot | Mapping[str, Any],
) -> ChallengeRunSnapshot:
    if isinstance(snapshot, ChallengeRunSnapshot):
        return snapshot
    return ChallengeRunSnapshot.from_dict(snapshot)


def _normalize_board(
    read_model: ChallengeBoardReadModel | Mapping[str, Any] | None,
) -> ChallengeBoardReadModel:
    if isinstance(read_model, ChallengeBoardReadModel):
        return read_model
    if not isinstance(read_model, Mapping):
        return ChallengeBoardReadModel(run_id="", challenge_id="")
    return ChallengeBoardReadModel.from_dict(read_model)


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


def _mapping_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    return [
        coerce_json_dict(item)
        for item in coerce_json_list(value if isinstance(value, list) else None)
        if isinstance(item, Mapping)
    ]


def _candidate_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    return [
        item
        for item in _mapping_list(value)
        if _clean_text(item.get("action"))
    ]


def _action_result_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    return [
        item
        for item in _mapping_list(value)
        if _clean_text(item.get("action")) and _clean_text(item.get("result"))
    ]


def _first_mapping(value: JsonValue) -> dict[str, JsonValue]:
    items = _mapping_list(value)
    return items[0] if items else {}


def _item_bucket(item: Mapping[str, Any]) -> str:
    metadata = coerce_json_dict(item.get("metadata"))
    bucket = metadata.get("boardBucket")
    return str(bucket or "")


def _is_projectable_board_item(item: Mapping[str, Any]) -> bool:
    return bool(str(item.get("itemType") or "").strip())


def _recommended_action_projection(
    *,
    explicit: dict[str, JsonValue],
    candidates: list[dict[str, JsonValue]],
    active_decision: Mapping[str, Any],
    action_results: list[dict[str, JsonValue]],
) -> dict[str, JsonValue]:
    if explicit:
        _mark_recommended_candidate(candidates, _clean_text(explicit.get("action")))
        return explicit
    if isinstance(active_decision.get("suppressedRecommendation"), Mapping):
        return {}
    selected_action = _clean_text(active_decision.get("nextAction"))
    if not selected_action:
        return {}
    selected_candidate = next(
        (
            item
            for item in candidates
            if _clean_text(item.get("action")) == selected_action
        ),
        None,
    )
    if not isinstance(selected_candidate, Mapping):
        return {}
    latest_selected_result = _latest_action_result(action_results, selected_action)
    result = _clean_text(
        latest_selected_result.get("result") or selected_candidate.get("lastResult")
    ).lower()
    if result not in {"failed", "skipped"}:
        return {}
    details = latest_selected_result.get("details")
    detail_map = coerce_json_dict(details if isinstance(details, Mapping) else None)
    for candidate in candidates:
        action = _clean_text(candidate.get("action"))
        if not action or action == selected_action:
            continue
        candidate["recommended"] = True
        recommended_action: dict[str, JsonValue] = {
            "action": action,
            "driver": _clean_text(candidate.get("driver")),
            "sourceType": _clean_text(candidate.get("sourceType")),
            "reason": "selected action failed; switch to next best candidate",
            "switchedFrom": selected_action,
            "triggerResult": result,
        }
        trigger_reason = _clean_text(detail_map.get("reason"))
        if trigger_reason:
            recommended_action["triggerReason"] = trigger_reason
        trigger_action_driver = _clean_text(latest_selected_result.get("driver"))
        if trigger_action_driver:
            recommended_action["triggerActionDriver"] = trigger_action_driver
        trigger_at = _clean_text(latest_selected_result.get("t"))
        if trigger_at:
            recommended_action["triggerAt"] = trigger_at
        _copy_hypothesis_summary(recommended_action, latest_selected_result)
        _copy_hypothesis_summary(recommended_action, active_decision)
        return recommended_action
    return {}


def _mark_recommended_candidate(
    candidates: list[dict[str, JsonValue]],
    recommended_action: str,
) -> None:
    if not recommended_action:
        return
    for candidate in candidates:
        if _clean_text(candidate.get("action")) == recommended_action:
            candidate["recommended"] = True


def _latest_action_result(
    action_results: list[dict[str, JsonValue]],
    action: str,
) -> dict[str, JsonValue]:
    for item in reversed(action_results):
        if _clean_text(item.get("action")) == action:
            return item
    return {}


def _copy_hypothesis_summary(
    target: dict[str, JsonValue],
    source: Mapping[str, Any],
) -> None:
    for key in (
        "strongestHypothesisKind",
        "strongestHypothesisStatus",
        "strongestHypothesisConfidence",
    ):
        if key not in target and source.get(key) is not None:
            target[key] = source.get(key)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _board_item_projection(item: Mapping[str, Any]) -> dict[str, JsonValue]:
    metadata = coerce_json_dict(item.get("metadata"))
    projection: dict[str, JsonValue] = {
        "kind": str(item.get("itemType") or ""),
        "value": item.get("value"),
    }
    source = item.get("sourceRef")
    if source is not None:
        projection["source"] = str(source)
    confidence = item.get("confidence")
    if confidence is not None:
        projection["confidence"] = confidence
    rationale = metadata.get("rationale")
    if rationale is not None:
        projection["rationale"] = rationale
    return projection
