from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    normalized: list[str] = []
    for raw in values:
        value = _clean_text(raw)
        if value:
            normalized.append(value)
    return list(dict.fromkeys(normalized))


def _resume_context(payload: Mapping[str, Any]) -> dict[str, Any]:
    session_context = payload.get("sessionContext")
    if isinstance(session_context, Mapping):
        resume_context = session_context.get("resumeContext")
        if isinstance(resume_context, Mapping):
            return dict(resume_context)
    resume_context = payload.get("resumeContext")
    if isinstance(resume_context, Mapping):
        return dict(resume_context)

    fallback: dict[str, Any] = {}
    run_id = _clean_text(payload.get("resumeFromRunId"))
    checkpoint_id = _clean_text(payload.get("resumeFromCheckpointId"))
    summary = _clean_text(payload.get("resumeSummary"))
    if run_id:
        fallback["runId"] = run_id
    if checkpoint_id:
        fallback["checkpointId"] = checkpoint_id
    if summary:
        fallback["summary"] = summary
    return fallback



def _blackboard_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = payload.get("blackboardSnapshot")
    if not isinstance(snapshot, Mapping):
        return {}
    normalized = dict(snapshot)
    pending = normalized.get("pendingVerifications")
    if not isinstance(pending, list):
        pending = normalized.get("pending_verifications")
    normalized["pendingVerifications"] = list(pending) if isinstance(pending, list) else []
    facts = normalized.get("facts")
    normalized["facts"] = list(facts) if isinstance(facts, list) else []
    recommended_action = normalized.get("recommendedAction")
    if not isinstance(recommended_action, Mapping):
        recommended_action = normalized.get("recommended_action")
    normalized["recommendedAction"] = (
        dict(recommended_action)
        if isinstance(recommended_action, Mapping)
        else {}
    )
    return normalized


def _blackboard_recommended_action(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    recommended = snapshot.get("recommendedAction")
    return dict(recommended) if isinstance(recommended, Mapping) else {}


def _blackboard_hypotheses(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    hypotheses = snapshot.get("hypotheses")
    if not isinstance(hypotheses, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in hypotheses:
        if isinstance(item, Mapping):
            normalized.append(dict(item))
    return normalized


def _best_blackboard_hypothesis(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    status_rank = {
        "supported": 0,
        "active": 1,
    }
    best: dict[str, Any] = {}
    best_key: tuple[int, float, str] | None = None
    for item in _blackboard_hypotheses(snapshot):
        kind = _clean_text(item.get("kind"))
        status = _clean_text(item.get("status")).lower()
        if not kind or status not in status_rank:
            continue
        try:
            confidence = float(item.get("confidence") or 0.0)
        except Exception:
            confidence = 0.0
        key = (status_rank[status], -confidence, kind)
        if best_key is None or key < best_key:
            best_key = key
            best = item
    return best


def strongest_hypothesis_contract(
    control_decision: Mapping[str, Any] | None,
    blackboard_snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    decision = control_decision if isinstance(control_decision, Mapping) else {}
    snapshot = blackboard_snapshot if isinstance(blackboard_snapshot, Mapping) else {}
    facts = decision.get("facts")
    normalized_facts = list(facts) if isinstance(facts, list) else []

    strongest_kind = ""
    strongest_status = ""
    strongest_confidence: float | None = None
    for raw in normalized_facts:
        fact = _clean_text(raw)
        if fact.startswith("strongestHypothesisKind="):
            strongest_kind = fact.split("=", 1)[1].strip()
        elif fact.startswith("strongestHypothesisStatus="):
            strongest_status = fact.split("=", 1)[1].strip()
        elif fact.startswith("strongestHypothesisConfidence="):
            raw_confidence = fact.split("=", 1)[1].strip()
            if raw_confidence:
                try:
                    strongest_confidence = float(raw_confidence)
                except Exception:
                    strongest_confidence = None

    strongest_hypothesis: dict[str, Any] = {}
    if strongest_kind:
        for item in _blackboard_hypotheses(snapshot):
            item_kind = _clean_text(item.get("kind"))
            item_status = _clean_text(item.get("status"))
            if item_kind != strongest_kind:
                continue
            if strongest_status and item_status != strongest_status:
                continue
            strongest_hypothesis = item
            break
    if not strongest_hypothesis:
        strongest_hypothesis = _best_blackboard_hypothesis(snapshot)
        strongest_kind = strongest_kind or _clean_text(strongest_hypothesis.get("kind"))
        strongest_status = strongest_status or _clean_text(strongest_hypothesis.get("status"))

    contract: dict[str, Any] = {}
    if strongest_kind:
        contract["kind"] = strongest_kind
    if strongest_status:
        contract["status"] = strongest_status
    try:
        confidence = float(strongest_hypothesis.get("confidence"))
    except Exception:
        confidence = strongest_confidence
    if confidence is not None:
        contract["confidence"] = confidence
    return contract


def build_control_decision_parts(
    control_decision: Mapping[str, Any] | None,
    blackboard_snapshot: Mapping[str, Any] | None,
    *,
    endpoint_fallback: str = "",
) -> list[str]:
    """Build the ``[control_decision]`` field lines shared by the cli / web / mcp
    dispatcher-hint producers.

    The three entry points differ only in how they adapt their input (kwargs /
    task dict / TaskEntry) and how they wrap the result (base-hint prefix,
    resume blocks, decision-block gating). This is the byte-identical core they
    all duplicated: the field chain derived purely from ``(decision, snapshot)``.

    ``endpoint_fallback`` reproduces the mcp-only behaviour of falling back to
    ``handoff["endpoint"]`` when ``nextAction == probe_discovered_endpoint`` and
    the snapshot yields no ``discovered_endpoint`` fact. cli/web pass ``""`` and
    so are unaffected.
    """
    decision = control_decision if isinstance(control_decision, Mapping) else {}
    snapshot = blackboard_snapshot if isinstance(blackboard_snapshot, Mapping) else {}
    decision_parts: list[str] = []
    if str(decision.get("decisionKind") or "").strip():
        decision_parts.append(f"decisionKind={str(decision.get('decisionKind') or '').strip()}")
    if str(decision.get("nextAction") or "").strip():
        decision_parts.append(f"nextAction={str(decision.get('nextAction') or '').strip()}")
    if str(decision.get("driver") or "").strip():
        decision_parts.append(f"driver={str(decision.get('driver') or '').strip()}")
    if str(decision.get("reason") or "").strip():
        decision_parts.append(f"reason={str(decision.get('reason') or '').strip()}")
    strongest_hypothesis = strongest_hypothesis_contract(decision, snapshot)
    if str(strongest_hypothesis.get("kind") or "").strip():
        decision_parts.append(
            f"strongestHypothesisKind={str(strongest_hypothesis.get('kind') or '').strip()}"
        )
    if str(strongest_hypothesis.get("status") or "").strip():
        decision_parts.append(
            f"strongestHypothesisStatus={str(strongest_hypothesis.get('status') or '').strip()}"
        )
    if strongest_hypothesis.get("confidence") is not None:
        decision_parts.append(
            f"strongestHypothesisConfidence={strongest_hypothesis.get('confidence')}"
        )
    next_action = str(decision.get("nextAction") or "").strip()
    if next_action == "probe_discovered_endpoint":
        endpoint = next(
            (
                str(item.get("value") or "").strip()
                for item in list(snapshot.get("facts") or [])
                if isinstance(item, dict) and str(item.get("kind") or "").strip() == "discovered_endpoint"
            ),
            "",
        )
        if not endpoint:
            endpoint = str(endpoint_fallback or "").strip()
        if endpoint:
            decision_parts.append(f"endpoint={endpoint}")
    if next_action == "verify_runtime_signal":
        runtime_flag = next(
            (
                str(item.get("value") or "").strip()
                for item in list(snapshot.get("pending_verifications") or [])
                if isinstance(item, dict) and str(item.get("kind") or "").strip() == "runtime_flag"
            ),
            "",
        )
        if runtime_flag:
            decision_parts.append(f"runtimeFlag={runtime_flag}")
    if next_action == "verify_or_submit_flag":
        verified_flag = next(
            (
                str(item.get("value") or "").strip()
                for item in list(snapshot.get("facts") or [])
                if isinstance(item, dict) and str(item.get("kind") or "").strip() == "verified_flag"
            ),
            "",
        )
        if verified_flag:
            decision_parts.append(f"verifiedFlag={verified_flag}")
    return decision_parts


def _hypothesis_contract(
    hypothesis: Mapping[str, Any],
    *,
    has_local_assets: bool,
) -> dict[str, str]:
    kind = _clean_text(hypothesis.get("kind"))
    if not kind:
        return {}
    if kind == "generic_web_recon":
        return {
            "decisionKind": "explore_first",
            "nextAction": "collect_initial_facts",
            "driver": f"blackboard.hypothesis.{kind}",
            "reason": "strongest blackboard hypothesis favors further reconnaissance",
        }
    if kind == "backup_source_leak" and has_local_assets:
        return {
            "decisionKind": "direct_execute",
            "nextAction": "bootstrap_local_assets",
            "driver": f"blackboard.hypothesis.{kind}",
            "reason": "strongest blackboard hypothesis favors local asset bootstrap",
        }
    endpoint_probe_hypotheses = {
        "auth_form_sqli",
        "backup_source_leak",
        "file_read_endpoint",
        "generic_web_recon_followup",
        "hash_guarded_file_read",
        "hash_reconstruction_attack",
        "hint_chain_followup",
        "path_traversal",
    }
    if kind in endpoint_probe_hypotheses:
        return {
            "decisionKind": "direct_execute",
            "nextAction": "probe_discovered_endpoint",
            "driver": f"blackboard.hypothesis.{kind}",
            "reason": "strongest blackboard hypothesis favors endpoint probing",
        }
    return {}


def _suppressed_recommendation(
    snapshot: Mapping[str, Any],
    *,
    suppressed_by: str,
) -> dict[str, Any]:
    recommended = _blackboard_recommended_action(snapshot)
    action = _clean_text(recommended.get("action"))
    if not action:
        return {}
    suppressed: dict[str, Any] = {"action": action, "suppressedBy": _clean_text(suppressed_by)}
    driver = _clean_text(recommended.get("driver"))
    reason = _clean_text(recommended.get("reason"))
    if driver:
        suppressed["driver"] = driver
    if reason:
        suppressed["reason"] = reason
    return suppressed


def _facts_with_suppressed_recommendation(
    facts: list[str],
    suppressed_recommendation: Mapping[str, Any] | None,
) -> list[str]:
    if not isinstance(suppressed_recommendation, Mapping) or not suppressed_recommendation:
        return list(facts)
    merged = list(facts)
    merged.append("blackboard.recommended_action=suppressed")
    suppressed_by = _clean_text(suppressed_recommendation.get("suppressedBy"))
    if suppressed_by:
        merged.append(f"recommendedActionSuppressedBy={suppressed_by}")
    return list(dict.fromkeys(merged))


def _blackboard_fact(
    facts: list[Mapping[str, Any]],
    kind: str,
) -> dict[str, Any]:
    normalized_kind = _clean_text(kind)
    for item in facts:
        if _clean_text(item.get("kind")) == normalized_kind:
            return dict(item)
    return {}


def _blackboard_fact_value(
    facts: list[Mapping[str, Any]],
    kind: str,
) -> str:
    return _clean_text(_blackboard_fact(facts, kind).get("value"))


def _derived_target_origin(payload: Mapping[str, Any], *, resume_context: Mapping[str, Any] | None = None) -> str:
    resume_context = resume_context or {}
    has_lineage = bool(
        _clean_text(payload.get("sourceRunId"))
        or _clean_text(payload.get("resumeFromRunId"))
        or _clean_text(payload.get("resumeFromCheckpointId"))
        or _clean_text(resume_context.get("runId"))
        or _clean_text(resume_context.get("checkpointId"))
    )
    return "inherited_lineage" if has_lineage else "runtime_derived"


def resolve_control_decision(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}

    explicit_target = _clean_text(payload.get("target"))
    target = explicit_target
    mode = _clean_text(payload.get("mode")).lower()
    challenge_path = _clean_text(payload.get("challengePath"))
    artifact_paths = _normalize_string_list(payload.get("artifactPaths"))
    resume_context = _resume_context(payload)
    blackboard = _blackboard_snapshot(payload)
    blackboard_facts = [item for item in list(blackboard.get("facts") or []) if isinstance(item, Mapping)]
    blackboard_pending = [item for item in list(blackboard.get("pendingVerifications") or []) if isinstance(item, Mapping)]
    blackboard_recommended_action = _blackboard_recommended_action(blackboard)
    strongest_hypothesis = _best_blackboard_hypothesis(blackboard)
    blackboard_derived_target_fact = _blackboard_fact(blackboard_facts, "derived_target")
    blackboard_derived_target = _clean_text(blackboard_derived_target_fact.get("value"))
    direct_derived_target = _clean_text(payload.get("derivedTarget"))
    direct_derived_target_source = _clean_text(payload.get("derivedTargetSource"))
    derived_target_origin = ""
    derived_target_driver = ""
    derived_target_reason = ""
    if not target and direct_derived_target:
        derived_target_origin = _derived_target_origin(payload, resume_context=resume_context)
        target = direct_derived_target
        derived_target_driver = f"task.derived_target.{derived_target_origin}"
        derived_target_reason = "derived target available for initial fact collection"
    elif not target and blackboard_derived_target:
        derived_target_origin = _derived_target_origin(payload, resume_context=resume_context)
        target = blackboard_derived_target
        derived_target_driver = f"blackboard.derived_target.{derived_target_origin}"
        derived_target_reason = "derived target available for initial fact collection"

    has_resume_context = bool(
        _clean_text(resume_context.get("runId"))
        or _clean_text(resume_context.get("checkpointId"))
    )
    has_local_assets = bool(challenge_path or artifact_paths)

    facts: list[str] = []
    if mode:
        facts.append(f"mode={mode}")
    if target:
        facts.append(f"target={target}")
    if challenge_path:
        facts.append(f"challengePath={challenge_path}")
    if artifact_paths:
        facts.append("artifactPaths=" + "; ".join(artifact_paths))
    if has_resume_context:
        facts.append("resumeContext=present")
    if blackboard_derived_target:
        facts.append("blackboard.derived_target=present")
    if derived_target_origin:
        facts.append(f"derivedTargetOrigin={derived_target_origin}")
    if direct_derived_target_source:
        facts.append(f"derivedTargetSource={direct_derived_target_source}")
    blackboard_derived_target_source = _clean_text(blackboard_derived_target_fact.get("source"))
    if blackboard_derived_target_source and not direct_derived_target_source and blackboard_derived_target:
        facts.append(f"derivedTargetSource={blackboard_derived_target_source}")
    if strongest_hypothesis:
        facts.append("blackboard.hypothesis=present")
        strongest_kind = _clean_text(strongest_hypothesis.get("kind"))
        strongest_status = _clean_text(strongest_hypothesis.get("status"))
        if strongest_kind:
            facts.append(f"strongestHypothesisKind={strongest_kind}")
        if strongest_status:
            facts.append(f"strongestHypothesisStatus={strongest_status}")

    if any(_clean_text(item.get("kind")) == "verified_flag" for item in blackboard_facts):
        facts.append("blackboard.verified_flag=present")
        suppressed_recommendation = _suppressed_recommendation(
            blackboard,
            suppressed_by="blackboard.verified_flag",
        )
        return {
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "verified flag already present in blackboard",
            "nextAction": "verify_or_submit_flag",
            "driver": "blackboard.verified_flag",
            "facts": _facts_with_suppressed_recommendation(facts, suppressed_recommendation),
            "suppressedRecommendation": suppressed_recommendation,
        }

    if any(_clean_text(item.get("kind")) == "runtime_flag" for item in blackboard_pending):
        facts.append("blackboard.runtime_flag=present")
        suppressed_recommendation = _suppressed_recommendation(
            blackboard,
            suppressed_by="blackboard.runtime_flag",
        )
        return {
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "runtime flag pending verification in blackboard",
            "nextAction": "verify_runtime_signal",
            "driver": "blackboard.runtime_flag",
            "facts": _facts_with_suppressed_recommendation(facts, suppressed_recommendation),
            "suppressedRecommendation": suppressed_recommendation,
        }

    if has_resume_context:
        suppressed_recommendation = _suppressed_recommendation(
            blackboard,
            suppressed_by="task.resume_context",
        )
        return {
            "shouldRun": True,
            "decisionKind": "resume_execute",
            "reason": "resume context available",
            "nextAction": "resume_from_checkpoint",
            "driver": "task.resume_context",
            "facts": _facts_with_suppressed_recommendation(facts, suppressed_recommendation),
            "suppressedRecommendation": suppressed_recommendation,
        }

    if any(_clean_text(item.get("kind")) == "resume_bootstrap_hint" for item in blackboard_facts):
        facts.append("blackboard.resume_bootstrap_hint=present")
        suppressed_recommendation = _suppressed_recommendation(
            blackboard,
            suppressed_by="blackboard.resume_bootstrap_hint",
        )
        return {
            "shouldRun": True,
            "decisionKind": "resume_execute",
            "reason": "resume bootstrap hint present in blackboard",
            "nextAction": "resume_from_checkpoint",
            "driver": "blackboard.resume_bootstrap_hint",
            "facts": _facts_with_suppressed_recommendation(facts, suppressed_recommendation),
            "suppressedRecommendation": suppressed_recommendation,
        }

    recommended_action = _clean_text(blackboard_recommended_action.get("action"))
    recommended_driver = _clean_text(blackboard_recommended_action.get("driver"))
    recommended_source_type = _clean_text(blackboard_recommended_action.get("sourceType"))
    recommended_reason = _clean_text(blackboard_recommended_action.get("reason"))
    recommended_switched_from = _clean_text(blackboard_recommended_action.get("switchedFrom"))
    recommended_trigger_reason = _clean_text(blackboard_recommended_action.get("triggerReason"))
    recommended_trigger_action_driver = _clean_text(
        blackboard_recommended_action.get("triggerActionDriver")
    )
    recommended_trigger_at = _clean_text(blackboard_recommended_action.get("triggerAt"))
    recommended_strongest_kind = _clean_text(
        blackboard_recommended_action.get("strongestHypothesisKind")
    )
    recommended_strongest_status = _clean_text(
        blackboard_recommended_action.get("strongestHypothesisStatus")
    )
    recommended_strongest_confidence = blackboard_recommended_action.get(
        "strongestHypothesisConfidence"
    )
    recommended_allowlist = {
        "exploit_identified_engine": "direct_execute",
        "probe_discovered_endpoint": "direct_execute",
        "validate_leaked_secret": "direct_execute",
        "collect_initial_facts": "explore_first",
        "bootstrap_local_assets": "direct_execute",
    }
    if mode == "ctf" and recommended_action in recommended_allowlist:
        facts.append("blackboard.recommended_action=present")
        if recommended_source_type:
            facts.append(f"recommendedActionSourceType={recommended_source_type}")
        if recommended_switched_from:
            facts.append(f"recommendedActionSwitchedFrom={recommended_switched_from}")
        if recommended_trigger_reason:
            facts.append(f"recommendedActionTriggerReason={recommended_trigger_reason}")
        if recommended_trigger_action_driver:
            facts.append(
                f"recommendedActionTriggerActionDriver={recommended_trigger_action_driver}"
            )
        if recommended_trigger_at:
            facts.append(f"recommendedActionTriggerAt={recommended_trigger_at}")
        if recommended_strongest_kind:
            facts.append(f"strongestHypothesisKind={recommended_strongest_kind}")
        if recommended_strongest_status:
            facts.append(f"strongestHypothesisStatus={recommended_strongest_status}")
        if recommended_strongest_confidence is not None:
            facts.append(f"strongestHypothesisConfidence={recommended_strongest_confidence}")
        return {
            "shouldRun": True,
            "decisionKind": recommended_allowlist[recommended_action],
            "reason": recommended_reason or "recommended action present in blackboard",
            "nextAction": recommended_action,
            "driver": recommended_driver or "blackboard.recommended_action",
            "facts": facts,
        }

    if mode == "ctf" and any(_clean_text(item.get("kind")) == "identified_engine" for item in blackboard_facts):
        facts.append("blackboard.identified_engine=present")
        return {
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "identified engine present in blackboard",
            "nextAction": "exploit_identified_engine",
            "driver": "blackboard.identified_engine",
            "facts": facts,
        }

    if mode == "ctf" and any(_clean_text(item.get("kind")) == "discovered_endpoint" for item in blackboard_facts):
        facts.append("blackboard.discovered_endpoint=present")
        return {
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "discovered endpoint present in blackboard",
            "nextAction": "probe_discovered_endpoint",
            "driver": "blackboard.discovered_endpoint",
            "facts": facts,
        }

    if mode == "ctf" and any(_clean_text(item.get("kind")) == "leaked_secret" for item in blackboard_facts):
        facts.append("blackboard.leaked_secret=present")
        return {
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "leaked secret present in blackboard",
            "nextAction": "validate_leaked_secret",
            "driver": "blackboard.leaked_secret",
            "facts": facts,
        }

    if mode == "ctf" and strongest_hypothesis:
        contract = _hypothesis_contract(strongest_hypothesis, has_local_assets=has_local_assets)
        if contract:
            return {
                "shouldRun": True,
                "decisionKind": contract["decisionKind"],
                "reason": contract["reason"],
                "nextAction": contract["nextAction"],
                "driver": contract["driver"],
                "facts": facts,
            }

    if mode == "ctf" and any(
        _clean_text(item.get("kind")) == "initial_fact_collection_requested"
        for item in blackboard_facts
    ):
        facts.append("blackboard.initial_fact_collection_requested=present")
        return {
            "shouldRun": True,
            "decisionKind": "explore_first",
            "reason": "initial fact collection already requested in blackboard",
            "nextAction": "collect_initial_facts",
            "driver": "blackboard.initial_fact_collection_requested",
            "facts": facts,
        }

    if mode == "ctf" and has_local_assets:
        return {
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "ctf local assets available",
            "nextAction": "bootstrap_local_assets",
            "facts": facts,
        }

    if not target and not has_local_assets:
        return {
            "shouldRun": False,
            "decisionKind": "blocked",
            "reason": "missing target and local assets",
            "nextAction": "await_input",
            "facts": facts,
        }

    return {
        "shouldRun": True,
        "decisionKind": "explore_first",
        "reason": derived_target_reason or "need initial fact collection",
        "nextAction": "collect_initial_facts",
        "driver": derived_target_driver,
        "facts": facts,
    }


def build_decision_record(
    decision: Mapping[str, Any] | None,
    *,
    source: str,
) -> dict[str, Any]:
    decision = decision or {}
    suppressed_recommendation = (
        dict(decision.get("suppressedRecommendation") or {})
        if isinstance(decision.get("suppressedRecommendation"), Mapping)
        else {}
    )
    return {
        "kind": _clean_text(decision.get("decisionKind")),
        "reason": _clean_text(decision.get("reason")),
        "nextAction": _clean_text(decision.get("nextAction")),
        "driver": _clean_text(decision.get("driver")),
        "facts": _normalize_string_list(decision.get("facts")),
        "suppressedRecommendation": suppressed_recommendation,
        "source": _clean_text(source),
    }
