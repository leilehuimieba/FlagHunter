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
            decisions=_decision_items(metadata),
            candidates=_mapping_list(metadata.get("candidates")),
            action_results=_mapping_list(
                metadata.get("actionResults") or metadata.get("action_results")
            ),
            recommended_task=_first_mapping_value(
                metadata,
                "recommendedTask",
                "recommendedAction",
                "recommended_action",
            ),
            surface_refs=_surface_refs(
                metadata.get("surfaceRefs") or metadata.get("attack_surfaces")
            ),
            metadata={
                key: value
                for key, value in metadata.items()
                if key
                not in {
                    "actionResults",
                    "action_results",
                    "activeDecision",
                    "active_decision",
                    "attack_surfaces",
                    "candidates",
                    "decisions",
                    "recommendedAction",
                    "recommended_action",
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
    decisions = _decision_list(payload.get("decisions"))
    action_results = _action_result_list(payload.get("actionResults"))
    candidates = _candidate_list(payload.get("candidates"), action_results)
    active_decision = decisions[0] if decisions else {}
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
    recommended_action = _recommended_action_projection(
        explicit=coerce_json_dict(payload.get("recommendedTask")),
        candidates=candidates,
        active_decision=active_decision,
        action_results=action_results,
    )
    _enrich_candidates(
        candidates,
        active_decision=active_decision,
        recommended_action=recommended_action,
    )
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
        "recommended_action": recommended_action,
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


def _decision_items(metadata: Mapping[str, JsonValue]) -> list[dict[str, JsonValue]]:
    decisions = _mapping_list(metadata.get("decisions"))
    active_decision = _first_mapping_value(
        metadata,
        "activeDecision",
        "active_decision",
    )
    if active_decision:
        return [active_decision, *decisions]
    return decisions


def _first_mapping_value(
    metadata: Mapping[str, JsonValue],
    *keys: str,
) -> dict[str, JsonValue]:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, Mapping):
            return coerce_json_dict(value)
    return {}


def _mapping_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    return [
        coerce_json_dict(item)
        for item in coerce_json_list(value if isinstance(value, list) else None)
        if isinstance(item, Mapping)
    ]


def _candidate_list(
    value: JsonValue,
    action_results: list[dict[str, JsonValue]] | None = None,
) -> list[dict[str, JsonValue]]:
    candidates = [
        _canonical_action_mapping(item)
        for item in _mapping_list(value)
        if _action_name(item)
    ]
    should_order = any("priority" in candidate for candidate in candidates)
    if should_order and action_results:
        for candidate in candidates:
            latest_result = _latest_action_result(
                action_results,
                _clean_text(candidate.get("action")),
            )
            result = _action_result_status(latest_result)
            if result:
                candidate["lastResult"] = result
    if should_order:
        for candidate in candidates:
            candidate.setdefault("recommended", False)
    if should_order:
        candidates.sort(key=_candidate_sort_key)
    return candidates


def _action_result_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    return [
        _canonical_action_mapping(item)
        for item in _mapping_list(value)
        if _action_name(item) and _action_result_status(item)
    ]


def _first_mapping(value: JsonValue) -> dict[str, JsonValue]:
    items = _mapping_list(value)
    return items[0] if items else {}


def _decision_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    return [_canonical_decision_mapping(item) for item in _mapping_list(value)]


def _canonical_decision_mapping(source: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    result = dict(source)
    decision_kind = _clean_text(
        source.get("decisionKind") or source.get("decision_kind")
    )
    next_action = _clean_text(
        source.get("nextAction") or source.get("next_action")
    )
    driver = _clean_text(source.get("driver") or source.get("decision_driver"))
    result.pop("decision_kind", None)
    result.pop("next_action", None)
    result.pop("decision_driver", None)
    if decision_kind:
        result["decisionKind"] = decision_kind
    if next_action:
        result["nextAction"] = next_action
    if driver:
        result["driver"] = driver
    return result


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
        _action_result_status(latest_selected_result)
        or selected_candidate.get("lastResult")
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
            "sourceType": _source_type(candidate),
            "reason": "selected action failed; switch to next best candidate",
            "switchedFrom": selected_action,
            "triggerResult": result,
        }
        trigger_reason = _clean_text(
            detail_map.get("reason")
            or latest_selected_result.get("triggerReason")
            or latest_selected_result.get("trigger_reason")
        )
        if trigger_reason:
            recommended_action["triggerReason"] = trigger_reason
        trigger_action_driver = _clean_text(
            latest_selected_result.get("driver")
            or latest_selected_result.get("triggerActionDriver")
            or latest_selected_result.get("trigger_action_driver")
        )
        if trigger_action_driver:
            recommended_action["triggerActionDriver"] = trigger_action_driver
        trigger_at = _clean_text(
            latest_selected_result.get("t")
            or latest_selected_result.get("triggerAt")
            or latest_selected_result.get("trigger_at")
        )
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


def _enrich_candidates(
    candidates: list[dict[str, JsonValue]],
    *,
    active_decision: Mapping[str, Any],
    recommended_action: Mapping[str, Any],
) -> None:
    selected_action = _clean_text(active_decision.get("nextAction"))
    recommended_action_name = _clean_text(recommended_action.get("action"))
    for candidate in candidates:
        action = _clean_text(candidate.get("action"))
        if action and action == selected_action:
            for key in (
                "driver",
                "reason",
                "strongestHypothesisKind",
                "strongestHypothesisStatus",
                "strongestHypothesisConfidence",
            ):
                if active_decision.get(key) is not None and key not in candidate:
                    candidate[key] = active_decision.get(key)
        if action and action == recommended_action_name:
            for key in (
                "driver",
                "sourceType",
                "switchedFrom",
                "triggerResult",
                "triggerReason",
                "triggerActionDriver",
                "triggerAt",
                "strongestHypothesisKind",
                "strongestHypothesisStatus",
                "strongestHypothesisConfidence",
            ):
                if recommended_action.get(key) is not None and key not in candidate:
                    candidate[key] = recommended_action.get(key)


def _latest_action_result(
    action_results: list[dict[str, JsonValue]],
    action: str,
) -> dict[str, JsonValue]:
    for item in reversed(action_results):
        if _action_name(item) == action:
            return item
    return {}


def _canonical_action_mapping(source: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    result = dict(source)
    action = _action_name(source)
    result.pop("taskAction", None)
    result.pop("task_action", None)
    if action:
        result["action"] = action
    return result


def _action_name(source: Mapping[str, Any]) -> str:
    return _clean_text(
        source.get("action") or source.get("taskAction") or source.get("task_action")
    )


def _action_result_status(source: Mapping[str, Any]) -> str:
    return _clean_text(
        source.get("result")
        or source.get("triggerResult")
        or source.get("trigger_result")
    )


def _candidate_sort_key(candidate: Mapping[str, JsonValue]) -> tuple[float, str]:
    priority = candidate.get("priority")
    if isinstance(priority, (int, float)):
        priority_value = float(priority)
    elif isinstance(priority, str):
        try:
            priority_value = float(priority)
        except ValueError:
            priority_value = 999.0
    else:
        priority_value = 999.0
    return (priority_value, _clean_text(candidate.get("action")))


def _copy_hypothesis_summary(
    target: dict[str, JsonValue],
    source: Mapping[str, Any],
) -> None:
    for key, alias in (
        ("strongestHypothesisKind", "strongest_hypothesis_kind"),
        ("strongestHypothesisStatus", "strongest_hypothesis_status"),
        ("strongestHypothesisConfidence", "strongest_hypothesis_confidence"),
    ):
        value = source.get(key)
        if value is None:
            value = source.get(alias)
        if key not in target and value is not None:
            target[key] = value


def _source_type(value: Mapping[str, Any]) -> str:
    return _clean_text(value.get("sourceType") or value.get("source_type"))


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
