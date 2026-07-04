from __future__ import annotations

import hashlib
import re
from typing import Any


_DEFAULT_PREVIEW_LIMIT = 160
_METADATA_ALLOWLIST = {
    "budget_name",
    "checkpoint_id",
    "phase",
    "provider",
    "run_id",
    "source_channel",
    "status",
    "task_id",
    "worker_id",
}


def _event(event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "event_type": str(event_type or "").strip(),
        "payload": dict(payload or {}),
    }


def _redact_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"(?im)^\s*set-cookie\s*:.*$", "<redacted>", text)
    text = re.sub(r"(?im)^\s*cookie\s*:.*$", "<redacted>", text)
    text = re.sub(r"(?im)^\s*authorization\s*:.*$", "<redacted>", text)
    text = re.sub(
        r"(?i)\bauthorization\s*:\s*bearer\s+[^\s,;&]+",
        "authorization=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(token|api[_-]?key|password|secret|session|cookie|authorization)\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)([\"'](?:token|api[_-]?key|password|secret|session|cookie|authorization)[\"']\s*:\s*)([\"'][^\"']*[\"']|[^,\n\r}\]]+)",
        r'\1"<redacted>"',
        text,
    )
    return text


def _preview(value: Any, *, limit: int = _DEFAULT_PREVIEW_LIMIT) -> str:
    return _redact_text(value)[: max(0, int(limit))]


def _safe_field(value: Any, *, limit: int = _DEFAULT_PREVIEW_LIMIT) -> str:
    return _preview(value, limit=limit).strip()


def _sha256_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    safe: dict[str, Any] = {}
    for key in sorted(_METADATA_ALLOWLIST):
        if key not in metadata:
            continue
        value = metadata[key]
        if isinstance(value, (bool, int, float)) or value is None:
            safe[key] = value
        else:
            safe[key] = _preview(value)
    return safe


def _maybe_number(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def build_dispatcher_started_event(
    *,
    target: str,
    goal: str,
    requested_type: str,
    local_challenge_auto_verify: bool,
    has_challenge_context: bool,
    has_resume_context: bool = False,
    resume_run_id: str = "",
    resume_checkpoint_id: str = "",
    decision_kind: str = "",
    next_action: str = "",
    decision_driver: str = "",
    switched_from: str = "",
    trigger_reason: str = "",
    strongest_hypothesis_kind: str = "",
    strongest_hypothesis_status: str = "",
    strongest_hypothesis_confidence: float | int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "target": str(target or "").strip(),
        "goal": str(goal or "").strip(),
        "requested_type": str(requested_type or "").strip(),
        "local_challenge_auto_verify": bool(local_challenge_auto_verify),
        "has_challenge_context": bool(has_challenge_context),
    }
    if has_resume_context or str(resume_run_id or "").strip() or str(resume_checkpoint_id or "").strip():
        payload.update(
            {
                "has_resume_context": bool(
                    has_resume_context
                    or str(resume_run_id or "").strip()
                    or str(resume_checkpoint_id or "").strip()
                ),
                "resume_run_id": str(resume_run_id or "").strip(),
                "resume_checkpoint_id": str(resume_checkpoint_id or "").strip(),
            }
        )
    if str(decision_kind or "").strip():
        payload["decision_kind"] = str(decision_kind or "").strip()
    if str(next_action or "").strip():
        payload["next_action"] = str(next_action or "").strip()
    if str(decision_driver or "").strip():
        payload["decision_driver"] = str(decision_driver or "").strip()
    if str(switched_from or "").strip():
        payload["switched_from"] = str(switched_from or "").strip()
    if str(trigger_reason or "").strip():
        payload["trigger_reason"] = str(trigger_reason or "").strip()
    if str(strongest_hypothesis_kind or "").strip():
        payload["strongest_hypothesis_kind"] = str(strongest_hypothesis_kind or "").strip()
    if str(strongest_hypothesis_status or "").strip():
        payload["strongest_hypothesis_status"] = str(strongest_hypothesis_status or "").strip()
    if strongest_hypothesis_confidence is not None:
        payload["strongest_hypothesis_confidence"] = strongest_hypothesis_confidence
    return _event("dispatcher_started", payload)


def build_control_action_started_event(
    *,
    action: str,
    decision_kind: str = "",
    driver: str = "",
    target: str = "",
    expected_action: str = "",
    alignment: str = "",
    alignment_reason: str = "",
    switched_from: str = "",
    trigger_reason: str = "",
    strongest_hypothesis_kind: str = "",
    strongest_hypothesis_status: str = "",
    strongest_hypothesis_confidence: float | int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action": str(action or "").strip(),
    }
    if str(decision_kind or "").strip():
        payload["decision_kind"] = str(decision_kind or "").strip()
    if str(driver or "").strip():
        payload["driver"] = str(driver or "").strip()
    if str(target or "").strip():
        payload["target"] = str(target or "").strip()
    if str(expected_action or "").strip():
        payload["expected_action"] = str(expected_action or "").strip()
    if str(alignment or "").strip():
        payload["alignment"] = str(alignment or "").strip()
    if str(alignment_reason or "").strip():
        payload["alignment_reason"] = str(alignment_reason or "").strip()
    if str(switched_from or "").strip():
        payload["switched_from"] = str(switched_from or "").strip()
    if str(trigger_reason or "").strip():
        payload["trigger_reason"] = str(trigger_reason or "").strip()
    if str(strongest_hypothesis_kind or "").strip():
        payload["strongest_hypothesis_kind"] = str(strongest_hypothesis_kind or "").strip()
    if str(strongest_hypothesis_status or "").strip():
        payload["strongest_hypothesis_status"] = str(strongest_hypothesis_status or "").strip()
    if strongest_hypothesis_confidence is not None:
        payload["strongest_hypothesis_confidence"] = strongest_hypothesis_confidence
    return _event("control_action_started", payload)


def build_control_action_completed_event(
    *,
    action: str,
    result: str,
    decision_kind: str = "",
    driver: str = "",
    target: str = "",
    details: dict[str, Any] | None = None,
    switched_from: str = "",
    trigger_reason: str = "",
    strongest_hypothesis_kind: str = "",
    strongest_hypothesis_status: str = "",
    strongest_hypothesis_confidence: float | int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action": str(action or "").strip(),
        "result": str(result or "").strip(),
    }
    if str(decision_kind or "").strip():
        payload["decision_kind"] = str(decision_kind or "").strip()
    if str(driver or "").strip():
        payload["driver"] = str(driver or "").strip()
    if str(target or "").strip():
        payload["target"] = str(target or "").strip()
    if isinstance(details, dict) and details:
        payload["details"] = dict(details)
    if str(switched_from or "").strip():
        payload["switched_from"] = str(switched_from or "").strip()
    if str(trigger_reason or "").strip():
        payload["trigger_reason"] = str(trigger_reason or "").strip()
    if str(strongest_hypothesis_kind or "").strip():
        payload["strongest_hypothesis_kind"] = str(strongest_hypothesis_kind or "").strip()
    if str(strongest_hypothesis_status or "").strip():
        payload["strongest_hypothesis_status"] = str(strongest_hypothesis_status or "").strip()
    if strongest_hypothesis_confidence is not None:
        payload["strongest_hypothesis_confidence"] = strongest_hypothesis_confidence
    return _event("control_action_completed", payload)


def build_verification_decision_event(
    *,
    decision: str,
    flag: str,
    evidence_source: str,
    rationale: str,
    confidence: float | int,
    hypothesis_id: str = "",
    strategy_kind: str = "",
) -> dict[str, Any]:
    return _event(
        "verification_decision",
        {
            "decision": str(decision or "").strip(),
            "flag": str(flag or "").strip(),
            "evidence_source": str(evidence_source or "").strip(),
            "rationale": str(rationale or "").strip(),
            "confidence": confidence,
            "hypothesis_id": str(hypothesis_id or "").strip(),
            "strategy_kind": str(strategy_kind or "").strip(),
        },
    )


def build_model_call_event(
    *,
    model: str,
    provider: str = "",
    status: str = "",
    duration_ms: float | int | None = None,
    prompt: str = "",
    completion: str = "",
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    metadata: dict[str, Any] | None = None,
    preview_limit: int = _DEFAULT_PREVIEW_LIMIT,
) -> dict[str, Any]:
    normalized_prompt_tokens = int(prompt_tokens or 0)
    normalized_completion_tokens = int(completion_tokens or 0)
    normalized_total_tokens = (
        int(total_tokens)
        if total_tokens is not None
        else normalized_prompt_tokens + normalized_completion_tokens
    )
    return _event(
        "model_call",
        {
            "model": _safe_field(model),
            "provider": _safe_field(provider),
            "status": _safe_field(status),
            "duration_ms": _maybe_number(duration_ms),
            "prompt_preview": _preview(prompt, limit=preview_limit),
            "completion_preview": _preview(completion, limit=preview_limit),
            "prompt_sha256": _sha256_text(prompt),
            "completion_sha256": _sha256_text(completion),
            "prompt_tokens": normalized_prompt_tokens,
            "completion_tokens": normalized_completion_tokens,
            "total_tokens": normalized_total_tokens,
            "metadata": _safe_metadata(metadata),
        },
    )


def build_state_transition_event(
    *,
    from_state: str,
    to_state: str,
    reason: str = "",
    source: str = "",
    success: bool | None = None,
    metadata: dict[str, Any] | None = None,
    preview_limit: int = _DEFAULT_PREVIEW_LIMIT,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "from_state": _safe_field(from_state),
        "to_state": _safe_field(to_state),
        "reason_preview": _preview(reason, limit=preview_limit),
        "source": _safe_field(source),
        "metadata": _safe_metadata(metadata),
    }
    if success is not None:
        payload["success"] = bool(success)
    return _event("state_transition", payload)


def build_budget_event(
    *,
    budget_name: str,
    event: str,
    used: int | float | None = None,
    limit: int | float | None = None,
    remaining: int | float | None = None,
    unit: str = "",
    source: str = "",
    metadata: dict[str, Any] | None = None,
    preview_limit: int = _DEFAULT_PREVIEW_LIMIT,
) -> dict[str, Any]:
    del preview_limit
    return _event(
        "budget_event",
        {
            "budget_name": _safe_field(budget_name),
            "event": _safe_field(event),
            "used": _maybe_number(used),
            "limit": _maybe_number(limit),
            "remaining": _maybe_number(remaining),
            "unit": _safe_field(unit),
            "source": _safe_field(source),
            "metadata": _safe_metadata(metadata),
        },
    )


def build_handoff_created_event(
    *,
    handoff_id: str,
    source: str = "",
    target: str = "",
    decision_kind: str = "",
    next_action: str = "",
    reason: str = "",
    metadata: dict[str, Any] | None = None,
    preview_limit: int = _DEFAULT_PREVIEW_LIMIT,
) -> dict[str, Any]:
    return _event(
        "handoff_created",
        {
            "handoff_id": _safe_field(handoff_id),
            "source": _safe_field(source),
            "target": _safe_field(target),
            "decision_kind": _safe_field(decision_kind),
            "next_action": _safe_field(next_action),
            "reason_preview": _preview(reason, limit=preview_limit),
            "metadata": _safe_metadata(metadata),
        },
    )


def build_handoff_consumed_event(
    *,
    handoff_id: str,
    consumer: str = "",
    status: str = "",
    reason: str = "",
    metadata: dict[str, Any] | None = None,
    preview_limit: int = _DEFAULT_PREVIEW_LIMIT,
) -> dict[str, Any]:
    return _event(
        "handoff_consumed",
        {
            "handoff_id": _safe_field(handoff_id),
            "consumer": _safe_field(consumer),
            "status": _safe_field(status),
            "reason_preview": _preview(reason, limit=preview_limit),
            "metadata": _safe_metadata(metadata),
        },
    )


def build_artifact_registered_event(record: dict[str, Any] | None) -> dict[str, Any]:
    item = dict(record or {})
    return _event(
        "artifact_registered",
        {
            "artifact_id": str(item.get("artifact_id") or "").strip(),
            "kind": str(item.get("kind") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "location": item.get("location"),
            "path": item.get("path"),
            "producer": str(item.get("producer") or "").strip(),
            "metadata": dict(item.get("metadata") or {}),
        },
    )


def build_recovery_decision_event(
    decision: Any,
    *,
    chain_name: str = "",
) -> dict[str, Any]:
    return _event(
        "recovery_decision",
        {
            "action": str(getattr(decision, "action", "") or "").strip(),
            "reason": str(getattr(decision, "reason", "") or "").strip(),
            "should_stop": bool(getattr(decision, "should_stop", False)),
            "chain_name": str(chain_name or "").strip(),
            "next_chain_order": list(getattr(decision, "next_chain_order", []) or []),
        },
    )


def build_task_finished_event(
    *,
    success: bool,
    flag: str,
    reason: str,
    chain_used: list[str] | None = None,
    missing_tools: list[str] | None = None,
) -> dict[str, Any]:
    return _event(
        "task_finished",
        {
            "success": bool(success),
            "flag": str(flag or "").strip(),
            "reason": str(reason or "").strip(),
            "chain_used": list(chain_used or []),
            "missing_tools": list(missing_tools or []),
        },
    )


def build_missing_tools_recorded_event(
    *,
    missing_tools: list[str] | None = None,
    install_commands: dict[str, str] | None = None,
) -> dict[str, Any]:
    return _event(
        "missing_tools_recorded",
        {
            "missing_tools": list(missing_tools or []),
            "install_commands": dict(install_commands or {}),
        },
    )


def build_checkpoint_written_event(record: dict[str, Any] | None) -> dict[str, Any]:
    item = dict(record or {})
    return _event(
        "checkpoint_written",
        {
            "checkpoint_id": str(item.get("checkpoint_id") or "").strip(),
            "label": str(item.get("label") or "").strip(),
            "metadata": dict(item.get("metadata") or {}),
        },
    )


def build_tool_called_event(
    *,
    tool_name: str,
    action: str,
    target: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _event(
        "tool_called",
        {
            "tool_name": str(tool_name or "").strip(),
            "action": str(action or "").strip(),
            "target": str(target or "").strip(),
            "metadata": dict(metadata or {}),
        },
    )


def build_tool_finished_event(
    *,
    tool_name: str,
    action: str,
    ok: bool,
    status_code: Any = None,
    target: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _event(
        "tool_finished",
        {
            "tool_name": str(tool_name or "").strip(),
            "action": str(action or "").strip(),
            "ok": bool(ok),
            "status_code": status_code,
            "target": str(target or "").strip(),
            "metadata": dict(metadata or {}),
        },
    )
