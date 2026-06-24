"""Decision / provenance summary builders split out of web_server (god-module 分簇).

Pure functions projecting a (control_decision, blackboard_snapshot) pair into the
summary dicts consumed by the task serialization / detail / trace payloads. They were
physically moved out of web_server.py behind preserved names: web_server re-imports every
symbol here into its own namespace so existing ``web_server._build_*`` references and the
test monkeypatch points keep resolving unchanged.
"""
from __future__ import annotations

from typing import Any

from .blackboard_lite import normalize_blackboard_snapshot
from .control_contract import strongest_hypothesis_contract


def _decision_fact_value(decision: dict[str, Any], prefix: str) -> str | None:
    facts = decision.get("facts")
    if not isinstance(facts, list):
        return None
    for raw in facts:
        fact = str(raw or "").strip()
        if fact.startswith(prefix):
            value = fact.split("=", 1)[1].strip()
            return value or None
    return None


def _build_decision_provenance_summary(
    control_decision: Any,
    blackboard_snapshot: Any,
) -> dict[str, Any]:
    decision = dict(control_decision or {}) if isinstance(control_decision, dict) else {}
    snapshot = normalize_blackboard_snapshot(
        blackboard_snapshot if isinstance(blackboard_snapshot, dict) else {}
    )
    recommended_action = (
        dict(snapshot.get("recommendedAction") or {})
        if isinstance(snapshot.get("recommendedAction"), dict)
        else {}
    )

    strongest_hypothesis = strongest_hypothesis_contract(decision, snapshot)
    strongest_kind = (
        str(recommended_action.get("strongestHypothesisKind") or "").strip()
        or str(strongest_hypothesis.get("kind") or "").strip()
        or None
    )
    strongest_status = (
        str(recommended_action.get("strongestHypothesisStatus") or "").strip()
        or str(strongest_hypothesis.get("status") or "").strip()
        or None
    )
    strongest_confidence = recommended_action.get("strongestHypothesisConfidence")
    if strongest_confidence is None:
        strongest_confidence = strongest_hypothesis.get("confidence")

    if strongest_confidence is not None:
        try:
            strongest_confidence = float(strongest_confidence)
        except Exception:
            strongest_confidence = None

    return {
        "recommendedActionSourceType": (
            str(recommended_action.get("sourceType") or "").strip()
            or _decision_fact_value(decision, "recommendedActionSourceType=")
        ),
        "recommendedActionSwitchedFrom": (
            str(recommended_action.get("switchedFrom") or "").strip()
            or _decision_fact_value(decision, "recommendedActionSwitchedFrom=")
        ),
        "recommendedActionTriggerReason": (
            str(recommended_action.get("triggerReason") or "").strip()
            or _decision_fact_value(decision, "recommendedActionTriggerReason=")
        ),
        "recommendedActionTriggerActionDriver": (
            str(recommended_action.get("triggerActionDriver") or "").strip()
            or _decision_fact_value(decision, "recommendedActionTriggerActionDriver=")
        ),
        "recommendedActionTriggerAt": (
            str(recommended_action.get("triggerAt") or "").strip()
            or _decision_fact_value(decision, "recommendedActionTriggerAt=")
        ),
        "strongestHypothesisKind": strongest_kind,
        "strongestHypothesisStatus": strongest_status,
        "strongestHypothesisConfidence": strongest_confidence,
    }


def _build_exploit_provenance_summary(blackboard_snapshot: Any) -> dict[str, Any]:
    snapshot = normalize_blackboard_snapshot(
        blackboard_snapshot if isinstance(blackboard_snapshot, dict) else {}
    )
    for item in reversed(list(snapshot.get("facts") or [])):
        if not isinstance(item, dict):
            continue
        if str(item.get("kind") or "").strip() != "source_leak_exploit_candidate":
            continue
        exploit_kind = str(item.get("value") or "").strip()
        if not exploit_kind:
            continue
        return {
            "sourceType": "source_leak_exploit_candidate",
            "exploitKind": exploit_kind,
            "observationSource": str(item.get("source") or "").strip() or None,
            "artifactUrl": str(item.get("artifactUrl") or "").strip() or None,
        }
    for item in reversed(list(snapshot.get("facts") or [])):
        if not isinstance(item, dict):
            continue
        if str(item.get("kind") or "").strip() != "local_challenge_source_hint":
            continue
        exploit_kind = str(item.get("exploitType") or "").strip()
        if not exploit_kind:
            continue
        return {
            "sourceType": "local_challenge_source_hint",
            "exploitKind": exploit_kind,
            "observationSource": str(item.get("source") or "").strip() or None,
            "artifactUrl": str(item.get("artifactUrl") or "").strip() or None,
        }
    return {
        "sourceType": None,
        "exploitKind": None,
        "observationSource": None,
        "artifactUrl": None,
    }


def _build_recommended_action_summary(blackboard_snapshot: Any) -> dict[str, Any]:
    snapshot = normalize_blackboard_snapshot(
        blackboard_snapshot if isinstance(blackboard_snapshot, dict) else {}
    )
    recommended_action = (
        dict(snapshot.get("recommendedAction") or {})
        if isinstance(snapshot.get("recommendedAction"), dict)
        else {}
    )
    action = str(recommended_action.get("action") or "").strip() or None
    driver = str(recommended_action.get("driver") or "").strip() or None
    source_type = str(recommended_action.get("sourceType") or "").strip() or None
    reason = str(recommended_action.get("reason") or "").strip() or None
    switched_from = str(recommended_action.get("switchedFrom") or "").strip() or None
    trigger_result = str(recommended_action.get("triggerResult") or "").strip() or None
    trigger_reason = str(recommended_action.get("triggerReason") or "").strip() or None

    summary: str | None = None
    if action:
        summary = action
        if driver:
            summary = f"{summary} via {driver}"
        if switched_from:
            summary = f"{summary} · from {switched_from}"
        if trigger_result:
            summary = f"{summary} · after {trigger_result}"

    return {
        "action": action,
        "driver": driver,
        "sourceType": source_type,
        "reason": reason,
        "switchedFrom": switched_from,
        "triggerResult": trigger_result,
        "triggerReason": trigger_reason,
        "summary": summary,
    }


def _build_candidate_summary(blackboard_snapshot: Any) -> dict[str, Any]:
    snapshot = normalize_blackboard_snapshot(
        blackboard_snapshot if isinstance(blackboard_snapshot, dict) else {}
    )
    active_decision = (
        dict(snapshot.get("activeDecision") or {})
        if isinstance(snapshot.get("activeDecision"), dict)
        else {}
    )
    recommended_action = (
        dict(snapshot.get("recommendedAction") or {})
        if isinstance(snapshot.get("recommendedAction"), dict)
        else {}
    )
    candidates = [
        dict(item)
        for item in list(snapshot.get("candidates") or [])
        if isinstance(item, dict) and str(item.get("action") or "").strip()
    ]
    candidate_actions = [str(item.get("action") or "").strip() for item in candidates]
    total_candidates = len(candidate_actions)
    active_action = str(active_decision.get("nextAction") or "").strip() or None
    recommended_candidate = str(recommended_action.get("action") or "").strip() or None
    noun = "candidate" if total_candidates == 1 else "candidates"
    summary = f"{total_candidates} {noun}"
    if active_action:
        summary = f"{summary} · active={active_action}"
    if recommended_candidate:
        summary = f"{summary} · recommended={recommended_candidate}"
    return {
        "activeAction": active_action,
        "recommendedAction": recommended_candidate,
        "candidateActions": candidate_actions,
        "totalCandidates": total_candidates,
        "summary": summary,
    }


def _build_last_action_result_summary(blackboard_snapshot: Any) -> dict[str, Any]:
    snapshot = normalize_blackboard_snapshot(
        blackboard_snapshot if isinstance(blackboard_snapshot, dict) else {}
    )
    latest_result: dict[str, Any] = {}
    for item in reversed(list(snapshot.get("actionResults") or [])):
        if isinstance(item, dict):
            latest_result = dict(item)
            break
    action = str(latest_result.get("action") or "").strip() or None
    result = str(latest_result.get("result") or "").strip() or None
    driver = str(latest_result.get("driver") or "").strip() or None
    expected_action = str(latest_result.get("expectedAction") or "").strip() or None
    alignment = str(latest_result.get("alignment") or "").strip() or None
    details = (
        dict(latest_result.get("details") or {})
        if isinstance(latest_result.get("details"), dict)
        else {}
    )
    reason = str(details.get("reason") or "").strip() or None

    summary: str | None = None
    if action and result:
        summary = f"{action} {result}"
        if driver:
            summary = f"{summary} via {driver}"
        if alignment:
            summary = f"{summary} · alignment={alignment}"

    return {
        "action": action,
        "result": result,
        "driver": driver,
        "expectedAction": expected_action,
        "alignment": alignment,
        "reason": reason,
        "summary": summary,
    }


def _build_pending_verification_summary(blackboard_snapshot: Any) -> dict[str, Any]:
    snapshot = normalize_blackboard_snapshot(
        blackboard_snapshot if isinstance(blackboard_snapshot, dict) else {}
    )
    pending = [
        dict(item)
        for item in list(snapshot.get("pendingVerifications") or [])
        if isinstance(item, dict)
    ]
    count = len(pending)
    latest = pending[-1] if pending else {}
    latest_kind = str(latest.get("kind") or "").strip() or None
    latest_value = str(latest.get("value") or "").strip() or None
    latest_source = str(latest.get("source") or "").strip() or None
    latest_rationale = str(latest.get("rationale") or "").strip() or None
    noun = "pending verification" if count == 1 else "pending verifications"
    summary = f"{count} {noun}"
    if latest_kind:
        summary = f"{summary} · latest={latest_kind}"
        if latest_source:
            summary = f"{summary} from {latest_source}"
    return {
        "count": count,
        "latestKind": latest_kind,
        "latestValue": latest_value,
        "latestSource": latest_source,
        "latestRationale": latest_rationale,
        "summary": summary,
    }


def _build_strongest_hypothesis_summary(
    control_decision: Any,
    blackboard_snapshot: Any,
) -> dict[str, Any]:
    snapshot = normalize_blackboard_snapshot(
        blackboard_snapshot if isinstance(blackboard_snapshot, dict) else {}
    )
    decision = dict(control_decision or {}) if isinstance(control_decision, dict) else {}
    strongest = strongest_hypothesis_contract(decision, snapshot)
    kind = str(strongest.get("kind") or "").strip() or None
    status = str(strongest.get("status") or "").strip() or None
    confidence = strongest.get("confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except Exception:
            confidence = None
    summary: str | None = None
    if kind:
        suffix_parts: list[str] = []
        if status:
            suffix_parts.append(status)
        if confidence is not None:
            suffix_parts.append(f"{confidence:.2f}")
        summary = kind
        if suffix_parts:
            summary = f"{summary} [{' / '.join(suffix_parts)}]".replace(" / ", "/")
    return {
        "kind": kind,
        "status": status,
        "confidence": confidence,
        "summary": summary,
    }


def _build_suppressed_recommendation_summary(
    control_decision: Any,
    blackboard_snapshot: Any,
) -> dict[str, Any]:
    decision = dict(control_decision or {}) if isinstance(control_decision, dict) else {}
    snapshot = normalize_blackboard_snapshot(
        blackboard_snapshot if isinstance(blackboard_snapshot, dict) else {}
    )
    active_decision = (
        dict(snapshot.get("activeDecision") or {})
        if isinstance(snapshot.get("activeDecision"), dict)
        else {}
    )
    suppressed = (
        dict(decision.get("suppressedRecommendation") or {})
        if isinstance(decision.get("suppressedRecommendation"), dict)
        else dict(active_decision.get("suppressedRecommendation") or {})
        if isinstance(active_decision.get("suppressedRecommendation"), dict)
        else {}
    )
    action = str(suppressed.get("action") or "").strip() or None
    driver = str(suppressed.get("driver") or "").strip() or None
    reason = str(suppressed.get("reason") or "").strip() or None
    suppressed_by = str(suppressed.get("suppressedBy") or "").strip() or None
    summary: str | None = None
    if action and suppressed_by:
        summary = f"{action} suppressed by {suppressed_by}"
    elif action:
        summary = action
    return {
        "action": action,
        "driver": driver,
        "reason": reason,
        "suppressedBy": suppressed_by,
        "summary": summary,
    }


def _build_active_decision_summary(blackboard_snapshot: Any) -> dict[str, Any]:
    snapshot = normalize_blackboard_snapshot(
        blackboard_snapshot if isinstance(blackboard_snapshot, dict) else {}
    )
    active_decision = (
        dict(snapshot.get("activeDecision") or {})
        if isinstance(snapshot.get("activeDecision"), dict)
        else {}
    )
    decision_kind = str(active_decision.get("decisionKind") or "").strip() or None
    next_action = str(active_decision.get("nextAction") or "").strip() or None
    driver = str(active_decision.get("driver") or "").strip() or None
    reason = str(active_decision.get("reason") or "").strip() or None
    expected_action = str(active_decision.get("expectedAction") or "").strip() or None
    observed_action = str(active_decision.get("observedAction") or "").strip() or None
    alignment = str(active_decision.get("alignment") or "").strip() or None
    alignment_reason = str(active_decision.get("alignmentReason") or "").strip() or None
    summary: str | None = None
    if decision_kind or next_action or driver:
        summary_parts: list[str] = []
        if decision_kind:
            summary_parts.append(decision_kind)
        if next_action:
            summary_parts.append(f"-> {next_action}" if summary_parts else next_action)
        if driver:
            summary_parts.append(f"via {driver}")
        summary = " ".join(summary_parts) if summary_parts else None
        if summary and observed_action:
            summary = f"{summary} · observed={observed_action}"
        if summary and alignment:
            summary = f"{summary} · alignment={alignment}"
    return {
        "decisionKind": decision_kind,
        "nextAction": next_action,
        "driver": driver,
        "reason": reason,
        "expectedAction": expected_action,
        "observedAction": observed_action,
        "alignment": alignment,
        "alignmentReason": alignment_reason,
        "summary": summary,
    }


def _build_action_path_summary(
    control_decision: Any,
    blackboard_snapshot: Any,
    decision_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = dict(control_decision or {}) if isinstance(control_decision, dict) else {}
    snapshot = normalize_blackboard_snapshot(
        blackboard_snapshot if isinstance(blackboard_snapshot, dict) else {}
    )
    active_decision = (
        dict(snapshot.get("activeDecision") or {})
        if isinstance(snapshot.get("activeDecision"), dict)
        else {}
    )
    provenance = dict(decision_provenance or {}) if isinstance(decision_provenance, dict) else {}

    strongest_hypothesis = strongest_hypothesis_contract(decision, snapshot)
    planned_action = (
        str(active_decision.get("nextAction") or "").strip()
        or str(decision.get("nextAction") or "").strip()
        or None
    )
    observed_action = str(active_decision.get("observedAction") or "").strip() or None
    effective_action = observed_action or planned_action
    strongest_kind = (
        str(active_decision.get("strongestHypothesisKind") or "").strip()
        or str(provenance.get("strongestHypothesisKind") or "").strip()
        or str(strongest_hypothesis.get("kind") or "").strip()
        or None
    )
    strongest_status = (
        str(active_decision.get("strongestHypothesisStatus") or "").strip()
        or str(provenance.get("strongestHypothesisStatus") or "").strip()
        or str(strongest_hypothesis.get("status") or "").strip()
        or None
    )
    strongest_confidence = active_decision.get("strongestHypothesisConfidence")
    if strongest_confidence is None:
        strongest_confidence = provenance.get("strongestHypothesisConfidence")
    if strongest_confidence is None:
        strongest_confidence = strongest_hypothesis.get("confidence")
    if strongest_confidence is not None:
        try:
            strongest_confidence = float(strongest_confidence)
        except Exception:
            strongest_confidence = None

    return {
        "decisionKind": (
            str(active_decision.get("decisionKind") or "").strip()
            or str(decision.get("decisionKind") or "").strip()
            or None
        ),
        "decisionDriver": (
            str(active_decision.get("driver") or "").strip()
            or str(decision.get("driver") or "").strip()
            or None
        ),
        "plannedAction": planned_action,
        "observedAction": observed_action,
        "effectiveAction": effective_action,
        "alignment": str(active_decision.get("alignment") or "").strip() or None,
        "alignmentReason": str(active_decision.get("alignmentReason") or "").strip() or None,
        "switchedFrom": (
            str(active_decision.get("switchedFrom") or "").strip()
            or str(provenance.get("recommendedActionSwitchedFrom") or "").strip()
            or None
        ),
        "triggerReason": (
            str(active_decision.get("triggerReason") or "").strip()
            or str(provenance.get("recommendedActionTriggerReason") or "").strip()
            or None
        ),
        "strongestHypothesisKind": strongest_kind,
        "strongestHypothesisStatus": strongest_status,
        "strongestHypothesisConfidence": strongest_confidence,
    }


def _build_next_action_explanation(
    control_decision: Any,
    action_path_summary: dict[str, Any] | None = None,
    decision_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = dict(control_decision or {}) if isinstance(control_decision, dict) else {}
    action_path = dict(action_path_summary or {}) if isinstance(action_path_summary, dict) else {}
    provenance = dict(decision_provenance or {}) if isinstance(decision_provenance, dict) else {}

    decision_kind = str(
        decision.get("decisionKind")
        or action_path.get("decisionKind")
        or ""
    ).strip()
    next_action = str(
        decision.get("nextAction")
        or action_path.get("plannedAction")
        or action_path.get("effectiveAction")
        or ""
    ).strip()
    driver = str(
        decision.get("driver")
        or action_path.get("decisionDriver")
        or ""
    ).strip()
    reason = str(decision.get("reason") or "").strip() or None
    source_type = str(provenance.get("recommendedActionSourceType") or "").strip() or None
    switched_from = str(
        action_path.get("switchedFrom")
        or provenance.get("recommendedActionSwitchedFrom")
        or ""
    ).strip() or None
    trigger_reason = str(
        action_path.get("triggerReason")
        or provenance.get("recommendedActionTriggerReason")
        or ""
    ).strip() or None
    if not any([decision_kind, next_action, driver, reason, source_type, switched_from, trigger_reason]):
        return {}
    summary_parts = []
    if decision_kind:
        summary_parts.append(decision_kind)
    if next_action:
        summary_parts.append(f"-> {next_action}" if summary_parts else next_action)
    if driver:
        summary_parts.append(f"via {driver}")
    return {
        "decisionKind": decision_kind or None,
        "nextAction": next_action or None,
        "driver": driver or None,
        "reason": reason,
        "sourceType": source_type,
        "switchedFrom": switched_from,
        "triggerReason": trigger_reason,
        "summary": " ".join(summary_parts) if summary_parts else None,
    }


def _build_ingress_handoff_explanation(handoff: Any) -> dict[str, Any]:
    normalized = dict(handoff or {}) if isinstance(handoff, dict) else {}
    decision_kind = str(normalized.get("decisionKind") or "").strip()
    next_action = str(normalized.get("nextAction") or "").strip()
    if not decision_kind and not next_action:
        return {}
    driver = str(normalized.get("driver") or "").strip()
    if not driver and next_action == "bootstrap_local_assets":
        driver = "task.local_assets"
    reason = str(normalized.get("reason") or "").strip()
    if not reason and next_action == "bootstrap_local_assets":
        reason = "local challenge assets available for bootstrap"
    summary_parts = []
    if decision_kind:
        summary_parts.append(decision_kind)
    if next_action:
        summary_parts.append(f"-> {next_action}" if summary_parts else next_action)
    if driver:
        summary_parts.append(f"via {driver}")
    return {
        "decisionKind": decision_kind or None,
        "nextAction": next_action or None,
        "driver": driver or None,
        "reason": reason or None,
        "sourceType": None,
        "switchedFrom": None,
        "triggerReason": None,
        "summary": " ".join(summary_parts) if summary_parts else None,
    }
