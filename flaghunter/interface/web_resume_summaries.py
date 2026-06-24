"""Resume / session-context summary builders split out of web_server (god-module 分簇).

Down-closed leaf cluster: these 8 pure functions normalize exploit/outcome provenance and
project a session_context / latest-checkpoint into the resume·ingress·checkpoint·runtime
summary dicts. They call only each other + stdlib (no back-call into web_server), so the
split introduces no import cycle. web_server re-imports every name here so existing
``web_server._build_resume_state_summary`` etc. references keep resolving.
"""
from __future__ import annotations

from typing import Any


def _normalize_exploit_provenance(exploit_provenance: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(exploit_provenance, dict):
        return {}
    source_type = str(exploit_provenance.get("sourceType") or "").strip()
    exploit_kind = str(exploit_provenance.get("exploitKind") or "").strip()
    observation_source = str(exploit_provenance.get("observationSource") or "").strip()
    artifact_url = str(exploit_provenance.get("artifactUrl") or "").strip()
    if not any([source_type, exploit_kind, observation_source, artifact_url]):
        return {}
    return {
        "sourceType": source_type or None,
        "exploitKind": exploit_kind or None,
        "observationSource": observation_source or None,
        "artifactUrl": artifact_url or None,
    }


def _exploit_summary_parts(exploit_provenance: dict[str, Any] | None) -> list[str]:
    normalized = _normalize_exploit_provenance(exploit_provenance)
    if not normalized:
        return []
    parts: list[str] = []
    exploit_kind = str(normalized.get("exploitKind") or "").strip()
    source_type = str(normalized.get("sourceType") or "").strip()
    if exploit_kind:
        parts.append(exploit_kind)
    if source_type:
        parts.append(f"source={source_type}")
    return parts


def _normalize_outcome_action_path_summary(action_path_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(action_path_summary, dict):
        return {}
    strongest_hypothesis_kind = str(action_path_summary.get("strongestHypothesisKind") or "").strip()
    strongest_hypothesis_status = str(action_path_summary.get("strongestHypothesisStatus") or "").strip()
    switched_from = str(action_path_summary.get("switchedFrom") or "").strip()
    trigger_reason = str(action_path_summary.get("triggerReason") or "").strip()
    decision_driver = str(action_path_summary.get("decisionDriver") or "").strip()
    effective_action = str(action_path_summary.get("effectiveAction") or "").strip()
    strongest_hypothesis_confidence = action_path_summary.get("strongestHypothesisConfidence")
    if strongest_hypothesis_confidence is not None:
        try:
            strongest_hypothesis_confidence = float(strongest_hypothesis_confidence)
        except Exception:
            strongest_hypothesis_confidence = None
    if not any(
        [
            strongest_hypothesis_kind,
            strongest_hypothesis_status,
            switched_from,
            trigger_reason,
            decision_driver,
            effective_action,
            strongest_hypothesis_confidence is not None,
        ]
    ):
        return {}
    return {
        "strongestHypothesisKind": strongest_hypothesis_kind or None,
        "strongestHypothesisStatus": strongest_hypothesis_status or None,
        "strongestHypothesisConfidence": strongest_hypothesis_confidence,
        "switchedFrom": switched_from or None,
        "triggerReason": trigger_reason or None,
        "decisionDriver": decision_driver or None,
        "effectiveAction": effective_action or None,
    }


def _derive_resume_context_from_latest_checkpoint(
    session_run_id: str,
    latest_checkpoint: dict[str, Any] | None,
    resume_context: dict[str, Any] | None,
) -> dict[str, Any]:
    current_resume = dict(resume_context or {}) if isinstance(resume_context, dict) else {}
    checkpoint = dict(latest_checkpoint or {}) if isinstance(latest_checkpoint, dict) else {}
    if current_resume:
        return current_resume
    run_id = str(session_run_id or "").strip()
    checkpoint_id = str(checkpoint.get("checkpointId") or "").strip()
    checkpoint_label = str(checkpoint.get("label") or "").strip()
    stop_reason = str(checkpoint.get("stopReason") or "").strip()
    if not any([run_id, checkpoint_id, checkpoint_label, stop_reason]):
        return {}
    summary_parts = []
    if run_id:
        summary_parts.append(f"run_id={run_id}")
    if checkpoint_label:
        summary_parts.append(f"latest_checkpoint={checkpoint_label}")
    if stop_reason:
        summary_parts.append(f"stop_reason={stop_reason}")
    return {
        "runId": run_id or None,
        "checkpointId": checkpoint_id or None,
        "checkpointLabel": checkpoint_label or None,
        "stopReason": stop_reason or None,
        "summary": "; ".join(summary_parts) if summary_parts else None,
    }


def _build_resume_ingress_summary(session_context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(session_context, dict):
        return None
    resume_ingress = (
        dict(session_context.get("resumeIngress") or {})
        if isinstance(session_context.get("resumeIngress"), dict)
        else {}
    )
    if not resume_ingress:
        recent_events = (
            list(session_context.get("recentEvents") or [])
            if isinstance(session_context.get("recentEvents"), list)
            else []
        )
        for raw_event in recent_events:
            if not isinstance(raw_event, dict):
                continue
            if str(raw_event.get("type") or "").strip() != "dispatcher_started":
                continue
            payload = dict(raw_event.get("payload") or {}) if isinstance(raw_event.get("payload"), dict) else {}
            has_resume_context = bool(payload.get("has_resume_context"))
            run_id = str(payload.get("resume_run_id") or "").strip()
            checkpoint_id = str(payload.get("resume_checkpoint_id") or "").strip()
            if not (has_resume_context or run_id or checkpoint_id):
                continue
            resume_ingress = {
                "hasResumeContext": has_resume_context or bool(run_id or checkpoint_id),
                "runId": run_id,
                "checkpointId": checkpoint_id,
                "sourceEvent": "dispatcher_started",
            }
            break
    if not resume_ingress:
        return None
    latest_checkpoint = (
        dict(session_context.get("latestCheckpoint") or {})
        if isinstance(session_context.get("latestCheckpoint"), dict)
        else {}
    )
    run_id = str(resume_ingress.get("runId") or "").strip()
    checkpoint_id = str(resume_ingress.get("checkpointId") or "").strip()
    source_event = str(resume_ingress.get("sourceEvent") or "").strip()
    stop_reason = str(latest_checkpoint.get("stopReason") or "").strip()
    summary_parts = [part for part in [run_id, checkpoint_id] if part]
    return {
        "hasResumeContext": bool(resume_ingress.get("hasResumeContext")),
        "runId": run_id or None,
        "checkpointId": checkpoint_id or None,
        "sourceEvent": source_event or None,
        "summary": " -> ".join(summary_parts) if summary_parts else None,
        "stopReason": stop_reason or None,
    }


def _build_resume_state_summary(session_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(session_context, dict):
        return {
            "hasResumeContext": False,
            "runId": None,
            "checkpointId": None,
            "sourceEvent": None,
            "stopReason": None,
            "summary": None,
        }
    resume_context = (
        dict(session_context.get("resumeContext") or {})
        if isinstance(session_context.get("resumeContext"), dict)
        else {}
    )
    if not resume_context:
        return {
            "hasResumeContext": False,
            "runId": None,
            "checkpointId": None,
            "sourceEvent": None,
            "stopReason": None,
            "summary": None,
        }
    resume_ingress = _build_resume_ingress_summary(session_context) or {}
    run_id = str(resume_context.get("runId") or "").strip() or None
    checkpoint_id = str(resume_context.get("checkpointId") or "").strip() or None
    stop_reason = str(resume_context.get("stopReason") or "").strip() or None
    summary = None
    if run_id or checkpoint_id:
        summary = " -> ".join([part for part in [run_id, checkpoint_id] if part]) or None
    return {
        "hasResumeContext": True,
        "runId": run_id,
        "checkpointId": checkpoint_id,
        "sourceEvent": str(resume_ingress.get("sourceEvent") or "").strip() or None,
        "stopReason": stop_reason,
        "summary": summary,
    }


def _build_checkpoint_state_summary(session_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(session_context, dict):
        return {
            "checkpointId": None,
            "label": None,
            "stopReason": None,
            "summary": None,
        }
    latest_checkpoint = (
        dict(session_context.get("latestCheckpoint") or {})
        if isinstance(session_context.get("latestCheckpoint"), dict)
        else {}
    )
    checkpoint_id = str(latest_checkpoint.get("checkpointId") or "").strip() or None
    label = str(latest_checkpoint.get("label") or "").strip() or None
    stop_reason = str(latest_checkpoint.get("stopReason") or "").strip() or None
    summary_parts: list[str] = []
    if label:
        summary_parts.append(f"label={label}")
    if checkpoint_id:
        summary_parts.append(f"checkpoint={checkpoint_id}")
    if stop_reason:
        summary_parts.append(f"stop={stop_reason}")
    return {
        "checkpointId": checkpoint_id,
        "label": label,
        "stopReason": stop_reason,
        "summary": " · ".join(summary_parts) if summary_parts else None,
    }


def _build_runtime_outcome_summary(
    task: dict[str, Any],
    session_context: dict[str, Any] | None,
) -> dict[str, Any]:
    latest_checkpoint = (
        dict(session_context.get("latestCheckpoint") or {})
        if isinstance(session_context, dict) and isinstance(session_context.get("latestCheckpoint"), dict)
        else {}
    )
    status = str(task.get("status") or "").strip() or None
    stop_reason = (
        str(latest_checkpoint.get("stopReason") or "").strip()
        or str(task.get("stopReason") or "").strip()
        or None
    )
    final_flag = str(task.get("finalFlag") or "").strip() or None
    summary_parts: list[str] = []
    if status:
        summary_parts.append(f"status={status}")
    if stop_reason:
        summary_parts.append(f"stop={stop_reason}")
    elif final_flag:
        summary_parts.append(f"flag={final_flag}")
    return {
        "status": status,
        "stopReason": stop_reason,
        "finalFlag": final_flag,
        "summary": " · ".join(summary_parts) if summary_parts else None,
    }
