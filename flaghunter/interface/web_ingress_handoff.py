"""Ingress handoff construction (debt ledger 第五波·刀19).

Extracted from web_server.py. This single-function themed cut builds the
``ingressHandoff`` payload attached to a task at ingress time: it folds the CTF
challenge context, the control decision and strongest-hypothesis contract, and
the verified-flag / runtime-flag / discovered-endpoint structured fields into a
dict consumed by the dispatcher. It calls only the already-extracted
``_build_ctf_challenge_context`` (web_challenge_context) /
``_task_blackboard_snapshot_for_decision`` (web_control_decision) and the
upstream ``strongest_hypothesis_contract`` (control_contract), so it is
down-closed with zero upward dependency on web_server. web_server re-imports it
so stay-behind callers (the run / replay / retry / continue ingress paths)
resolve unchanged. Note: mcp_tools defines its own independent
``_build_ingress_handoff``; only the web_server copy moves here.
"""

from __future__ import annotations

from typing import Any

from .control_contract import strongest_hypothesis_contract
from .web_challenge_context import _build_ctf_challenge_context
from .web_control_decision import _task_blackboard_snapshot_for_decision


def _build_ingress_handoff(task: dict[str, Any]) -> dict[str, Any]:
    decision = task.get("controlDecision") if isinstance(task.get("controlDecision"), dict) else {}
    blackboard_snapshot = _task_blackboard_snapshot_for_decision(task)
    challenge_context = _build_ctf_challenge_context(task)
    resume_context = (
        dict(challenge_context.get("resumeContext") or {})
        if isinstance(challenge_context.get("resumeContext"), dict)
        else {}
    )
    resume_bootstrap: dict[str, Any] | None = None
    resume_run_id = str(resume_context.get("runId") or "").strip()
    resume_checkpoint_id = str(resume_context.get("checkpointId") or "").strip()
    resume_summary = str(resume_context.get("summary") or "").strip()
    if str(decision.get("decisionKind") or "").strip() == "resume_execute":
        resume_bootstrap = {
            "nextAction": str(decision.get("nextAction") or "").strip() or "resume_from_checkpoint",
            "runId": resume_run_id,
            "checkpointId": resume_checkpoint_id,
            "summary": resume_summary,
        }
    recommended_source_type = ""
    recommended_switched_from = ""
    recommended_trigger_reason = ""
    recommended_trigger_action_driver = ""
    recommended_trigger_at = ""
    for raw_fact in list(decision.get("facts") or []):
        fact = str(raw_fact or "").strip()
        if fact.startswith("recommendedActionSourceType="):
            recommended_source_type = fact.split("=", 1)[1].strip()
        elif fact.startswith("recommendedActionSwitchedFrom="):
            recommended_switched_from = fact.split("=", 1)[1].strip()
        elif fact.startswith("recommendedActionTriggerReason="):
            recommended_trigger_reason = fact.split("=", 1)[1].strip()
        elif fact.startswith("recommendedActionTriggerActionDriver="):
            recommended_trigger_action_driver = fact.split("=", 1)[1].strip()
        elif fact.startswith("recommendedActionTriggerAt="):
            recommended_trigger_at = fact.split("=", 1)[1].strip()
    strongest_hypothesis = strongest_hypothesis_contract(decision, blackboard_snapshot)
    handoff = {
        "decisionKind": str(decision.get("decisionKind") or "").strip(),
        "nextAction": str(decision.get("nextAction") or "").strip(),
        "driver": str(decision.get("driver") or "").strip(),
        "reason": str(decision.get("reason") or "").strip(),
        "challengeContext": challenge_context,
        "resumeBootstrap": resume_bootstrap,
    }
    if recommended_source_type:
        handoff["sourceType"] = recommended_source_type
    if recommended_switched_from:
        handoff["switchedFrom"] = recommended_switched_from
    if recommended_trigger_reason:
        handoff["triggerReason"] = recommended_trigger_reason
    if recommended_trigger_action_driver:
        handoff["triggerActionDriver"] = recommended_trigger_action_driver
    if recommended_trigger_at:
        handoff["triggerAt"] = recommended_trigger_at
    if str(strongest_hypothesis.get("kind") or "").strip():
        handoff["strongestHypothesisKind"] = str(strongest_hypothesis.get("kind") or "").strip()
    if str(strongest_hypothesis.get("status") or "").strip():
        handoff["strongestHypothesisStatus"] = str(strongest_hypothesis.get("status") or "").strip()
    if strongest_hypothesis.get("confidence") is not None:
        handoff["strongestHypothesisConfidence"] = strongest_hypothesis.get("confidence")
    if str(decision.get("nextAction") or "").strip() == "probe_discovered_endpoint":
        endpoint = next(
            (
                str(item.get("value") or "").strip()
                for item in list(blackboard_snapshot.get("facts") or [])
                if isinstance(item, dict) and str(item.get("kind") or "").strip() == "discovered_endpoint"
            ),
            "",
        )
        if endpoint:
            handoff["endpoint"] = endpoint
    if str(decision.get("nextAction") or "").strip() == "verify_runtime_signal":
        runtime_flag = next(
            (
                str(item.get("value") or "").strip()
                for item in list(blackboard_snapshot.get("pendingVerifications") or [])
                if isinstance(item, dict) and str(item.get("kind") or "").strip() == "runtime_flag"
            ),
            "",
        )
        if runtime_flag:
            handoff["runtimeFlag"] = runtime_flag
    if str(decision.get("nextAction") or "").strip() == "verify_or_submit_flag":
        # P1: carry verifiedFlag as a selector for an existing canonical
        # verified claim only. Web ingress/replay cannot use it as proof or
        # create verified state.
        verified_flag = next(
            (
                str(item.get("value") or "").strip()
                for item in list(blackboard_snapshot.get("facts") or [])
                if isinstance(item, dict) and str(item.get("kind") or "").strip() == "verified_flag"
            ),
            "",
        )
        if verified_flag:
            handoff["verifiedFlag"] = verified_flag
    return handoff
