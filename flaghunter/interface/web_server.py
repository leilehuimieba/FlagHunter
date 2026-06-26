"""FlagHunter Web Console — aiohttp server.

Serves the static frontend from web/console/ and exposes a REST + SSE API.
Usage:
    flaghunter web [--host 127.0.0.1] [--port 8080]
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aiohttp import web

from .blackboard_lite import build_task_blackboard_snapshot, serialize_blackboard_snapshot
from .control_contract import (
    build_control_decision_parts,
    build_decision_record,
    resolve_control_decision,
    strongest_hypothesis_contract,
)
from .mode_router import resolve_mode_contract
from .web_decision_summaries import (
    _build_action_path_summary,
    _build_active_decision_summary,
    _build_candidate_summary,
    _build_decision_provenance_summary,
    _build_exploit_provenance_summary,
    _build_ingress_handoff_explanation,
    _build_last_action_result_summary,
    _build_next_action_explanation,
    _build_pending_verification_summary,
    _build_recommended_action_summary,
    _build_strongest_hypothesis_summary,
    _build_suppressed_recommendation_summary,
    _decision_fact_value,
)
from .web_knowledge_docs import (
    _build_knowledge_doc,
    _chunk_markdown,
    _decode_doc_key,
    _doc_key,
    _doc_match_tokens,
    _knowledge_tags_for,
    _message_mentions_doc,
)
from .web_resume_summaries import (
    _build_checkpoint_state_summary,
    _build_resume_ingress_summary,
    _build_resume_state_summary,
    _build_runtime_outcome_summary,
    _derive_resume_context_from_latest_checkpoint,
    _exploit_summary_parts,
    _normalize_exploit_provenance,
    _normalize_outcome_action_path_summary,
)
from .web_trace_timeline import (
    _build_control_decision_timeline_event,
    _build_control_observation_timeline_events,
    _build_hint_timeline,
    _build_trace_timeline,
)
from .web_leaf_utils import (
    _duration_ms_for_task, _friendly_tool_name, _load_json_file, _message_time_at, _normalize_string_list, _now_iso, _parse_iso, _single_line_preview, _sort_time_key, _truncate_text, _workspace_name_for_target,
)
from .web_serialize_task import (
    _merge_blackboard_snapshots,
    _normalize_task_collections,
    _normalized_blackboard_snapshot,
    _serialize_task,
    _task_capabilities,
    _task_detail_defaults,
)
from .web_detail_sections import (
    _build_messages_from_metrics,
    _build_messages_from_snapshot,
    _build_plan_from_snapshot,
)
from .web_knowledge_hits import (
    _KNOWLEDGE_TOOLS,
    _build_knowledge_hits_from_metrics,
    _build_knowledge_hits_from_snapshot,
    _knowledge_result_kind,
    _parse_knowledge_score,
)
from .web_settings_io import (
    _SETTINGS_EDITABLE_PATHS,
    _SETTINGS_RESTART_REQUIRED_PATHS,
    _apply_settings,
    _mask_secret,
    _mcp_manager_for_project,
    _read_env,
    _settings_meta,
    _settings_to_api,
    _write_env_key,
)
from ..agents.pa_agent.session_context import build_workspace_run_context

logger = logging.getLogger(__name__)

# ── Global event bus for SSE ──────────────────────────────────────────────────
# Built on the neutral EventBus (flaghunter.session.event_bus) so the project
# has a single event-bus implementation (architecture invariant I3). This
# adapter keeps web's dict-in / asyncio.Queue-out API — used by the 16 emit call
# sites and the SSE endpoint — layered on top of the shared neutral core.

from ..session.event_bus import EventBus as _CoreEventBus


class EventBus(_CoreEventBus):
    """SSE broadcaster: web's dict+queue API on top of the neutral EventBus."""

    def __init__(self) -> None:
        super().__init__()
        self._queue_unsubs: dict[asyncio.Queue, object] = {}

    def emit(self, event: dict) -> None:  # type: ignore[override]
        """Thread-safe emit of a web event dict (forwarded to the neutral core)."""
        super().emit(str(event.get("type", "")), event, source="web")

    def subscribe(self) -> asyncio.Queue:  # type: ignore[override]
        q: asyncio.Queue = asyncio.Queue(maxsize=128)

        def _forward(neutral_event) -> None:
            try:
                q.put_nowait(neutral_event.data)
            except asyncio.QueueFull:
                pass

        self._queue_unsubs[q] = super().subscribe(_forward)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:  # type: ignore[override]
        unsub = self._queue_unsubs.pop(q, None)
        if unsub is not None:
            unsub()


_bus = EventBus()


class DashboardAggregator:
    """Thread-safe time-series accumulator for dashboard charts.

    Called from background agent threads to record per-turn metrics.
    The dashboard endpoint reads aggregated series via get_summary().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token_buckets: dict[str, int] = {}         # "HH:00" → tokens
        self._knowledge_hit_buckets: dict[str, int] = {}  # "HH:00" → hits
        self._tool_counts: dict[str, int] = {}            # tool_name → count
        self._failure_counts: dict[str, int] = {}         # stop_reason → count
        self._total_knowledge_hits: int = 0

    @staticmethod
    def _hour_key() -> str:
        return datetime.now(timezone.utc).strftime("%H:00")

    def record_turn(
        self,
        input_tokens: int,
        output_tokens: int,
        tool_names: list[str],
        knowledge_hits: int = 0,
    ) -> None:
        hour = self._hour_key()
        total = input_tokens + output_tokens
        with self._lock:
            self._token_buckets[hour] = self._token_buckets.get(hour, 0) + total
            if knowledge_hits > 0:
                self._knowledge_hit_buckets[hour] = (
                    self._knowledge_hit_buckets.get(hour, 0) + knowledge_hits
                )
                self._total_knowledge_hits += knowledge_hits
            for name in tool_names:
                self._tool_counts[name] = self._tool_counts.get(name, 0) + 1

    def record_failure(self, stop_reason: str) -> None:
        reason = stop_reason or "unknown"
        with self._lock:
            self._failure_counts[reason] = self._failure_counts.get(reason, 0) + 1

    def record_knowledge_hit(self) -> None:
        hour = self._hour_key()
        with self._lock:
            self._knowledge_hit_buckets[hour] = (
                self._knowledge_hit_buckets.get(hour, 0) + 1
            )
            self._total_knowledge_hits += 1

    @staticmethod
    def _series_from_buckets(buckets: dict[str, int]) -> list[dict]:
        return [
            {"t": k, "v": v}
            for k, v in sorted(buckets.items())[-24:]
        ]

    def get_summary(self) -> dict:
        with self._lock:
            return {
                "totalKnowledgeHits": self._total_knowledge_hits,
                "tokenSeries": self._series_from_buckets(dict(self._token_buckets)),
                "knowledgeHitTrend": self._series_from_buckets(
                    dict(self._knowledge_hit_buckets)
                ),
                "toolDistribution": [
                    {"name": k, "value": v}
                    for k, v in sorted(
                        self._tool_counts.items(), key=lambda x: x[1], reverse=True
                    )[:12]
                ],
                "failureDistribution": [
                    {
                        "name": k,
                        "value": v,
                        "color": {
                            "no_progress": "var(--red)",
                            "missing_tool": "var(--amber)",
                            "budget_capped": "var(--magenta)",
                            "verifier_reject": "var(--cyan)",
                        }.get(k, "var(--fg-3)"),
                    }
                    for k, v in sorted(
                        self._failure_counts.items(), key=lambda x: x[1], reverse=True
                    )
                ],
            }


_aggregator = DashboardAggregator()


def emit_log(level: str, source: str, message: str) -> None:
    """Thread-safe log emitter for live tailing via SSE.

    Can be called from any thread (agent background threads, tools, etc.).
    The SSE stream picks up ``log_line`` events and pushes them to the browser.
    """
    _bus.emit({
        "type": "log_line",
        "level": level,        # "info", "warn", "error", "debug"
        "source": source,      # "agent", "tool.terminal", "rag", etc.
        "message": message[:500],
        "t": _now_iso(),
    })


# ── Task registry ─────────────────────────────────────────────────────────────

_tasks: dict[str, dict] = {}
_task_threads: dict[str, threading.Thread] = {}


def _task_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
    return f"task_{ts}_{uuid.uuid4().hex[:4]}"


def _run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
    return f"run_{ts}_{uuid.uuid4().hex[:4]}"


def _task_blackboard_snapshot_for_decision(
    task: dict[str, Any],
    explicit_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rebuilt_snapshot = _normalized_blackboard_snapshot(build_task_blackboard_snapshot(task))
    existing_snapshot = task.get("blackboardSnapshot")
    merged_snapshot = _merge_blackboard_snapshots(rebuilt_snapshot, existing_snapshot)
    if isinstance(explicit_snapshot, dict) and explicit_snapshot:
        merged_snapshot = _merge_blackboard_snapshots(merged_snapshot, explicit_snapshot)
    if (
        merged_snapshot["facts"]
        or merged_snapshot["hypotheses"]
        or merged_snapshot["pendingVerifications"]
        or merged_snapshot["decisions"]
        or merged_snapshot["candidates"]
        or merged_snapshot["actionResults"]
        or merged_snapshot["recommendedAction"]
        or merged_snapshot["activeDecision"]
    ):
        return merged_snapshot
    return rebuilt_snapshot


def _inherit_source_blackboard_seed(task: dict[str, Any], source_task: dict[str, Any] | None) -> None:
    if not isinstance(source_task, dict):
        return
    if isinstance(source_task.get("ctfStateSnapshot"), dict) and not isinstance(task.get("ctfStateSnapshot"), dict):
        task["ctfStateSnapshot"] = dict(source_task.get("ctfStateSnapshot") or {})
    task["blackboardSnapshot"] = _task_blackboard_snapshot_for_decision(source_task)


def _apply_control_decision(
    task: dict[str, Any],
    *,
    blackboard_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision_payload = dict(task)
    decision_payload["blackboardSnapshot"] = _task_blackboard_snapshot_for_decision(
        task,
        blackboard_snapshot,
    )
    task["blackboardSnapshot"] = decision_payload["blackboardSnapshot"]
    decision = resolve_control_decision(decision_payload)
    task["controlDecision"] = decision
    task["decisionRecords"] = [
        build_decision_record(decision, source="web_ingress")
    ]
    return decision


def _apply_followup_recommended_control_decision(
    task: dict[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    blackboard_snapshot = _task_blackboard_snapshot_for_decision(task)
    recommended_action = (
        dict(blackboard_snapshot.get("recommendedAction") or {})
        if isinstance(blackboard_snapshot, dict)
        and isinstance(blackboard_snapshot.get("recommendedAction"), dict)
        else {}
    )
    if not str(recommended_action.get("action") or "").strip():
        return _apply_control_decision(task, blackboard_snapshot=blackboard_snapshot)
    decision_payload = dict(task)
    decision_payload.pop("resumeFromRunId", None)
    decision_payload.pop("resumeFromCheckpointId", None)
    decision_payload.pop("resumeSummary", None)
    session_context = (
        dict(task.get("sessionContext") or {})
        if isinstance(task.get("sessionContext"), dict)
        else {}
    )
    session_context.pop("resumeContext", None)
    if session_context:
        decision_payload["sessionContext"] = session_context
    else:
        decision_payload.pop("sessionContext", None)
    decision_payload["blackboardSnapshot"] = blackboard_snapshot
    decision = resolve_control_decision(decision_payload)
    task["blackboardSnapshot"] = decision_payload["blackboardSnapshot"]
    task["controlDecision"] = decision
    task["decisionRecords"] = [
        build_decision_record(decision, source=source)
    ]
    return decision


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


def _session_context_has_observed_data(context: Any) -> bool:
    if not isinstance(context, dict):
        return False
    return bool(
        context.get("recentEvents")
        or context.get("artifacts")
        or context.get("latestCheckpoint")
        or context.get("resumeContext")
    )


def _build_run_session_context(project_root: Path, run_id: str | None) -> dict[str, Any]:
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        return {
            "runId": "",
            "recentEvents": [],
            "artifacts": [],
            "latestCheckpoint": None,
            "resumeContext": None,
        }
    return build_workspace_run_context(project_root, normalized_run_id)


def _build_resume_lineage_payload(project_root: Path, run_id: str | None) -> dict[str, Any]:
    session_context = _build_run_session_context(project_root, run_id)
    resume_context = (
        dict(session_context.get("resumeContext") or {})
        if isinstance(session_context.get("resumeContext"), dict)
        else {}
    )
    latest_checkpoint = (
        dict(session_context.get("latestCheckpoint") or {})
        if isinstance(session_context.get("latestCheckpoint"), dict)
        else {}
    )
    return {
        "sourceRunId": str(run_id or "").strip() or None,
        "resumeFromRunId": (
            str(resume_context.get("runId") or run_id or "").strip() or None
        ),
        "resumeFromCheckpointId": (
            str(resume_context.get("checkpointId") or latest_checkpoint.get("checkpointId") or "").strip()
            or None
        ),
        "resumeSummary": str(resume_context.get("summary") or "").strip() or None,
        "sessionContext": session_context,
    }


def _merge_resume_lineage_with_source_task(
    lineage_payload: dict[str, Any],
    source_task: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(source_task, dict):
        return lineage_payload
    merged = dict(lineage_payload)
    source_session_context = (
        dict(source_task.get("sessionContext") or {})
        if isinstance(source_task.get("sessionContext"), dict)
        else {}
    )
    source_resume_context = (
        dict(source_session_context.get("resumeContext") or {})
        if isinstance(source_session_context.get("resumeContext"), dict)
        else {}
    )
    if not merged.get("resumeFromRunId"):
        merged["resumeFromRunId"] = (
            str(source_task.get("resumeFromRunId") or source_resume_context.get("runId") or "").strip() or None
        )
    if not merged.get("resumeFromCheckpointId"):
        merged["resumeFromCheckpointId"] = (
            str(source_task.get("resumeFromCheckpointId") or source_resume_context.get("checkpointId") or "").strip() or None
        )
    if not merged.get("resumeSummary"):
        merged["resumeSummary"] = (
            str(source_task.get("resumeSummary") or source_resume_context.get("summary") or "").strip() or None
        )
    session_context = (
        dict(merged.get("sessionContext") or {})
        if isinstance(merged.get("sessionContext"), dict)
        else {}
    )
    if not isinstance(session_context.get("resumeContext"), dict) and source_resume_context:
        session_context["resumeContext"] = source_resume_context
        merged["sessionContext"] = session_context
    return merged


def _apply_mode_contract(
    task: dict[str, Any],
    payload: dict[str, Any],
    *,
    source_task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = resolve_mode_contract(payload, source_task=source_task)
    task["mode"] = contract["mode"]
    task["modeSubtype"] = contract["modeSubtype"]
    task["goalStyle"] = contract["goalStyle"]
    normalized_payload = dict(payload)
    normalized_payload.update(contract)
    if contract["mode"] == "ctf":
        ctf_type = str(normalized_payload.get("ctfType") or contract["modeSubtype"] or "unknown").strip().lower()
        task["ctfType"] = ctf_type or "unknown"
        normalized_payload["ctfType"] = task["ctfType"]
    else:
        task.pop("ctfType", None)
        normalized_payload.pop("ctfType", None)
    task.pop("detectedType", None)
    normalized_payload.pop("detectedType", None)
    return normalized_payload


def _default_goal_for_payload(payload: dict[str, Any]) -> str:
    mode = str(payload.get("mode") or "").lower()
    subtype = str(payload.get("modeSubtype") or payload.get("ctfType") or "unknown").lower()
    if mode == "ctf":
        return f"CTF {subtype} challenge — capture the flag"
    target = str(payload.get("target") or "").strip()
    if target:
        return f"Assess target {target} and produce concrete security evidence"
    return "Assess the target and produce concrete security evidence"


def _ensure_effective_goal(task: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    effective_goal = str(payload.get("goal") or "").strip() or _default_goal_for_payload(payload)
    task["goal"] = effective_goal
    normalized_payload = dict(payload)
    normalized_payload["goal"] = effective_goal
    return normalized_payload


def _latest_user_hint(task: dict[str, Any]) -> str:
    hints = task.get("hints") if isinstance(task.get("hints"), list) else []
    for raw in reversed(hints):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if not text or text == "__continue__":
            continue
        return text
    return ""


def _normalize_task_asset_contract(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    challenge_path = str(normalized.get("challengePath") or "").strip()
    normalized["challengePath"] = challenge_path or None
    normalized["artifactPaths"] = _normalize_string_list(normalized.get("artifactPaths"))
    return normalized


def _apply_task_asset_contract(task: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_task_asset_contract(payload)
    task["challengePath"] = normalized.get("challengePath")
    task["artifactPaths"] = list(normalized.get("artifactPaths") or [])
    return normalized


def _ctf_dispatcher_hint(task: dict[str, Any]) -> str:
    latest_hint = _latest_user_hint(task)
    decision = task.get("controlDecision") if isinstance(task.get("controlDecision"), dict) else {}
    blackboard_snapshot = build_task_blackboard_snapshot(task)
    handoff = task.get("ingressHandoff") if isinstance(task.get("ingressHandoff"), dict) else {}
    challenge_context = (
        dict(handoff.get("challengeContext") or {})
        if isinstance(handoff.get("challengeContext"), dict)
        else _build_ctf_challenge_context(task)
    )
    challenge_path = str(challenge_context.get("challengePath") or "").strip()
    artifact_paths = _normalize_string_list(challenge_context.get("artifactPaths"))
    resume_context = (
        dict(challenge_context.get("resumeContext") or {})
        if isinstance(challenge_context.get("resumeContext"), dict)
        else {}
    )
    structured_parts: list[str] = []
    decision_parts = build_control_decision_parts(decision, blackboard_snapshot)
    if challenge_path:
        structured_parts.append(f"challengePath={challenge_path}")
    if artifact_paths:
        structured_parts.append("artifactPaths=" + "; ".join(artifact_paths))
    resume_summary = str(resume_context.get("summary") or "").strip()
    if resume_summary:
        structured_parts.append("[resume_context]\nsummary=" + resume_summary)
    resume_bootstrap = (
        dict(handoff.get("resumeBootstrap") or {})
        if isinstance(handoff.get("resumeBootstrap"), dict)
        else {}
    )
    resume_run_id = str(resume_bootstrap.get("runId") or resume_context.get("runId") or "").strip()
    resume_checkpoint_id = str(resume_bootstrap.get("checkpointId") or resume_context.get("checkpointId") or "").strip()
    resume_bootstrap_summary = str(resume_bootstrap.get("summary") or resume_summary or "").strip()
    resume_bootstrap_action = str(resume_bootstrap.get("nextAction") or "resume_from_checkpoint").strip()
    if resume_run_id or resume_checkpoint_id or resume_bootstrap_summary:
        resume_bootstrap_parts = [f"nextAction={resume_bootstrap_action}"]
        if resume_run_id:
            resume_bootstrap_parts.append(f"runId={resume_run_id}")
        if resume_checkpoint_id:
            resume_bootstrap_parts.append(f"checkpointId={resume_checkpoint_id}")
        if resume_bootstrap_summary:
            resume_bootstrap_parts.append(f"summary={resume_bootstrap_summary}")
        structured_parts.append("[resume_bootstrap]\n" + "\n".join(resume_bootstrap_parts))
    should_include_decision_block = bool(
        decision_parts
        and (
            str(decision.get("nextAction") or "").strip() != "collect_initial_facts"
            or challenge_path
            or artifact_paths
            or resume_summary
            or resume_run_id
            or resume_checkpoint_id
        )
    )
    if should_include_decision_block:
        structured_parts.insert(0, "[control_decision]\n" + "\n".join(decision_parts))
    if not structured_parts:
        return latest_hint
    structured_hint = "[local_ctf_assets]\n" + "\n".join(structured_parts)
    if latest_hint:
        return latest_hint + "\n\n" + structured_hint
    return structured_hint


async def _run_ctf_dispatcher_with_handoff(
    dispatcher: Any,
    *,
    target: str,
    goal: str,
    ctf_type: str,
    hint: str,
    challenge_context: dict[str, Any],
    ingress_handoff: dict[str, Any] | None,
) -> Any:
    kwargs = {
        "target": target,
        "goal": goal,
        "type": ctf_type,
        "hint": hint,
        "challenge_context": challenge_context,
    }
    try:
        return await dispatcher.run(**kwargs, ingress_handoff=ingress_handoff)
    except TypeError as exc:
        if "ingress_handoff" not in str(exc):
            raise
        return await dispatcher.run(**kwargs)


def _build_ctf_resume_context(task: dict[str, Any]) -> dict[str, Any] | None:
    session_context = task.get("sessionContext")
    if isinstance(session_context, dict) and isinstance(session_context.get("resumeContext"), dict):
        resume_context = dict(session_context.get("resumeContext") or {})
    else:
        resume_context = {}
    summary = str(task.get("resumeSummary") or "").strip()
    run_id = str(task.get("resumeFromRunId") or "").strip()
    checkpoint_id = str(task.get("resumeFromCheckpointId") or "").strip()
    if not resume_context:
        if not any([summary, run_id, checkpoint_id]):
            return None
        resume_context = {
            "runId": run_id,
            "checkpointId": checkpoint_id,
            "summary": summary,
        }
    else:
        if run_id and not str(resume_context.get("runId") or "").strip():
            resume_context["runId"] = run_id
        if checkpoint_id and not str(resume_context.get("checkpointId") or "").strip():
            resume_context["checkpointId"] = checkpoint_id
        if summary and not str(resume_context.get("summary") or "").strip():
            resume_context["summary"] = summary
    normalized: dict[str, Any] = {}
    for key in ["runId", "checkpointId", "checkpointLabel", "stopReason", "summary"]:
        value = str(resume_context.get(key) or "").strip()
        if value:
            normalized[key] = value
    for key in ["verifiedFlags", "runtimeFlags"]:
        values = _normalize_string_list(resume_context.get(key))
        if values:
            normalized[key] = list(dict.fromkeys(values))
        elif key in resume_context:
            normalized[key] = []
    return normalized or None


def _build_ctf_challenge_context(task: dict[str, Any]) -> dict[str, Any]:
    context = {
        "challengePath": str(task.get("challengePath") or "").strip() or None,
        "artifactPaths": _normalize_string_list(task.get("artifactPaths")),
    }
    resume_context = _build_ctf_resume_context(task)
    if resume_context:
        context["resumeContext"] = resume_context
    return context


def _sync_runtime_challenge_context(task: dict[str, Any], dispatcher: Any) -> None:
    runtime_context = getattr(dispatcher, "_challenge_context", None)
    if not isinstance(runtime_context, dict):
        return
    handoff = dict(task.get("ingressHandoff") or {}) if isinstance(task.get("ingressHandoff"), dict) else {}
    challenge_context = (
        dict(handoff.get("challengeContext") or {})
        if isinstance(handoff.get("challengeContext"), dict)
        else _build_ctf_challenge_context(task)
    )
    for key in ("challengePath", "derivedTarget", "derivedTargetSource", "derivedTargetComposePath"):
        value = str(runtime_context.get(key) or "").strip()
        if value:
            challenge_context[key] = value
    artifact_paths = _normalize_string_list(runtime_context.get("artifactPaths"))
    if artifact_paths:
        challenge_context["artifactPaths"] = artifact_paths
    handoff["challengeContext"] = challenge_context
    task["ingressHandoff"] = handoff
    derived_target = str(challenge_context.get("derivedTarget") or "").strip()
    if derived_target and not str(task.get("target") or "").strip():
        task["target"] = derived_target


def _inherit_source_challenge_context(task: dict[str, Any], source_task: dict[str, Any] | None) -> None:
    if not isinstance(source_task, dict):
        return
    source_handoff = source_task.get("ingressHandoff")
    if not isinstance(source_handoff, dict):
        return
    source_challenge_context = source_handoff.get("challengeContext")
    if not isinstance(source_challenge_context, dict):
        return
    handoff = dict(task.get("ingressHandoff") or {}) if isinstance(task.get("ingressHandoff"), dict) else {}
    challenge_context = (
        dict(handoff.get("challengeContext") or {})
        if isinstance(handoff.get("challengeContext"), dict)
        else _build_ctf_challenge_context(task)
    )
    for key in ("challengePath", "derivedTarget", "derivedTargetSource", "derivedTargetComposePath"):
        value = str(source_challenge_context.get(key) or "").strip()
        if value and not str(challenge_context.get(key) or "").strip():
            challenge_context[key] = value
    source_artifact_paths = _normalize_string_list(source_challenge_context.get("artifactPaths"))
    if source_artifact_paths and not _normalize_string_list(challenge_context.get("artifactPaths")):
        challenge_context["artifactPaths"] = source_artifact_paths
    handoff["challengeContext"] = challenge_context
    task["ingressHandoff"] = handoff
    derived_target = str(challenge_context.get("derivedTarget") or "").strip()
    if derived_target and not str(task.get("target") or "").strip():
        task["target"] = derived_target


def _source_derived_target_contract(source_task: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(source_task, dict):
        return {}
    handoff = source_task.get("ingressHandoff")
    if not isinstance(handoff, dict):
        return {}
    challenge_context = handoff.get("challengeContext")
    if not isinstance(challenge_context, dict):
        return {}
    payload: dict[str, Any] = {}
    for key in ("derivedTarget", "derivedTargetSource", "derivedTargetComposePath"):
        value = str(challenge_context.get(key) or "").strip()
        if value:
            payload[key] = value
    return payload


def _derived_target_detail_source(task: dict[str, Any]) -> dict[str, Any]:
    handoff = task.get("ingressHandoff")
    if not isinstance(handoff, dict):
        return {"derivedTargetOrigin": "unobserved"}
    challenge_context = handoff.get("challengeContext")
    if not isinstance(challenge_context, dict):
        return {"derivedTargetOrigin": "unobserved"}

    derived_target = str(challenge_context.get("derivedTarget") or "").strip()
    derived_target_source = str(challenge_context.get("derivedTargetSource") or "").strip()
    derived_target_compose_path = str(challenge_context.get("derivedTargetComposePath") or "").strip()
    if not (derived_target or derived_target_source or derived_target_compose_path):
        return {"derivedTargetOrigin": "unobserved"}

    has_lineage = bool(
        str(task.get("sourceRunId") or "").strip()
        or str(task.get("resumeFromRunId") or "").strip()
    )
    payload = {
        "derivedTargetOrigin": "inherited_lineage" if has_lineage else "runtime_derived",
    }
    if derived_target:
        payload["derivedTarget"] = derived_target
    if derived_target_source:
        payload["derivedTargetSource"] = derived_target_source
    if derived_target_compose_path:
        payload["derivedTargetComposePath"] = derived_target_compose_path
    return payload


def _candidate_notes_files(project_root: Path, task: dict[str, Any]) -> list[Path]:
    target = str(task.get("target") or "")
    workspace_name = _workspace_name_for_target(target)
    candidates = [
        project_root / "loot" / "notes.json",
    ]
    if workspace_name:
        candidates.append(project_root / "workspaces" / workspace_name / "loot" / "notes.json")
    seen: set[Path] = set()
    result: list[Path] = []
    for path in candidates:
        if path.exists() and path not in seen:
            result.append(path)
            seen.add(path)
    return result


def _note_matches_task(key: str, note: dict[str, Any], task: dict[str, Any]) -> bool:
    target = str(task.get("target") or "").lower()
    run_id = str(task.get("currentRunId") or "")
    task_id = str(task.get("id") or "")
    haystacks = [key.lower(), str(note.get("content") or "").lower()]
    meta = note.get("metadata") if isinstance(note.get("metadata"), dict) else {}
    for value in meta.values():
        if isinstance(value, (str, int, float)):
            haystacks.append(str(value).lower())
    if run_id and any(run_id.lower() in text for text in haystacks):
        return True
    if task_id and any(task_id.lower() in text for text in haystacks):
        return True
    if target and any(target in text for text in haystacks):
        return True
    return False


def _load_task_notes(project_root: Path, task: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    sources: list[str] = []
    for path in _candidate_notes_files(project_root, task):
        raw = _load_json_file(path)
        if not isinstance(raw, dict):
            continue
        relative_source = str(path.relative_to(project_root))
        sources.append(relative_source)
        for idx, (key, note) in enumerate(raw.items(), start=1):
            if not isinstance(note, dict):
                continue
            meta = note.get("metadata") if isinstance(note.get("metadata"), dict) else {}
            entry = {
                "id": f"{path.stem}:{idx}",
                "key": key,
                "value": str(note.get("content") or ""),
                "category": note.get("category") or "info",
                "confidence": note.get("confidence") or "medium",
                "status": note.get("status") or "confirmed",
                "metadata": meta,
                "source": relative_source,
            }
            if _note_matches_task(key, note, task):
                items.append(entry)
    return items[:12], sources


def _iter_session_paths(project_root: Path, task: dict[str, Any]) -> list[Path]:
    target = str(task.get("target") or "")
    workspace_name = _workspace_name_for_target(target)
    paths = [project_root / "loot" / "sessions"]
    if workspace_name:
        paths.append(project_root / "workspaces" / workspace_name / "loot" / "sessions")
    results: list[Path] = []
    seen: set[Path] = set()
    for base in paths:
        if not base.exists():
            continue
        for path in sorted(base.glob("*.json")):
            if path.name == "index.json":
                continue
            resolved = path.resolve()
            if resolved not in seen:
                results.append(path)
                seen.add(resolved)
    return results


def _score_session_snapshot(snapshot: dict[str, Any], task: dict[str, Any], path: Path) -> float:
    score = 0.0
    task_started = _parse_iso(task.get("startedAt") or task.get("createdAt"))
    snapshot_updated = _parse_iso(snapshot.get("updated_at"))
    if task_started and snapshot_updated:
        score += abs((snapshot_updated - task_started).total_seconds())
    else:
        score += 86_400.0
    target = str(task.get("target") or "").lower()
    snap_target = str(snapshot.get("target") or "").lower()
    if target and snap_target:
        score += 0 if target == snap_target else 10_000.0
    elif target or snap_target:
        score += 20_000.0
    if snapshot.get("session_id") == task.get("sessionId"):
        score -= 50_000.0
    if path.stem == task.get("sessionId"):
        score -= 50_000.0
    message_count = len(snapshot.get("conversation") or [])
    score -= min(message_count, 50) * 10.0
    return score


def _session_confidence_for_score(score: float) -> str:
    if score <= 600:
        return "medium"
    if score <= 3_600:
        return "low"
    return "very_low"


def _pick_session_snapshot(project_root: Path, task: dict[str, Any]) -> tuple[dict[str, Any] | None, Path | None, dict[str, Any]]:
    explicit_id = str(task.get("sessionId") or "")
    meta = {
        "matchedBy": "none",
        "confidence": "none",
        "expectedSessionId": explicit_id or None,
        "blockedReason": None,
        "candidateScore": None,
    }
    if explicit_id:
        for base in [project_root / "loot" / "sessions", project_root / "workspaces" / _workspace_name_for_target(task.get("target")) / "loot" / "sessions"]:
            candidate = base / f"{explicit_id}.json"
            if candidate.exists():
                data = _load_json_file(candidate)
                if isinstance(data, dict):
                    meta["matchedBy"] = "explicit_session_id"
                    meta["confidence"] = "high"
                    return data, candidate, meta
        meta["blockedReason"] = "expected_session_missing"
    best: tuple[float, dict[str, Any], Path] | None = None
    for path in _iter_session_paths(project_root, task):
        data = _load_json_file(path)
        if not isinstance(data, dict):
            continue
        score = _score_session_snapshot(data, task, path)
        if best is None or score < best[0]:
            best = (score, data, path)
    if best is None:
        return None, None, meta
    meta["matchedBy"] = "heuristic_target_time"
    meta["candidateScore"] = round(best[0], 3)
    meta["confidence"] = _session_confidence_for_score(best[0])
    return best[1], best[2], meta


def _build_hint_messages(task: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for idx, raw in enumerate(task.get("hints") or [], start=1):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "hint accepted").strip() or "hint accepted"
        items.append({
            "id": f"hint_msg_{idx}",
            "role": "system",
            "t": str(raw.get("t") or task.get("finishedAt") or task.get("startedAt") or _now_iso()),
            "content": f"hint accepted · {text}",
        })
    return items


def _extract_tool_events_from_snapshot(task: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    raw_messages = snapshot.get("conversation") or []
    if not isinstance(raw_messages, list):
        return []
    events: list[dict[str, Any]] = []
    total = len(raw_messages)
    pending_calls: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_messages):
        if not isinstance(raw, dict):
            continue
        t = _message_time_at(task, snapshot, idx, total)
        role = str(raw.get("role") or "")
        if role == "assistant":
            tool_calls = raw.get("tool_calls") if isinstance(raw.get("tool_calls"), list) else []
            pending_calls.extend([
                {
                    "tool": str(tc.get("name") or "tool"),
                    "input": json.dumps(tc.get("arguments") or {}, ensure_ascii=False, indent=2),
                    "t": t,
                }
                for tc in tool_calls if isinstance(tc, dict)
            ])
        elif role == "tool_result":
            tool_results = raw.get("tool_results") if isinstance(raw.get("tool_results"), list) else []
            for result in tool_results:
                if not isinstance(result, dict):
                    continue
                matched = pending_calls.pop(0) if pending_calls else {
                    "tool": str(result.get("tool_name") or "tool"),
                    "input": None,
                    "t": t,
                }
                output = str(result.get("result") or result.get("error") or "").strip()
                events.append({
                    "tool": matched.get("tool"),
                    "input": matched.get("input"),
                    "output": _truncate_text(output or "no output captured", 4000),
                    "success": bool(result.get("success", True)),
                    "durationMs": result.get("duration_ms"),
                    "t": matched.get("t") or t,
                })
    return events


def _extract_tool_audit_events_from_session_context(session_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(session_context, dict):
        return []
    recent_events = session_context.get("recentEvents")
    if not isinstance(recent_events, list):
        return []

    events: list[dict[str, Any]] = []
    for idx, event in enumerate(recent_events, start=1):
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "").strip()
        if event_type not in {"tool_called", "tool_finished"}:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        tool_name = str(payload.get("tool_name") or "tool").strip() or "tool"
        action = str(payload.get("action") or "").strip()
        target = str(payload.get("target") or "").strip()
        summary_bits = [action] if action else []
        if target:
            summary_bits.append(target)
        if event_type == "tool_finished":
            ok = bool(payload.get("ok", True))
            summary_bits.append("ok" if ok else "failed")
        events.append({
            "tool": tool_name,
            "input": json.dumps(payload.get("metadata") or {}, ensure_ascii=False) if event_type == "tool_called" else None,
            "output": None,
            "success": bool(payload.get("ok", True)) if event_type == "tool_finished" else None,
            "durationMs": None,
            "t": str(event.get("t") or _now_iso()),
            "type": "tool",
            "kind": event_type,
            "title": f"{tool_name} {'called' if event_type == 'tool_called' else 'finished'}",
            "summary": " · ".join(summary_bits) if summary_bits else event_type,
            "status": "running" if event_type == "tool_called" else ("done" if payload.get("ok", True) else "failed"),
            "id": f"audit_{event_type}_{idx}",
        })
    return events


def _build_task_list_payload(project_root: Path, task: dict[str, Any]) -> dict[str, Any]:
    item = _serialize_task(task)
    session_context = _build_session_context_from_harness(project_root, item)
    item["resumeStateSummary"] = _build_resume_state_summary(session_context)
    item["checkpointStateSummary"] = _build_checkpoint_state_summary(session_context)
    item["runtimeOutcomeSummary"] = _build_runtime_outcome_summary(item, session_context)
    return item


def _extract_outcome_events_from_session_context(
    session_context: dict[str, Any] | None,
    exploit_provenance: dict[str, Any] | None = None,
    action_path_summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(session_context, dict):
        return []
    recent_events = session_context.get("recentEvents")
    if not isinstance(recent_events, list):
        return []
    normalized_exploit_provenance = _normalize_exploit_provenance(exploit_provenance)
    normalized_action_path_summary = _normalize_outcome_action_path_summary(action_path_summary)
    latest_checkpoint = (
        dict(session_context.get("latestCheckpoint") or {})
        if isinstance(session_context.get("latestCheckpoint"), dict)
        else {}
    )
    resume_context = (
        dict(session_context.get("resumeContext") or {})
        if isinstance(session_context.get("resumeContext"), dict)
        else {}
    )
    session_run_id = str(session_context.get("runId") or "").strip()
    effective_resume_context = _derive_resume_context_from_latest_checkpoint(
        session_run_id,
        latest_checkpoint,
        resume_context,
    )

    events: list[dict[str, Any]] = []
    supported_types = {
        "dispatcher_started",
        "control_action_started",
        "control_action_completed",
        "verification_decision",
        "recovery_decision",
        "task_finished",
        "checkpoint_written",
    }
    for idx, event in enumerate(recent_events, start=1):
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "").strip()
        if event_type not in supported_types:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "dispatcher_started":
            decision_kind = str(payload.get("decision_kind") or "").strip()
            next_action = str(payload.get("next_action") or "").strip()
            decision_driver = str(payload.get("decision_driver") or "").strip()
            summary_bits = [item for item in [decision_kind, next_action, decision_driver] if item]
            summary_bits.extend(_exploit_summary_parts(normalized_exploit_provenance))
            summary = " · ".join(summary_bits)
            if not summary:
                summary = str(payload.get("requested_type") or "").strip() or event_type
            output_payload = dict(payload)
            if normalized_exploit_provenance:
                output_payload["exploit_provenance"] = normalized_exploit_provenance
            events.append({
                "id": f"outcome_{event_type}_{idx}",
                "type": "system",
                "kind": event_type,
                "title": "dispatcher started",
                "summary": summary,
                "status": "done",
                "t": str(event.get("t") or _now_iso()),
                "output": json.dumps(output_payload, ensure_ascii=False, indent=2),
                "tokens": 0,
            })
            continue
        if event_type in {"control_action_started", "control_action_completed"}:
            action = str(payload.get("action") or "").strip()
            driver = str(payload.get("driver") or "").strip()
            result = str(payload.get("result") or "").strip()
            expected_action = str(payload.get("expected_action") or "").strip()
            alignment = str(payload.get("alignment") or "").strip()
            summary_bits: list[str] = []
            if action:
                summary_bits.append(f"action={action}")
            if expected_action and event_type == "control_action_started":
                summary_bits.append(f"expected={expected_action}")
            if result and event_type == "control_action_completed":
                summary_bits.append(f"result={result}")
            if alignment and event_type == "control_action_started":
                summary_bits.append(f"alignment={alignment}")
            if driver:
                summary_bits.append(f"driver={driver}")
            exploit_summary_parts = _exploit_summary_parts(normalized_exploit_provenance)
            if exploit_summary_parts:
                summary_bits.append("exploit=" + " ".join(exploit_summary_parts))
            summary = " · ".join(summary_bits) or event_type
            output_payload = dict(payload)
            if normalized_exploit_provenance:
                output_payload["exploit_provenance"] = normalized_exploit_provenance
            events.append({
                "id": f"outcome_{event_type}_{idx}",
                "type": "system",
                "kind": event_type,
                "title": "control action started" if event_type == "control_action_started" else "control action completed",
                "summary": summary,
                "status": "done" if event_type == "control_action_started" or result in {"", "ok"} else "failed",
                "t": str(event.get("t") or _now_iso()),
                "output": json.dumps(output_payload, ensure_ascii=False, indent=2),
                "tokens": 0,
            })
            continue
        if event_type == "verification_decision":
            decision = str(payload.get("decision") or "").strip() or "observed"
            flag = str(payload.get("flag") or "").strip()
            rationale = str(payload.get("rationale") or "").strip()
            strategy_kind = str(payload.get("strategy_kind") or "").strip()
            strongest_hypothesis_kind = str(
                normalized_action_path_summary.get("strongestHypothesisKind") or ""
            ).strip()
            summary_bits = [decision]
            if flag:
                summary_bits.append(flag)
            if strategy_kind:
                summary_bits.append(strategy_kind)
            if strongest_hypothesis_kind:
                summary_bits.append(strongest_hypothesis_kind)
            summary_bits.extend(_exploit_summary_parts(normalized_exploit_provenance))
            summary = " · ".join(summary_bits)
            if rationale:
                summary = f"{summary} — {rationale}" if summary else rationale
            output_payload = dict(payload)
            if normalized_exploit_provenance:
                output_payload["exploit_provenance"] = normalized_exploit_provenance
            if normalized_action_path_summary:
                output_payload["action_path_summary"] = normalized_action_path_summary
            events.append({
                "id": f"outcome_{event_type}_{idx}",
                "type": "verify",
                "kind": event_type,
                "title": "verification decision",
                "summary": summary or event_type,
                "status": "failed" if decision == "rejected" else "done",
                "t": str(event.get("t") or _now_iso()),
                "output": json.dumps(output_payload, ensure_ascii=False, indent=2),
                "tokens": 0,
            })
            continue
        if event_type == "recovery_decision":
            action = str(payload.get("action") or "").strip()
            reason = str(payload.get("reason") or "").strip()
            chain_name = str(payload.get("chain_name") or "").strip()
            switched_from = str(normalized_action_path_summary.get("switchedFrom") or "").strip()
            strongest_hypothesis_kind = str(
                normalized_action_path_summary.get("strongestHypothesisKind") or ""
            ).strip()
            summary_bits = [action] if action else []
            if chain_name:
                summary_bits.append(f"chain={chain_name}")
            if switched_from:
                summary_bits.append(f"from={switched_from}")
            if strongest_hypothesis_kind:
                summary_bits.append(f"hypothesis={strongest_hypothesis_kind}")
            exploit_summary_parts = _exploit_summary_parts(normalized_exploit_provenance)
            if exploit_summary_parts:
                summary_bits.append("exploit=" + " ".join(exploit_summary_parts))
            summary = " · ".join(summary_bits)
            if reason:
                summary = f"{summary} — {reason}" if summary else reason
            output_payload = dict(payload)
            if normalized_exploit_provenance:
                output_payload["exploit_provenance"] = normalized_exploit_provenance
            if normalized_action_path_summary:
                output_payload["action_path_summary"] = normalized_action_path_summary
            events.append({
                "id": f"outcome_{event_type}_{idx}",
                "type": "system",
                "kind": event_type,
                "title": "recovery decision",
                "summary": summary or event_type,
                "status": "failed" if bool(payload.get("should_stop")) else "done",
                "t": str(event.get("t") or _now_iso()),
                "output": json.dumps(output_payload, ensure_ascii=False, indent=2),
                "tokens": 0,
            })
            continue
        if event_type == "task_finished":
            reason = str(payload.get("reason") or "").strip()
            chain_used = [str(item).strip() for item in list(payload.get("chain_used") or []) if str(item).strip()]
            missing_tools = [str(item).strip() for item in list(payload.get("missing_tools") or []) if str(item).strip()]
            summary_parts = [reason] if reason else []
            if chain_used:
                summary_parts.append("chain=" + " → ".join(chain_used))
            strongest_hypothesis_kind = str(
                normalized_action_path_summary.get("strongestHypothesisKind") or ""
            ).strip()
            if strongest_hypothesis_kind:
                summary_parts.append("hypothesis=" + strongest_hypothesis_kind)
            exploit_summary_parts = _exploit_summary_parts(normalized_exploit_provenance)
            if exploit_summary_parts:
                summary_parts.append("exploit=" + " ".join(exploit_summary_parts))
            if missing_tools:
                summary_parts.append("missing=" + ", ".join(missing_tools))
            output_payload = dict(payload)
            if normalized_exploit_provenance:
                output_payload["exploit_provenance"] = normalized_exploit_provenance
            if normalized_action_path_summary:
                output_payload["action_path_summary"] = normalized_action_path_summary
            events.append({
                "id": f"outcome_{event_type}_{idx}",
                "type": "system",
                "kind": event_type,
                "title": "task finished",
                "summary": " · ".join(summary_parts) or event_type,
                "status": "done" if bool(payload.get("success")) else "failed",
                "t": str(event.get("t") or _now_iso()),
                "output": json.dumps(output_payload, ensure_ascii=False, indent=2),
                "tokens": 0,
            })
            continue
        label = str(payload.get("label") or latest_checkpoint.get("label") or "").strip()
        checkpoint_id = str(
            payload.get("checkpoint_id")
            or latest_checkpoint.get("checkpointId")
            or effective_resume_context.get("checkpointId")
            or ""
        ).strip()
        stop_reason = str(
            latest_checkpoint.get("stopReason")
            or effective_resume_context.get("stopReason")
            or ""
        ).strip()
        summary_bits: list[str] = []
        if label:
            summary_bits.append(f"label={label}")
        if checkpoint_id:
            summary_bits.append(f"checkpoint={checkpoint_id}")
        if stop_reason:
            summary_bits.append(f"stop={stop_reason}")
        summary = " · ".join(summary_bits) or event_type
        output_payload = dict(payload)
        if session_run_id:
            output_payload["run_id"] = session_run_id
        if checkpoint_id:
            output_payload["checkpoint_id"] = checkpoint_id
        if label:
            output_payload["checkpoint_label"] = label
        if stop_reason:
            output_payload["stop_reason"] = stop_reason
        if latest_checkpoint:
            output_payload["latest_checkpoint"] = latest_checkpoint
        if effective_resume_context:
            output_payload["resume_context"] = effective_resume_context
            resume_summary = str(effective_resume_context.get("summary") or "").strip()
            if resume_summary:
                output_payload["resume_summary"] = resume_summary
        events.append({
            "id": f"outcome_{event_type}_{idx}",
            "type": "system",
            "kind": event_type,
            "title": "checkpoint written",
            "summary": summary,
            "status": "done",
            "t": str(event.get("t") or _now_iso()),
            "output": json.dumps(output_payload, ensure_ascii=False, indent=2),
            "tokens": 0,
        })
    return events


def _task_detail_payload(project_root: Path, task: dict[str, Any]) -> dict[str, Any]:
    item = _serialize_task(task)
    metrics = _pick_metrics_for_task(project_root, item)
    metrics_session_id = str(metrics.get("session_id") or "") if metrics else ""
    task_session_id = str(item.get("sessionId") or "")
    expected_session_id = task_session_id or metrics_session_id
    snapshot_task = dict(item)
    if expected_session_id:
        snapshot_task["sessionId"] = expected_session_id
    snapshot, snapshot_path, session_meta = _pick_session_snapshot(project_root, snapshot_task)
    messages = _build_messages_from_snapshot(item, snapshot) if snapshot else []
    messages_mode = "session_snapshot"
    if not messages and metrics:
        messages = _build_messages_from_metrics(item, metrics)
        messages_mode = "metrics_observed"
    elif not messages:
        messages_mode = "synthetic_fallback"
    plan = _build_plan_from_snapshot(snapshot) if snapshot else []
    notes, notes_sources = _load_task_notes(project_root, item)
    knowledge_hits = _build_knowledge_hits_from_snapshot(item, snapshot) if snapshot else []
    knowledge_mode = "session_snapshot"
    if not knowledge_hits and metrics:
        knowledge_hits = _build_knowledge_hits_from_metrics(item, metrics)
        if knowledge_hits:
            knowledge_mode = "metrics_observed"
        else:
            knowledge_mode = "unobserved"
    elif not knowledge_hits:
        knowledge_mode = "unobserved"
    hint_messages = _build_hint_messages(item)
    if hint_messages:
        messages = [*messages, *hint_messages]
    harness_session_context = _build_session_context_from_harness(project_root, item)
    inherited_session_context = (
        dict(item.get("sessionContext") or {})
        if isinstance(item.get("sessionContext"), dict)
        else None
    )
    session_context, session_context_mode = _resolve_task_session_context(
        harness_session_context,
        inherited_session_context,
    )
    item["hints"] = item.get("hints") if isinstance(item.get("hints"), list) else []
    item["messages"] = messages if isinstance(messages, list) else []
    item["plan"] = plan if isinstance(plan, list) else []
    item["notes"] = notes if isinstance(notes, list) else []
    item["knowledgeHits"] = knowledge_hits if isinstance(knowledge_hits, list) else []
    item["sessionContext"] = session_context
    item = _normalize_task_collections(item)
    if item["messages"]:
        item["messages"] = sorted(
            item["messages"],
            key=lambda msg: _sort_time_key(str(msg.get("t") or "")),
        )
    projection = _build_task_projection_fields(
        project_root=project_root,
        item=item,
        session_context=session_context,
        session_context_mode=session_context_mode,
        session_meta=session_meta,
        metrics_session_id=metrics_session_id,
        task_session_id=task_session_id,
        notes_sources=notes_sources,
        messages_mode=messages_mode,
        plan=plan,
        notes=notes,
        knowledge_mode=knowledge_mode,
        snapshot_path=snapshot_path,
    )
    item["detailSource"] = projection["detailSource"]
    item["blackboardSnapshot"] = projection["blackboardSnapshot"]
    item["decisionProvenance"] = projection["decisionProvenance"]
    item["exploitProvenance"] = projection["exploitProvenance"]
    item["recommendedActionSummary"] = projection["recommendedActionSummary"]
    item["candidateSummary"] = projection["candidateSummary"]
    item["lastActionResultSummary"] = projection["lastActionResultSummary"]
    item["pendingVerificationSummary"] = projection["pendingVerificationSummary"]
    item["strongestHypothesisSummary"] = projection["strongestHypothesisSummary"]
    item["suppressedRecommendationSummary"] = projection["suppressedRecommendationSummary"]
    item["activeDecisionSummary"] = projection["activeDecisionSummary"]
    item["actionPathSummary"] = projection["actionPathSummary"]
    item["nextActionExplanation"] = _build_next_action_explanation(
        item.get("controlDecision"),
        projection["actionPathSummary"],
        projection["decisionProvenance"],
    )
    item["resumeIngress"] = _build_resume_ingress_summary(session_context)
    item["capabilities"] = _task_capabilities(item)
    return item


def _build_session_context_from_harness(project_root: Path, task: dict[str, Any]) -> dict[str, Any]:
    run_id = str(task.get("currentRunId") or task.get("id") or "").strip()
    return _build_run_session_context(project_root, run_id)


def _resolve_task_session_context(
    harness_session_context: dict[str, Any] | None,
    inherited_session_context: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    if _session_context_has_observed_data(harness_session_context):
        return dict(harness_session_context or {}), "harness"
    if _session_context_has_observed_data(inherited_session_context):
        return dict(inherited_session_context or {}), "inherited_resume"
    return dict(harness_session_context or {}), "unobserved"


def _build_task_projection_fields(
    *,
    project_root: Path,
    item: dict[str, Any],
    session_context: dict[str, Any],
    session_context_mode: str,
    session_meta: dict[str, Any] | None,
    metrics_session_id: str,
    task_session_id: str,
    notes_sources: list[str] | None,
    messages_mode: str,
    plan: list[Any] | None,
    notes: list[Any] | None,
    knowledge_mode: str,
    snapshot_path: Path | None,
) -> dict[str, Any]:
    meta = dict(session_meta or {})
    detail_source = {
        "session": str(snapshot_path.relative_to(project_root)) if snapshot_path else None,
        "metrics": f"loot/metrics/metrics_{metrics_session_id}.json" if metrics_session_id else None,
        "notes": list(notes_sources or []),
        "messages": messages_mode,
        "plan": "session_snapshot" if plan else "unobserved",
        "notesMode": "observed" if notes else "empty",
        "knowledge": knowledge_mode,
        "knowledgeConfidence": "high" if knowledge_mode == "session_snapshot" else ("low" if knowledge_mode == "metrics_observed" else "none"),
        "messagesConfidence": "high" if messages_mode == "session_snapshot" else ("medium" if messages_mode == "metrics_observed" else "low"),
        "sessionMatchedBy": meta.get("matchedBy"),
        "sessionConfidence": meta.get("confidence"),
        "sessionExpectedId": meta.get("expectedSessionId"),
        "sessionBlockedReason": meta.get("blockedReason"),
        "sessionCandidateScore": meta.get("candidateScore"),
        "metricsSessionId": metrics_session_id or None,
        "taskSessionId": task_session_id or None,
        "sessionContext": session_context_mode,
    }
    if metrics_session_id and task_session_id and metrics_session_id != task_session_id:
        detail_source["sessionMismatch"] = {
            "taskSessionId": task_session_id,
            "metricsSessionId": metrics_session_id,
        }
    detail_source.update(_derived_target_detail_source(item))
    blackboard_snapshot = _merge_blackboard_snapshots(
        build_task_blackboard_snapshot(item, session_context=session_context),
        item.get("blackboardSnapshot") if isinstance(item.get("blackboardSnapshot"), dict) else None,
    )
    serialized_blackboard_snapshot = serialize_blackboard_snapshot(blackboard_snapshot)
    decision_provenance = _build_decision_provenance_summary(
        item.get("controlDecision"),
        serialized_blackboard_snapshot,
    )
    return {
        "detailSource": detail_source,
        "blackboardSnapshot": serialized_blackboard_snapshot,
        "decisionProvenance": decision_provenance,
        "exploitProvenance": _build_exploit_provenance_summary(
            serialized_blackboard_snapshot,
        ),
        "recommendedActionSummary": _build_recommended_action_summary(
            serialized_blackboard_snapshot,
        ),
        "candidateSummary": _build_candidate_summary(
            serialized_blackboard_snapshot,
        ),
        "lastActionResultSummary": _build_last_action_result_summary(
            serialized_blackboard_snapshot,
        ),
        "pendingVerificationSummary": _build_pending_verification_summary(
            serialized_blackboard_snapshot,
        ),
        "strongestHypothesisSummary": _build_strongest_hypothesis_summary(
            item.get("controlDecision"),
            serialized_blackboard_snapshot,
        ),
        "suppressedRecommendationSummary": _build_suppressed_recommendation_summary(
            item.get("controlDecision"),
            serialized_blackboard_snapshot,
        ),
        "activeDecisionSummary": _build_active_decision_summary(
            serialized_blackboard_snapshot,
        ),
        "actionPathSummary": _build_action_path_summary(
            item.get("controlDecision"),
            serialized_blackboard_snapshot,
            decision_provenance,
        ),
    }


def _iter_all_session_paths(project_root: Path) -> list[Path]:
    results: list[Path] = []
    seen: set[Path] = set()
    bases = [project_root / "loot" / "sessions"]
    workspaces_dir = project_root / "workspaces"
    if workspaces_dir.exists():
        for workspace_dir in workspaces_dir.iterdir():
            if workspace_dir.is_dir():
                bases.append(workspace_dir / "loot" / "sessions")
    for base in bases:
        if not base.exists():
            continue
        for path in sorted(base.glob("*.json")):
            if path.name == "index.json":
                continue
            resolved = path.resolve()
            if resolved not in seen:
                results.append(path)
                seen.add(resolved)
    return results


def _task_session_lookup(project_root: Path) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for task in _tasks.values():
        item = _serialize_task(task)
        metrics = _pick_metrics_for_task(project_root, item)
        session_id = str(item.get("sessionId") or (metrics.get("session_id") if metrics else "") or "")
        if session_id:
            lookup[session_id] = item
    return lookup


def _iter_metric_files(project_root: Path) -> list[Path]:
    metrics_dir = project_root / "loot" / "metrics"
    if not metrics_dir.exists():
        return []
    return sorted(metrics_dir.glob("metrics_*.json"))


def _load_metrics_data(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _pick_metrics_for_task(project_root: Path, task: dict[str, Any]) -> dict[str, Any] | None:
    started = _parse_iso(task.get("startedAt")) or _parse_iso(task.get("createdAt"))
    files = _iter_metric_files(project_root)
    if not files:
        return None

    candidates: list[tuple[int, float, Path, dict[str, Any]]] = []
    expected_tool_calls = int(task.get("toolCalls") or 0)
    expected_duration = _duration_ms_for_task(task)
    expected_run_id = str(task.get("currentRunId") or "")
    expected_task_id = str(task.get("id") or "")
    expected_target = str(task.get("target") or "")

    for path in files:
        data = _load_metrics_data(path)
        if not data:
            continue

        match_rank = 3
        metric_run_id = str(data.get("run_id") or "")
        metric_task_id = str(data.get("task_id") or "")
        metric_target = str(data.get("target") or "")
        if expected_run_id and metric_run_id == expected_run_id:
            match_rank = 0
        elif expected_task_id and metric_task_id == expected_task_id:
            match_rank = 1
        elif expected_target and metric_target and metric_target == expected_target:
            match_rank = 2

        score = 0.0
        metric_started = _parse_iso(data.get("started_at"))
        if started and metric_started:
            score += abs((metric_started - started).total_seconds())
        elif started or metric_started:
            score += 86_400.0

        metric_tools = int(data.get("total_tool_calls") or 0)
        score += abs(metric_tools - expected_tool_calls) * 30.0

        metric_duration = data.get("total_wall_time_ms")
        if expected_duration is not None and metric_duration is not None:
            score += abs(float(metric_duration) - float(expected_duration)) / 1000.0

        candidates.append((match_rank, score, path, data))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][3]


def _build_trace_payload(project_root: Path, task: dict[str, Any], include_timeline: bool = False) -> dict[str, Any]:
    item = _serialize_task(task)
    metrics = _pick_metrics_for_task(project_root, item)
    if metrics and not item.get("sessionId"):
        item["sessionId"] = metrics.get("session_id")
    turns = metrics.get("turns", []) if metrics else []
    input_tokens = sum(int(turn.get("input_tokens", 0) or 0) for turn in turns)
    output_tokens = sum(int(turn.get("output_tokens", 0) or 0) for turn in turns)
    total_tokens = int(metrics.get("total_tokens", item.get("tokensUsed", 0)) if metrics else item.get("tokensUsed", 0) or 0)
    total_tool_calls = int(metrics.get("total_tool_calls", item.get("toolCalls", 0)) if metrics else item.get("toolCalls", 0) or 0)
    total_steps = total_tool_calls if total_tool_calls > 0 else len(turns)
    metrics_session_id = str(metrics.get("session_id") or "") if metrics else ""
    snapshot_task = dict(item)
    if metrics_session_id and not snapshot_task.get("sessionId"):
        snapshot_task["sessionId"] = metrics_session_id
    snapshot, snapshot_path, _session_meta = _pick_session_snapshot(project_root, snapshot_task)
    session_context = _build_run_session_context(project_root, item.get("currentRunId") or item.get("sessionId") or item["id"])
    projection = _build_task_projection_fields(
        project_root=project_root,
        item=item,
        session_context=session_context,
        session_context_mode="harness" if _session_context_has_observed_data(session_context) else "unobserved",
        session_meta={},
        metrics_session_id=metrics_session_id,
        task_session_id=str(item.get("sessionId") or ""),
        notes_sources=[],
        messages_mode="unobserved",
        plan=[],
        notes=[],
        knowledge_mode="unobserved",
        snapshot_path=snapshot_path,
    )

    payload = {
        "id": item.get("currentRunId", item["id"]),
        "taskId": item["id"],
        "mode": item.get("mode"),
        "modeSubtype": item.get("modeSubtype"),
        "goalStyle": item.get("goalStyle"),
        "controlDecision": item.get("controlDecision"),
        "ctfChainUsed": item.get("ctfChainUsed", []),
        "ctfMissingTools": item.get("ctfMissingTools", []),
        "ctfNotes": item.get("ctfNotes", []),
        "ctfStateSnapshot": item.get("ctfStateSnapshot"),
        "blackboardSnapshot": projection["blackboardSnapshot"],
        "decisionProvenance": projection["decisionProvenance"],
        "exploitProvenance": projection["exploitProvenance"],
        "recommendedActionSummary": projection["recommendedActionSummary"],
        "candidateSummary": projection["candidateSummary"],
        "lastActionResultSummary": projection["lastActionResultSummary"],
        "pendingVerificationSummary": projection["pendingVerificationSummary"],
        "strongestHypothesisSummary": projection["strongestHypothesisSummary"],
        "suppressedRecommendationSummary": projection["suppressedRecommendationSummary"],
        "activeDecisionSummary": projection["activeDecisionSummary"],
        "actionPathSummary": projection["actionPathSummary"],
        "nextActionExplanation": _build_next_action_explanation(
            item.get("controlDecision"),
            projection["actionPathSummary"],
            projection["decisionProvenance"],
        ),
        "resumeIngress": _build_resume_ingress_summary(session_context),
        "decisionRecords": item.get("decisionRecords", []),
        "target": item.get("target"),
        "status": item.get("status"),
        "startedAt": item.get("startedAt"),
        "finishedAt": item.get("finishedAt"),
        "durationMs": item.get("durationMs"),
        "totalSteps": total_steps,
        "totalToolCalls": total_tool_calls,
        "totalTokens": total_tokens,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "finalFlag": item.get("finalFlag"),
        "sessionId": item.get("sessionId"),
        "detailSource": projection["detailSource"],
    }
    if include_timeline:
        payload["timeline"] = _build_trace_timeline(item, metrics)
        snapshot_tool_events = _extract_tool_events_from_snapshot(item, snapshot) if snapshot else []
        audit_tool_events = _extract_tool_audit_events_from_session_context(session_context)
        payload["toolEvents"] = [*snapshot_tool_events, *audit_tool_events]
        payload["sessionArtifacts"] = list(session_context.get("artifacts") or []) if isinstance(session_context, dict) else []
        payload["latestCheckpoint"] = (
            dict(session_context.get("latestCheckpoint") or {})
            if isinstance(session_context, dict) and isinstance(session_context.get("latestCheckpoint"), dict)
            else None
        )
        payload["outcomeEvents"] = _extract_outcome_events_from_session_context(
            session_context,
            projection["exploitProvenance"],
            projection["actionPathSummary"],
        )
        tool_events = payload["toolEvents"]
        tool_idx = 0
        for event in payload["timeline"]:
            if event.get("type") != "tool":
                continue
            while tool_idx < len(tool_events):
                tool_event = tool_events[tool_idx]
                if not event.get("tool") or not tool_event.get("tool") or event.get("tool") == tool_event.get("tool"):
                    break
                tool_idx += 1
            if tool_idx >= len(tool_events):
                break
            tool_event = tool_events[tool_idx]
            event["input"] = tool_event.get("input")
            event["output"] = tool_event.get("output")
            tool_idx += 1
    return payload


def _build_knowledge_usage(project_root: Path, path: Path) -> dict[str, Any]:
    relative_path = str(path.relative_to(project_root))
    title = path.stem.replace("_", " ").replace("-", " ")
    tokens = _doc_match_tokens(relative_path, path.stem, title)
    session_lookup = _task_session_lookup(project_root)
    hit_history: list[dict[str, Any]] = []
    related_runs: list[dict[str, Any]] = []
    cited_by: dict[str, int] = {}

    for session_path in _iter_all_session_paths(project_root):
        snapshot = _load_json_file(session_path)
        if not isinstance(snapshot, dict):
            continue
        session_id = str(snapshot.get("session_id") or session_path.stem)
        task = session_lookup.get(session_id)
        run_id = task.get("currentRunId") if task else None
        task_id = task.get("id") if task else None
        task_title = task.get("title") if task else None
        task_status = task.get("status") if task else None
        conversation = snapshot.get("conversation") if isinstance(snapshot.get("conversation"), list) else []
        total = len(conversation)
        pending_searches: list[dict[str, Any]] = []
        session_counted = False
        for idx, raw in enumerate(conversation):
            if not isinstance(raw, dict):
                continue
            t = _message_time_at(task or {}, snapshot, idx, total)
            role = str(raw.get("role") or "")
            if role == "assistant":
                tool_calls = raw.get("tool_calls") if isinstance(raw.get("tool_calls"), list) else []
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    tool_name = str(tool_call.get("name") or "")
                    if tool_name not in {"knowledge_search", "rag", "memory_query"}:
                        continue
                    arguments = tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {}
                    pending_searches.append({
                        "tool": tool_name,
                        "query": str(arguments.get("query") or ""),
                        "t": t,
                    })
                content = str(raw.get("content") or "")
                if _message_mentions_doc(content, tokens):
                    cited_by["assistant"] = cited_by.get("assistant", 0) + 1
            elif role == "tool_result":
                tool_results = raw.get("tool_results") if isinstance(raw.get("tool_results"), list) else []
                for result in tool_results:
                    if not isinstance(result, dict):
                        continue
                    tool_name = str(result.get("tool_name") or "")
                    output = str(result.get("result") or result.get("error") or "")
                    if tool_name in {"knowledge_search", "rag", "memory_query"} and _message_mentions_doc(output, tokens):
                        pending = pending_searches.pop(0) if pending_searches else {"query": "", "tool": tool_name, "t": t}
                        chunk_match = re.search(r"chunk[_\s:-]*(\d+)", output, re.IGNORECASE)
                        chunk_id = f"chunk_{int(chunk_match.group(1)):03d}" if chunk_match else None
                        hit_history.append({
                            "t": pending.get("t") or t,
                            "runId": run_id,
                            "chunkId": chunk_id,
                            "score": 1.0,
                            "query": pending.get("query") or "",
                        })
                        cited_by[pending.get("tool") or tool_name] = cited_by.get(pending.get("tool") or tool_name, 0) + 1
                        session_counted = True
                    elif _message_mentions_doc(output, tokens):
                        cited_by[tool_name or "tool_result"] = cited_by.get(tool_name or "tool_result", 0) + 1
            else:
                content = str(raw.get("content") or "")
                if _message_mentions_doc(content, tokens):
                    cited_by[role or "system"] = cited_by.get(role or "system", 0) + 1
        if session_counted:
            related_runs.append({
                "runId": run_id,
                "taskId": task_id,
                "taskTitle": task_title,
                "usedFor": hit_history[-1].get("query") or "knowledge_search",
                "status": task_status or "stopped",
            })

    hit_history.sort(key=lambda item: item.get("t") or "")
    related_runs_map: dict[str, dict[str, Any]] = {}
    for run in related_runs:
        key = str(run.get("runId") or run.get("taskId") or uuid.uuid4().hex)
        related_runs_map[key] = run
    related_runs = list(related_runs_map.values())

    heatmap = [0] * 24
    for hit in hit_history:
        dt = _parse_iso(hit.get("t"))
        if dt is not None:
            heatmap[dt.hour] += 1

    cited_by_list = [
        {"name": name, "count": count}
        for name, count in sorted(cited_by.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "hitCount": len(hit_history),
        "lastHitAt": hit_history[-1]["t"] if hit_history else None,
        "hitHistory": hit_history,
        "relatedRuns": related_runs,
        "citedBy": cited_by_list,
        "heatmap": heatmap,
    }


def _run_agent_task(task_id: str, payload: dict, project_root: Path) -> None:
    """Background thread: builds agent components and runs the agent loop."""
    task = _tasks[task_id]
    task["status"] = "running"
    task["startedAt"] = _now_iso()
    _bus.emit({
        "type": "task_status",
        "task_id": task_id,
        "run_id": task.get("currentRunId"),
        "t": task["startedAt"],
        "updates": {"status": "running", "startedAt": task["startedAt"]},
    })
    _bus.emit({
        "type": "task.started",
        "task_id": task_id,
        "run_id": task.get("currentRunId"),
        "t": task["startedAt"],
        "title": "task started",
        "summary": task.get("target") or task.get("title") or task_id,
    })
    saved_session_id: str | None = None

    try:
        import importlib

        from ..config.settings import get_settings
        from ..session import AgentSession

        settings = get_settings()
        initializer_module = importlib.import_module("flaghunter.interface.initializer")
        target = payload.get("target", "")
        max_iter = int(payload.get("maxIter", 30))
        goal = payload.get("goal") or _default_goal_for_payload(payload)
        use_docker = bool(payload.get("docker", False))
        flag_fmt = payload.get("flagFormat", r"flag\{[^}]+\}")

        async def _build_and_run() -> dict[str, Any]:
            nonlocal saved_session_id
            # ── Single assembly path (architecture invariant I2) ──────────
            # AgentSession.create funnels build_agent_components, so RAG,
            # workspace activation, runtime AND the CPA modules (M1-M6) all
            # initialize for web tasks too — previously this hand-rolled
            # assembly silently skipped the CPA hooks. CTF mode below reuses
            # session.runtime.
            session = await AgentSession.create(
                target=target,
                model=settings.model,
                docker=use_docker,
                no_mcp=True,
                on_progress=lambda level, msg: emit_log(level, "agent.init", str(msg)),
                builder=initializer_module.build_agent_components,
            )
            runtime = session.runtime
            rag = session.rag_engine

            if str(payload.get("mode") or "").lower() == "ctf":
                # CTF mode runs a separate execution engine (CTFTaskDispatcher),
                # NOT the FlagHunterAgent loop. It is intentionally not routed
                # through the AgentSession facade (which is an agent-loop
                # assembler/driver): the dispatcher has its own solve-chain
                # lifecycle and result shape. It reuses session.runtime — the
                # I2 assembly the facade just performed — which is the right
                # seam. Folding CTF into the facade would conflate two distinct
                # engines for no gain (H13: exempt, separate path by design).
                from ..agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

                ctf_subtype = str(payload.get("modeSubtype") or payload.get("ctfType") or "auto")
                if not isinstance(task.get("ingressHandoff"), dict):
                    _apply_control_decision(task)
                    task["ingressHandoff"] = _build_ingress_handoff(task)
                dispatcher_hint = _ctf_dispatcher_hint(task)
                crew_requested = (
                    str(payload.get("executionMode") or "").strip().lower() == "crew"
                    or bool(payload.get("crew"))
                )
                if crew_requested:
                    # CTF crew (multi-worker via CTFCrewCoordinator) — previously
                    # TUI-only; the shared headless runner gives web parity (D4).
                    # Returns the planning dispatcher so the downstream chain/
                    # snapshot/derived-target plumbing below is unchanged.
                    from ..agents.pa_agent.ctf_crew_runner import run_ctf_crew_solve

                    emit_log("info", "ctf.crew", f"Task {task_id} started (crew) — subtype: {ctf_subtype}, target: {target or '(none)'}")
                    solve_result, dispatcher = await run_ctf_crew_solve(
                        runtime=runtime,
                        llm=session.llm,
                        target=target,
                        goal=goal,
                        chtype=ctf_subtype,
                        hint=dispatcher_hint,
                        challenge_context=_build_ctf_challenge_context(task),
                        progress_callback=lambda message: emit_log("info", "ctf.crew", str(message)),
                        worker_event=lambda wid, evt, data: emit_log(
                            "info", "ctf.crew", f"[{wid}] {evt}" + (f" {data}" if data else "")
                        ),
                    )
                else:
                    emit_log("info", "ctf.dispatcher", f"Task {task_id} started — subtype: {ctf_subtype}, target: {target or '(none)'}")
                    dispatcher = CTFTaskDispatcher(
                        runtime=runtime,
                        progress_callback=lambda message: emit_log("info", "ctf.dispatcher", str(message)),
                    )
                    solve_result = await _run_ctf_dispatcher_with_handoff(
                        dispatcher,
                        target=target,
                        goal=goal,
                        ctf_type=ctf_subtype,
                        hint=dispatcher_hint,
                        challenge_context=_build_ctf_challenge_context(task),
                        ingress_handoff=(
                            dict(task.get("ingressHandoff") or {})
                            if isinstance(task.get("ingressHandoff"), dict)
                            else None
                        ),
                    )
                chain_used = [str(item) for item in (getattr(solve_result, "chain_used", None) or []) if str(item or "").strip()]
                task["ctfChainUsed"] = chain_used
                if chain_used:
                    emit_log("info", "ctf.dispatcher", f"chains: {', '.join(chain_used)}")
                missing_tools = [str(item) for item in (getattr(solve_result, "missing_tools", None) or []) if str(item or "").strip()]
                task["ctfMissingTools"] = missing_tools
                if missing_tools:
                    emit_log("warn", "ctf.dispatcher", f"missing tools: {', '.join(missing_tools)}")
                task["ctfNotes"] = [str(item) for item in (getattr(solve_result, "notes", None) or []) if str(item or "").strip()]
                _sync_runtime_challenge_context(task, dispatcher)
                dispatcher_state = getattr(dispatcher, "state", None)
                if dispatcher_state is not None and hasattr(dispatcher_state, "to_snapshot"):
                    try:
                        task["ctfStateSnapshot"] = dispatcher_state.to_snapshot()
                    except Exception:
                        pass
                return {
                    "output": str(getattr(solve_result, "flag", "") or getattr(solve_result, "reason", "") or ""),
                    "final_flag": getattr(solve_result, "flag", None),
                    "stop_reason": None if getattr(solve_result, "flag", None) else (getattr(solve_result, "reason", None) or "no_flag_found"),
                }

            # ── Agent (assembled by the facade) ───────────────────────────
            # build_agent_components already wired the LLM, tools, RAG, the
            # CPA modules, _session_store and _metrics. Only the per-task
            # knobs are applied here.
            agent = session.agent
            agent.max_iterations = max_iter
            agent.run_id = task.get("currentRunId")
            agent.project_root = project_root

            # ── Run agent loop ───────────────────────────────────────────
            import re
            final_flag = None
            result_text: list[str] = []
            tokens_used = 0
            tool_calls_count = 0

            emit_log("info", "agent", f"Task {task_id} started — target: {target or '(none)'}")

            async for msg in agent.agent_loop(goal):
                # Emit real-time events for the SSE bus
                if msg.tool_calls:
                    turn_tool_names: list[str] = []
                    for tc in msg.tool_calls:
                        tool_calls_count += 1
                        turn_tool_names.append(tc.name)
                        _bus.emit({
                            "type": "tool_call",
                            "task_id": task_id,
                            "run_id": task.get("currentRunId"),
                            "tool": tc.name,
                            "summary": str(tc.arguments)[:200],
                            "kind": "tool.called",
                            "t": _now_iso(),
                            "timestamp": _now_iso(),
                        })
                        task["toolCalls"] = tool_calls_count
                        emit_log("info", f"tool.{tc.name}", f"{tc.name}: {str(tc.arguments)[:200]}")

                    # F1: record turn-level metrics to dashboard aggregator
                    input_toks = msg.usage.get("input_tokens", 0) if msg.usage else 0
                    output_toks = msg.usage.get("output_tokens", 0) if msg.usage else 0
                    _aggregator.record_turn(
                        input_tokens=input_toks,
                        output_tokens=output_toks,
                        tool_names=turn_tool_names,
                        knowledge_hits=1 if any(
                            tn in ("knowledge_search", "rag", "memory_query")
                            for tn in turn_tool_names
                        ) else 0,
                    )

                if msg.usage:
                    usage = msg.usage
                    tokens_used += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                    task["tokensUsed"] = tokens_used

                if msg.tool_results:
                    for tool_result in msg.tool_results:
                        tool_name = getattr(tool_result, "tool_name", "") or "tool"
                        preview = _single_line_preview(
                            getattr(tool_result, "result", None)
                            or getattr(tool_result, "error", None)
                        )
                        event_t = _now_iso()
                        finished_event = {
                            "type": "tool.finished",
                            "task_id": task_id,
                            "run_id": task.get("currentRunId"),
                            "tool": tool_name,
                            "success": bool(getattr(tool_result, "success", True)),
                            "duration_ms": getattr(tool_result, "duration_ms", 0.0),
                            "summary": preview,
                            "output": _truncate_text(str(getattr(tool_result, "result", "") or getattr(tool_result, "error", "") or ""), 4000),
                            "kind": "tool.finished",
                            "t": event_t,
                        }
                        _bus.emit(finished_event)

                        if tool_name in {"knowledge_search", "rag", "memory_query"} and getattr(tool_result, "success", True):
                            _bus.emit({
                                "type": "knowledge.retrieved",
                                "task_id": task_id,
                                "run_id": task.get("currentRunId"),
                                "source": tool_name,
                                "summary": preview,
                                "output": _truncate_text(str(getattr(tool_result, "result", "") or ""), 4000),
                                "kind": "knowledge.retrieved",
                                "t": event_t,
                            })

                        if tool_name == "notes" and getattr(tool_result, "success", True):
                            _bus.emit({
                                "type": "note.created",
                                "task_id": task_id,
                                "run_id": task.get("currentRunId"),
                                "summary": preview,
                                "output": _truncate_text(str(getattr(tool_result, "result", "") or ""), 4000),
                                "kind": "note.created",
                                "t": event_t,
                            })
                    try:
                        live_session_id = agent.save_session()
                    except Exception:
                        live_session_id = getattr(agent, "_session_id", None)
                    if live_session_id:
                        saved_session_id = live_session_id
                        task["sessionId"] = live_session_id

                if msg.content:
                    result_text.append(msg.content)
                    # Scan for flag in content
                    flags_found = re.findall(flag_fmt, msg.content)
                    if flags_found and not final_flag:
                        final_flag = flags_found[0]
                        emit_log("info", "agent.observer", f"Flag detected: {final_flag}")

                # Emit progress update
                _bus.emit({
                    "type": "task_status",
                    "task_id": task_id,
                    "run_id": task.get("currentRunId"),
                    "t": _now_iso(),
                    "updates": {
                        "tokensUsed": tokens_used,
                        "toolCalls": tool_calls_count,
                    },
                })

            try:
                saved_session_id = agent.save_session()
            except Exception:
                saved_session_id = getattr(agent, "_session_id", None)
            return {
                "output": "\n".join(result_text),
                "final_flag": final_flag,
                "stop_reason": None if final_flag else "no_flag_found",
            }

        loop = asyncio.new_event_loop()
        run_result = loop.run_until_complete(_build_and_run())
        loop.close()

        # Final flag extraction from full result
        import re
        result = str(run_result.get("output", "") or "")
        final_flag = run_result.get("final_flag")
        if not final_flag:
            flags = re.findall(flag_fmt, result or "")
            final_flag = flags[0] if flags else None
        stop_reason = run_result.get("stop_reason") or (None if final_flag else "no_flag_found")

        task.update({
            "status": "success" if final_flag else "stopped",
            "finishedAt": _now_iso(),
            "finalFlag": final_flag,
            "stopReason": stop_reason,
        })
        if saved_session_id:
            task["sessionId"] = saved_session_id
        if final_flag:
            emit_log("info", "agent", f"Task {task_id} completed — flag captured")
        else:
            emit_log("warn", "agent", f"Task {task_id} stopped — {stop_reason or 'no_flag_found'}")
            _aggregator.record_failure(stop_reason or "no_flag_found")
    except Exception as exc:
        logger.exception("Agent task %s failed: %s", task_id, exc)
        stop_reason = str(exc)[:120]
        task.update({
            "status": "failed",
            "finishedAt": _now_iso(),
            "stopReason": stop_reason,
        })
        if saved_session_id:
            task["sessionId"] = saved_session_id
        emit_log("error", "agent", f"Task {task_id} failed: {stop_reason}")
        _aggregator.record_failure(stop_reason)

    _bus.emit({
        "type": "task_status",
        "task_id": task_id,
        "run_id": task.get("currentRunId"),
        "t": task.get("finishedAt") or _now_iso(),
        "updates": {k: task[k] for k in ("status", "finishedAt", "finalFlag", "stopReason") if k in task},
    })
    _bus.emit({
        "type": f"task.{task.get('status')}",
        "task_id": task_id,
        "run_id": task.get("currentRunId"),
        "t": task.get("finishedAt") or _now_iso(),
        "title": f"task {task.get('status')}",
        "summary": task.get("finalFlag") or task.get("stopReason") or task.get("status"),
    })

    _persist_tasks(project_root)


def _persist_tasks(project_root: Path) -> None:
    path = project_root / "loot" / "web_tasks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(list(_tasks.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Could not persist tasks: %s", e)


def _load_tasks(project_root: Path) -> None:
    path = project_root / "loot" / "web_tasks.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for t in data:
                _tasks[t["id"]] = t
        except Exception as e:
            logger.warning("Could not load tasks: %s", e)


def _seed_aggregator_from_metrics(project_root: Path) -> None:
    """Replay historical turn data from loot/metrics/*.json into the aggregator."""
    metrics_dir = project_root / "loot" / "metrics"
    if not metrics_dir.exists():
        return
    for f in sorted(metrics_dir.glob("metrics_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for turn in data.get("turns", []):
                _aggregator.record_turn(
                    input_tokens=turn.get("input_tokens", 0),
                    output_tokens=turn.get("output_tokens", 0),
                    tool_names=turn.get("tool_calls", []),
                )
        except Exception:
            pass


# ── Route handlers ────────────────────────────────────────────────────────────

def _make_handlers(project_root: Path):
    console_dir = project_root / "web" / "console"

    async def get_status(req: web.Request) -> web.Response:
        from ..config.constants import APP_VERSION
        from ..config.settings import get_settings
        s = get_settings()
        return web.json_response({
            "ok": True,
            "version": APP_VERSION,
            "model": s.model,
            "runtime": "LocalRuntime",
            "tasks": {"total": len(_tasks), "running": sum(1 for t in _tasks.values() if t["status"] == "running")},
        })

    async def get_settings_handler(req: web.Request) -> web.Response:
        try:
            data = _settings_to_api(project_root)
            return web.json_response(data)
        except Exception as e:
            logger.exception("get_settings error")
            return web.json_response({"error": str(e)}, status=500)

    async def put_settings_handler(req: web.Request) -> web.Response:
        try:
            payload = await req.json()
            result = _apply_settings(project_root, payload)
            return web.json_response({"ok": True, **result, "settings": _settings_to_api(project_root)})
        except Exception as e:
            logger.exception("put_settings error")
            return web.json_response({"error": str(e)}, status=500)

    async def post_mcp_server(req: web.Request) -> web.Response:
        try:
            payload = await req.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        name = str(payload.get("name") or "").strip()
        url = str(payload.get("url") or "").strip()
        if not name:
            return web.json_response({"error": "name required"}, status=400)
        if not url.startswith("http://") and not url.startswith("https://"):
            return web.json_response({"error": "valid sse url required"}, status=400)

        try:
            mcp_manager = _mcp_manager_for_project(project_root)
            mcp_manager.add_sse_server(name=name, url=url)
            return web.json_response({"ok": True, "settings": _settings_to_api(project_root)})
        except Exception as e:
            logger.exception("post_mcp_server error")
            return web.json_response({"error": str(e)}, status=500)

    async def post_runtime_test(req: web.Request) -> web.Response:
        from ..interface import initializer as initializer_module

        settings_payload = _settings_to_api(project_root)
        runtime_cfg = settings_payload.get("runtime", {})
        mode = str(runtime_cfg.get("mode") or "local")
        docker_enabled = bool(runtime_cfg.get("dockerEnabled"))
        auto_ssh = bool(runtime_cfg.get("autoSsh"))

        runtime = None
        try:
            runtime, runtime_info = await initializer_module.build_runtime(
                docker=(mode == "docker") or docker_enabled,
                ssh=(mode == "ssh"),
                auto_ssh=auto_ssh,
            )
            healthy = bool(runtime_info.get("connected")) or runtime_info.get("selected") == "local"
            return web.json_response({
                "ok": True,
                "healthy": healthy,
                "runtime": runtime_info,
                "testedAt": _now_iso(),
            })
        except Exception as e:
            logger.exception("post_runtime_test error")
            return web.json_response({"ok": False, "error": str(e)}, status=500)
        finally:
            if runtime is not None:
                try:
                    await runtime.stop()
                except Exception:
                    pass

    async def get_tasks(req: web.Request) -> web.Response:
        tasks = [_build_task_list_payload(project_root, task) for task in _tasks.values()]
        # sort newest first
        tasks.sort(key=lambda t: t.get("createdAt", ""), reverse=True)
        return web.json_response(tasks)

    async def post_task(req: web.Request) -> web.Response:
        try:
            payload = await req.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        readiness = dict(_settings_to_api(project_root).get("model", {}).get("readiness") or {})
        if readiness.get("ready") is False:
            return web.json_response(
                {
                    "error": "model not ready",
                    "reason": str(readiness.get("reason") or ""),
                    "readiness": readiness,
                },
                status=409,
            )

        tid = _task_id()
        rid = _run_id()
        task = {
            "id": tid,
            "title": payload.get("title") or payload.get("target", ""),
            "target": payload.get("target", ""),
            "goal": payload.get("goal", ""),
            "mode": payload.get("mode", "pentest"),
            "maxIter": payload.get("maxIter", 30),
            "docker": payload.get("docker", False),
            "flagFormat": payload.get("flagFormat", r"flag\{[^}]+\}"),
            "status": "queued",
            "createdAt": _now_iso(),
            "startedAt": None,
            "finishedAt": None,
            "tokensUsed": 0,
            "toolCalls": 0,
            "finalFlag": None,
            "stopReason": None,
            "currentRunId": rid,
            "sparkSeed": [1, 1, 1, 1],
            "hints": [],
            "messages": [],
            "plan": [],
            "notes": [],
            "knowledgeHits": [],
            "attachments": [],
            "challengePath": None,
            "artifactPaths": [],
        }
        payload = _apply_mode_contract(task, payload)
        payload = _apply_task_asset_contract(task, payload)
        payload = _ensure_effective_goal(task, payload)
        decision = _apply_control_decision(
            task,
            blackboard_snapshot=payload.get("blackboardSnapshot") if isinstance(payload.get("blackboardSnapshot"), dict) else None,
        )
        task["ingressHandoff"] = _build_ingress_handoff(task)
        if decision.get("shouldRun") is False:
            task["status"] = "blocked"
        _tasks[tid] = task
        _persist_tasks(project_root)

        _bus.emit({"type": "task_created", "task": task, "task_id": tid, "run_id": rid, "t": task["createdAt"]})

        if decision.get("shouldRun") is not False:
            # Start agent in background thread
            t = threading.Thread(
                target=_run_agent_task,
                args=(tid, payload, project_root),
                daemon=True,
                name=f"agent-{tid}",
            )
            _task_threads[tid] = t
            t.start()

        return web.json_response(_serialize_task(task), status=201)

    async def replay_trace(req: web.Request) -> web.Response:
        run_id = req.match_info["runId"]
        source_task = next((t for t in _tasks.values() if t.get("currentRunId", t.get("id")) == run_id), None)
        if not source_task:
            return web.json_response({"error": "not found"}, status=404)

        payload = {
            "title": source_task.get("title") or source_task.get("target", ""),
            "target": source_task.get("target", ""),
            "goal": source_task.get("goal", ""),
            "mode": source_task.get("mode", "pentest"),
            "maxIter": source_task.get("maxIter", 30),
            "docker": source_task.get("docker", False),
            "flagFormat": source_task.get("flagFormat", r"flag\{[^}]+\}"),
            "challengePath": source_task.get("challengePath"),
            "artifactPaths": source_task.get("artifactPaths", []),
        }
        payload.update(_source_derived_target_contract(source_task))
        if str(source_task.get("mode") or "").lower() == "ctf":
            payload["ctfType"] = source_task.get("ctfType", source_task.get("modeSubtype", source_task.get("detectedType", "unknown")))
        if not str(payload.get("target") or "").strip() and not str(payload.get("derivedTarget") or "").strip():
            return web.json_response({"error": "target required"}, status=400)

        tid = _task_id()
        rid = _run_id()
        task = {
            "id": tid,
            "title": payload.get("title") or payload.get("target", ""),
            "target": payload.get("target", ""),
            "goal": payload.get("goal", ""),
            "mode": payload.get("mode", "pentest"),
            "maxIter": payload.get("maxIter", 30),
            "docker": payload.get("docker", False),
            "flagFormat": payload.get("flagFormat", r"flag\{[^}]+\}"),
            "status": "queued",
            "createdAt": _now_iso(),
            "startedAt": None,
            "finishedAt": None,
            "tokensUsed": 0,
            "toolCalls": 0,
            "finalFlag": None,
            "stopReason": None,
            "currentRunId": rid,
            "sparkSeed": [1, 1, 1, 1],
            "hints": [],
            "messages": [],
            "plan": [],
            "notes": [],
            "knowledgeHits": [],
            "attachments": [],
            "challengePath": None,
            "artifactPaths": [],
        }
        task.update(_source_derived_target_contract(source_task))
        payload = _apply_mode_contract(task, payload, source_task=source_task)
        payload = _apply_task_asset_contract(task, payload)
        payload = _ensure_effective_goal(task, payload)
        task.update(_merge_resume_lineage_with_source_task(
            _build_resume_lineage_payload(project_root, run_id),
            source_task,
        ))
        _inherit_source_blackboard_seed(task, source_task)
        _apply_control_decision(task)
        if str(task.get("mode") or "").lower() == "ctf":
            _apply_followup_recommended_control_decision(task, source="web_replay")
        task["ingressHandoff"] = _build_ingress_handoff(task)
        _inherit_source_challenge_context(task, source_task)
        _tasks[tid] = task
        _persist_tasks(project_root)

        _bus.emit({"type": "task_created", "task": task, "task_id": tid, "run_id": rid, "t": task["createdAt"]})

        t = threading.Thread(
            target=_run_agent_task,
            args=(tid, payload, project_root),
            daemon=True,
            name=f"agent-{tid}",
        )
        _task_threads[tid] = t
        t.start()

        return web.json_response(_serialize_task(task))

    async def retry_task(req: web.Request) -> web.Response:
        task_id = req.match_info["taskId"]
        source_task = _tasks.get(task_id)
        if not source_task:
            return web.json_response({"error": "not found"}, status=404)

        if not _task_capabilities(source_task).get("retry"):
            return web.json_response({"error": "retry unsupported"}, status=409)

        payload = {
            "title": source_task.get("title") or source_task.get("target", ""),
            "target": source_task.get("target", ""),
            "goal": source_task.get("goal", ""),
            "mode": source_task.get("mode", "pentest"),
            "maxIter": source_task.get("maxIter", 30),
            "docker": source_task.get("docker", False),
            "flagFormat": source_task.get("flagFormat", r"flag\{[^}]+\}"),
            "challengePath": source_task.get("challengePath"),
            "artifactPaths": source_task.get("artifactPaths", []),
        }
        payload.update(_source_derived_target_contract(source_task))
        if str(source_task.get("mode") or "").lower() == "ctf":
            payload["ctfType"] = source_task.get("ctfType", source_task.get("modeSubtype", source_task.get("detectedType", "unknown")))
        if not str(payload.get("target") or "").strip() and not str(payload.get("derivedTarget") or "").strip():
            return web.json_response({"error": "target required"}, status=400)

        tid = _task_id()
        rid = _run_id()
        task = {
            "id": tid,
            "title": payload.get("title") or payload.get("target", ""),
            "target": payload.get("target", ""),
            "goal": payload.get("goal", ""),
            "mode": payload.get("mode", "pentest"),
            "maxIter": payload.get("maxIter", 30),
            "docker": payload.get("docker", False),
            "flagFormat": payload.get("flagFormat", r"flag\{[^}]+\}"),
            "status": "queued",
            "createdAt": _now_iso(),
            "startedAt": None,
            "finishedAt": None,
            "tokensUsed": 0,
            "toolCalls": 0,
            "finalFlag": None,
            "stopReason": None,
            "currentRunId": rid,
            "sparkSeed": [1, 1, 1, 1],
            "hints": [],
            "messages": [],
            "plan": [],
            "notes": [],
            "knowledgeHits": [],
            "attachments": [],
            "challengePath": None,
            "artifactPaths": [],
        }
        task.update(_source_derived_target_contract(source_task))
        payload = _apply_mode_contract(task, payload, source_task=source_task)
        payload = _apply_task_asset_contract(task, payload)
        payload = _ensure_effective_goal(task, payload)
        task.update(_merge_resume_lineage_with_source_task(
            _build_resume_lineage_payload(project_root, source_task.get("currentRunId") or source_task.get("id")),
            source_task,
        ))
        _inherit_source_blackboard_seed(task, source_task)
        _apply_control_decision(task)
        if str(task.get("mode") or "").lower() == "ctf":
            _apply_followup_recommended_control_decision(task, source="web_retry")
        task["ingressHandoff"] = _build_ingress_handoff(task)
        _inherit_source_challenge_context(task, source_task)
        _tasks[tid] = task
        _persist_tasks(project_root)

        _bus.emit({"type": "task_created", "task": task, "task_id": tid, "run_id": rid, "t": task["createdAt"]})

        t = threading.Thread(
            target=_run_agent_task,
            args=(tid, payload, project_root),
            daemon=True,
            name=f"agent-{tid}",
        )
        _task_threads[tid] = t
        t.start()

        return web.json_response(_serialize_task(task))

    async def continue_task(req: web.Request) -> web.Response:
        task_id = req.match_info["taskId"]
        task = _tasks.get(task_id)
        if not task:
            return web.json_response({"error": "not found"}, status=404)

        if not _task_capabilities(task).get("continue"):
            return web.json_response({"error": "continue unsupported"}, status=409)

        continue_entry = {
            "text": "__continue__",
            "t": _now_iso(),
            "source": "continue",
        }
        if isinstance(task.get("hints"), list):
            task["hints"].append(continue_entry)
        else:
            task["hints"] = [continue_entry]

        _bus.emit({
            "type": "task.continue",
            "task_id": task_id,
            "run_id": task.get("currentRunId"),
            "t": continue_entry["t"],
            "text": continue_entry["text"],
        })
        emit_log("info", "agent.continue", f"Task {task_id} continue accepted")
        lineage_payload = _build_resume_lineage_payload(
            project_root,
            task.get("currentRunId") or task.get("id"),
        )
        pre_continue_ingress_handoff = (
            dict(task.get("ingressHandoff") or {})
            if isinstance(task.get("ingressHandoff"), dict)
            else {}
        )
        pre_continue_control_decision = (
            dict(task.get("controlDecision") or {})
            if isinstance(task.get("controlDecision"), dict)
            else {}
        )
        pre_continue_blackboard_snapshot = (
            dict(task.get("blackboardSnapshot") or {})
            if isinstance(task.get("blackboardSnapshot"), dict)
            else {}
        )
        pre_continue_decision_provenance = _build_decision_provenance_summary(
            pre_continue_control_decision,
            pre_continue_blackboard_snapshot,
        )
        pre_continue_action_path_summary = _build_action_path_summary(
            pre_continue_control_decision,
            pre_continue_blackboard_snapshot,
            pre_continue_decision_provenance,
        )
        task.update({
            "resumeFromRunId": lineage_payload.get("resumeFromRunId"),
            "resumeFromCheckpointId": lineage_payload.get("resumeFromCheckpointId"),
            "resumeSummary": lineage_payload.get("resumeSummary"),
        })
        if str(task.get("mode") or "").lower() == "ctf":
            existing_handoff = (
                dict(task.get("ingressHandoff") or {})
                if isinstance(task.get("ingressHandoff"), dict)
                else {}
            )
            _apply_followup_recommended_control_decision(task, source="web_continue")
            task["ingressHandoff"] = _build_ingress_handoff(task)
            _inherit_source_challenge_context(task, {"ingressHandoff": existing_handoff})
        _persist_tasks(project_root)
        return web.json_response({
            "ok": True,
            "taskId": task_id,
            "runId": task.get("currentRunId"),
            "accepted": True,
            "resumeFromRunId": lineage_payload.get("resumeFromRunId"),
            "resumeFromCheckpointId": lineage_payload.get("resumeFromCheckpointId"),
            "resumeSummary": lineage_payload.get("resumeSummary"),
            "nextActionExplanation": (
                _build_ingress_handoff_explanation(pre_continue_ingress_handoff)
                or _build_next_action_explanation(
                    pre_continue_control_decision,
                    pre_continue_action_path_summary,
                    pre_continue_decision_provenance,
                )
            ),
            "sessionContext": lineage_payload.get("sessionContext"),
            "challengeContext": (
                dict(task.get("ingressHandoff", {}).get("challengeContext") or {})
                if isinstance(task.get("ingressHandoff"), dict)
                and isinstance(task.get("ingressHandoff", {}).get("challengeContext"), dict)
                else {}
            ),
        })

    async def get_task(req: web.Request) -> web.Response:
        tid = req.match_info["taskId"]
        task = _tasks.get(tid)
        if not task:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response(_task_detail_payload(project_root, task))

    async def stop_task(req: web.Request) -> web.Response:
        tid = req.match_info["taskId"]
        task = _tasks.get(tid)
        if not task:
            return web.json_response({"error": "not found"}, status=404)
        task["status"] = "stopped"
        task["finishedAt"] = _now_iso()
        task["stopReason"] = "user_stop"
        _bus.emit({
            "type": "task_status",
            "task_id": tid,
            "run_id": task.get("currentRunId"),
            "t": task["finishedAt"],
            "updates": {"status": "stopped", "finishedAt": task["finishedAt"], "stopReason": "user_stop"},
        })
        _bus.emit({
            "type": "task.stopped",
            "task_id": tid,
            "run_id": task.get("currentRunId"),
            "t": task["finishedAt"],
            "title": "task stopped",
            "summary": "user_stop",
        })
        _persist_tasks(project_root)
        return web.json_response({"ok": True})

    async def post_hint(req: web.Request) -> web.Response:
        tid = req.match_info["taskId"]
        try:
            body = await req.json()
            text = body.get("text", "")
        except Exception:
            text = ""
        task = _tasks.get(tid) or {}
        hint_entry = {
            "text": text,
            "t": _now_iso(),
            "runId": task.get("currentRunId"),
        }
        if isinstance(task.get("hints"), list):
            task["hints"].append(hint_entry)
        else:
            task["hints"] = [hint_entry]
        _bus.emit({
            "type": "hint",
            "task_id": tid,
            "run_id": task.get("currentRunId"),
            "text": text,
            "t": hint_entry["t"],
        })
        emit_log("info", "agent.hint", f"Task {tid} hint accepted: {text or '(empty)'}")
        if task:
            _persist_tasks(project_root)
        return web.json_response({"ok": True})

    async def get_dashboard(req: web.Request) -> web.Response:
        params = req.rel_url.query
        window_filter = str(params.get("window") or "24h").lower()
        runtime_filter = str(params.get("runtime") or "all").lower()
        if window_filter not in {"24h", "all"}:
            window_filter = "24h"
        if runtime_filter not in {"all", "local", "docker", "ssh"}:
            runtime_filter = "all"

        def _task_runtime_kind(task: dict[str, Any]) -> str:
            runtime_info = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
            selected = str(runtime_info.get("selected") or "").lower()
            if selected == "ssh":
                return "ssh"
            if task.get("docker"):
                return "docker"
            return "local"

        def _task_time(task: dict[str, Any]) -> datetime | None:
            return _parse_iso(task.get("startedAt")) or _parse_iso(task.get("createdAt"))

        now_dt = datetime.now(timezone.utc)
        all_tasks = list(_tasks.values())
        filtered_tasks = []
        for task in all_tasks:
            if runtime_filter != "all" and _task_runtime_kind(task) != runtime_filter:
                continue
            if window_filter == "24h":
                task_time = _task_time(task)
                if not task_time or (now_dt - task_time) > timedelta(hours=24):
                    continue
            filtered_tasks.append(task)

        all_tasks = filtered_tasks
        running = [t for t in all_tasks if t["status"] == "running"]
        queued = [t for t in all_tasks if t["status"] == "queued"]
        succeeded = [t for t in all_tasks if t["status"] == "success"]
        failed = [t for t in all_tasks if t["status"] == "failed"]
        stopped = [t for t in all_tasks if t["status"] == "stopped"]
        sorted_tasks = sorted(all_tasks, key=lambda t: t.get("createdAt") or t.get("startedAt") or "", reverse=True)
        flags = [
            {
                "id": t["id"],
                "flag": t["finalFlag"],
                "target": t.get("target", ""),
                "t": t.get("finishedAt") or t.get("startedAt") or t.get("createdAt"),
                "type": t.get("modeSubtype") or t.get("detectedType") or t.get("ctfType"),
            }
            for t in sorted_tasks
            if t.get("finalFlag")
        ]

        total_tokens = sum(t.get("tokensUsed", 0) for t in all_tasks)
        # Rough cost estimate: ~$3/1M input, ~$15/1M output for Claude
        estimated_cost = round(total_tokens / 1_000_000 * 6, 2)

        series = _aggregator.get_summary()
        recent_tasks = []
        for t in sorted_tasks[:6]:
            serialized = _build_task_list_payload(project_root, t)
            recent_tasks.append(
                {
                    "id": serialized["id"],
                    "title": serialized.get("title") or serialized.get("target", ""),
                    "mode": serialized.get("mode"),
                    "modeSubtype": serialized.get("modeSubtype"),
                    "goalStyle": serialized.get("goalStyle"),
                    "status": serialized.get("status"),
                    "startedAt": serialized.get("startedAt"),
                    "finishedAt": serialized.get("finishedAt"),
                    "nextActionSummary": (
                        str(
                            serialized.get("nextActionExplanation", {}).get("summary") or ""
                        ).strip()
                        or None
                    ),
                    "activeDecisionSummary": (
                        str(
                            serialized.get("activeDecisionSummary", {}).get("summary") or ""
                        ).strip()
                        or None
                    ),
                    "resumeStateSummary": serialized.get("resumeStateSummary"),
                    "checkpointStateSummary": serialized.get("checkpointStateSummary"),
                    "runtimeOutcomeSummary": serialized.get("runtimeOutcomeSummary"),
                }
            )

        recent_tool_calls: list[dict[str, Any]] = []
        for task in sorted_tasks[:12]:
            run_id = str(task.get("currentRunId") or task.get("id") or "").strip()
            if not run_id:
                continue
            session_context = _build_run_session_context(project_root, run_id)
            for event in _extract_tool_audit_events_from_session_context(session_context):
                recent_tool_calls.append({
                    "id": str(event.get("id") or f"tool_{run_id}"),
                    "time": event.get("t"),
                    "tool": event.get("tool") or "",
                    "summary": event.get("summary") or "",
                    "status": (
                        "running"
                        if event.get("status") == "running"
                        else ("failed" if event.get("status") == "failed" else "success")
                    ),
                    "runId": run_id,
                    "taskId": str(task.get("id") or ""),
                })

        recent_tool_calls.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
        if recent_tool_calls:
            recent_tool_calls = recent_tool_calls[:6]
        else:
            log_entries = await _collect_log_entries()
            filtered_task_ids = {str(t.get("id") or "") for t in all_tasks}
            filtered_run_ids = {str(t.get("currentRunId") or "") for t in all_tasks}
            recent_tool_calls = [
                {
                    "id": entry["id"],
                    "time": entry.get("t"),
                    "tool": entry.get("source", ""),
                    "summary": entry.get("msg", ""),
                    "status": "failed" if entry.get("level") == "error" else "success",
                    "runId": entry.get("runId") or "—",
                    "taskId": entry.get("taskId") or "",
                }
                for entry in log_entries
                if str(entry.get("source", "")).startswith("tool")
                and (
                    not filtered_task_ids
                    or str(entry.get("taskId") or "") in filtered_task_ids
                    or str(entry.get("runId") or "") in filtered_run_ids
                )
            ][:6]

        recent_artifacts: list[dict[str, Any]] = []
        seen_artifact_ids: set[str] = set()
        for task in sorted_tasks[:12]:
            run_id = str(task.get("currentRunId") or task.get("id") or "").strip()
            if not run_id:
                continue
            session_context = _build_run_session_context(project_root, run_id)
            artifacts = session_context.get("artifacts") if isinstance(session_context, dict) else []
            if not isinstance(artifacts, list):
                continue
            for artifact in sorted(
                [item for item in artifacts if isinstance(item, dict)],
                key=lambda item: str(item.get("t") or ""),
                reverse=True,
            ):
                artifact_id = str(artifact.get("artifactId") or "").strip() or f"{run_id}:{artifact.get('title') or artifact.get('location') or artifact.get('path') or 'artifact'}"
                if artifact_id in seen_artifact_ids:
                    continue
                seen_artifact_ids.add(artifact_id)
                recent_artifacts.append({
                    "id": artifact_id,
                    "artifactId": artifact_id,
                    "taskId": str(task.get("id") or ""),
                    "runId": run_id,
                    "title": str(artifact.get("title") or ""),
                    "kind": str(artifact.get("kind") or ""),
                    "location": artifact.get("location"),
                    "path": artifact.get("path"),
                    "producer": str(artifact.get("producer") or ""),
                    "mode": task.get("mode"),
                    "modeSubtype": task.get("modeSubtype"),
                    "t": artifact.get("t"),
                })
                if len(recent_artifacts) >= 6:
                    break
            if len(recent_artifacts) >= 6:
                break

        alerts: list[dict[str, Any]] = []
        if running:
            task = sorted(running, key=lambda t: t.get("startedAt") or "", reverse=True)[0]
            alerts.append({
                "id": f"running-{task['id']}",
                "level": "warn",
                "message": f"{task['id']} is still running",
                "t": task.get("startedAt") or _now_iso(),
            })
        if total_tokens > 0:
            alerts.append({
                "id": "daily-token-usage",
                "level": "info",
                "message": f"daily token usage {total_tokens}",
                "t": _now_iso(),
            })
        kb_dir = project_root / "knowledge"
        if kb_dir.exists():
            latest_doc = max(
                (p for p in kb_dir.rglob("*.md")),
                key=lambda p: p.stat().st_mtime,
                default=None,
            )
            if latest_doc is not None:
                alerts.append({
                    "id": "knowledge-index-status",
                    "level": "info",
                    "message": f"knowledge doc updated: {latest_doc.name}",
                    "t": datetime.fromtimestamp(latest_doc.stat().st_mtime, timezone.utc).isoformat(),
                })

        return web.json_response({
            "kpis": {
                "running": len(running),
                "queued": len(queued),
                "tasksToday": len(all_tasks),
                "successToday": len(succeeded),
                "failedToday": len(failed),
                "stoppedToday": len(stopped),
                "dailyTokens": total_tokens,
                "estimatedCost": estimated_cost,
                "successRate": len(succeeded) / max(len(all_tasks), 1),
                "toolCalls": sum(t.get("toolCalls", 0) for t in all_tasks),
                "knowledgeHits": series["totalKnowledgeHits"],
            },
            "tokenSeries": series["tokenSeries"],
            "toolDistribution": series["toolDistribution"],
            "failureDistribution": series["failureDistribution"],
            "knowledgeHitTrend": series["knowledgeHitTrend"],
            "flags": flags,
            "recentTasks": recent_tasks,
            "recentToolCalls": recent_tool_calls,
            "recentArtifacts": recent_artifacts,
            "alerts": alerts[:6],
        })

    async def get_traces(req: web.Request) -> web.Response:
        window_filter = str(req.rel_url.query.get("window") or "24h").lower()
        if window_filter not in {"24h", "all"}:
            window_filter = "24h"
        target_filter = str(req.rel_url.query.get("target") or "all").strip()

        now_dt = datetime.now(timezone.utc)
        window_tasks: list[dict[str, Any]] = []
        for task in _tasks.values():
            if window_filter == "24h":
                task_time = _parse_iso(task.get("startedAt")) or _parse_iso(task.get("createdAt"))
                if not task_time or (now_dt - task_time) > timedelta(hours=24):
                    continue
            window_tasks.append(task)

        available_targets = sorted(
            {
                str(task.get("target") or "").strip()
                for task in window_tasks
                if str(task.get("target") or "").strip()
            }
        )
        target_options = ["all", *available_targets]
        if target_filter not in target_options:
            target_filter = "all"

        filtered_tasks = [
            task
            for task in window_tasks
            if target_filter == "all" or str(task.get("target") or "").strip() == target_filter
        ]

        filtered_tasks.sort(key=lambda t: t.get("createdAt") or t.get("startedAt") or "", reverse=True)
        traces = [_build_trace_payload(project_root, t, include_timeline=False) for t in filtered_tasks]
        return web.json_response({
            "items": traces,
            "filters": {
                "window": window_filter,
                "target": target_filter,
                "targets": target_options,
            },
        })

    async def get_trace(req: web.Request) -> web.Response:
        run_id = req.match_info["runId"]
        task = next((t for t in _tasks.values() if t.get("currentRunId", t.get("id")) == run_id), None)
        if not task:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response(_build_trace_payload(project_root, task, include_timeline=True))

    async def _collect_log_entries() -> list[dict[str, Any]]:
        import re

        log_dir = project_root / "logs"
        entries = []
        if log_dir.exists():
            for f in sorted(log_dir.glob("*.log"), reverse=True)[:2]:
                if f.name.startswith("web_console_") or f.name in {"web_console_stdout.log", "web_console_stderr.log"}:
                    continue
                try:
                    for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]):
                        if line.strip():
                            run_match = re.search(r"\b(run_[A-Za-z0-9_-]+)\b", line)
                            task_match = re.search(r"\b(task_[A-Za-z0-9_-]+)\b", line)
                            message = line[:300]
                            entries.append({
                                "id": f"{f.name}:{i}",
                                "t": _now_iso(),
                                "level": "info",
                                "source": f.stem,
                                "msg": message,
                                "message": message,
                                "runId": run_match.group(1) if run_match else "—",
                                "taskId": task_match.group(1) if task_match else "—",
                            })
                except Exception:
                    pass
        return entries

    async def get_logs(req: web.Request) -> web.Response:
        entries = await _collect_log_entries()
        return web.json_response(entries)

    async def get_knowledge(req: web.Request) -> web.Response:
        kb_dir = project_root / "knowledge"
        docs = []
        if kb_dir.exists():
            for f in kb_dir.rglob("*.md"):
                doc = _build_knowledge_doc(project_root, f, include_content=False)
                usage = _build_knowledge_usage(project_root, f)
                doc["hitCount"] = usage["hitCount"]
                doc["lastHitAt"] = usage["lastHitAt"]
                docs.append(doc)
        return web.json_response(docs)

    async def post_knowledge_reindex(req: web.Request) -> web.Response:
        from ..knowledge import RAGEngine

        knowledge_path = project_root / "knowledge"
        knowledge_path.mkdir(parents=True, exist_ok=True)
        rag = RAGEngine(knowledge_path=knowledge_path, use_local_embeddings=True)
        rag.index_documents(force=True)
        documents = list(getattr(rag, "documents", []) or [])
        doc_count = len({str(getattr(doc, "source", "")) for doc in documents if getattr(doc, "source", "")})
        chunk_count = len(documents)
        return web.json_response({
            "ok": True,
            "reindexed": True,
            "docCount": doc_count,
            "chunkCount": chunk_count,
            "updatedAt": _now_iso(),
        })

    async def get_knowledge_doc(req: web.Request) -> web.Response:
        doc_key = req.match_info["docKey"]
        source_path = _decode_doc_key(doc_key)
        if not source_path:
            return web.json_response({"error": "not found"}, status=404)
        path = (project_root / source_path).resolve()
        kb_root = (project_root / "knowledge").resolve()
        if not path.exists() or kb_root not in path.parents:
            return web.json_response({"error": "not found"}, status=404)
        doc = _build_knowledge_doc(project_root, path, include_content=True)
        usage = _build_knowledge_usage(project_root, path)
        doc.update(usage)
        return web.json_response(doc)

    async def open_knowledge_doc(req: web.Request) -> web.Response:
        doc_key = req.match_info["docKey"]
        source_path = _decode_doc_key(doc_key)
        if not source_path:
            return web.json_response({"error": "not found"}, status=404)
        path = (project_root / source_path).resolve()
        kb_root = (project_root / "knowledge").resolve()
        if not path.exists() or kb_root not in path.parents:
            return web.json_response({"error": "not found"}, status=404)
        if path.suffix.lower() not in {".md", ".txt", ".json"}:
            return web.json_response({"error": "unsupported file type"}, status=400)
        return web.json_response({
            "ok": True,
            "openUrl": f"/api/knowledge/{doc_key}/content",
            "sourcePath": str(path.relative_to(project_root)).replace("\\", "/"),
        })

    async def get_knowledge_doc_content(req: web.Request) -> web.Response:
        doc_key = req.match_info["docKey"]
        source_path = _decode_doc_key(doc_key)
        if not source_path:
            return web.json_response({"error": "not found"}, status=404)
        path = (project_root / source_path).resolve()
        kb_root = (project_root / "knowledge").resolve()
        if not path.exists() or kb_root not in path.parents:
            return web.json_response({"error": "not found"}, status=404)
        content_types = {
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".json": "application/json",
        }
        suffix = path.suffix.lower()
        if suffix not in content_types:
            return web.json_response({"error": "unsupported file type"}, status=400)
        return web.Response(body=path.read_bytes(), content_type=content_types[suffix])

    async def post_knowledge_document(req: web.Request) -> web.Response:
        from ..knowledge import RAGEngine

        knowledge_dir = project_root / "knowledge" / "sources"
        knowledge_dir.mkdir(parents=True, exist_ok=True)

        allowed_suffixes = {".md", ".txt", ".json"}
        saved_path: Path | None = None

        try:
            reader = await req.multipart()
            async for part in reader:
                if part.name != "file":
                    continue

                filename = Path(part.filename or "document.md").name or "document.md"
                suffix = Path(filename).suffix.lower()
                if suffix not in allowed_suffixes:
                    return web.json_response({"ok": False, "error": "unsupported file type"}, status=400)

                dest = knowledge_dir / filename
                stem, final_suffix = dest.stem, dest.suffix
                counter = 1
                while dest.exists():
                    dest = knowledge_dir / f"{stem}_{counter}{final_suffix}"
                    counter += 1

                with dest.open("wb") as fh:
                    while True:
                        chunk = await part.read_chunk(65536)
                        if not chunk:
                            break
                        fh.write(chunk)

                saved_path = dest
                break
        except Exception as exc:
            logger.exception("post_knowledge_document error: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

        if saved_path is None:
            return web.json_response({"ok": False, "error": "file required"}, status=400)

        rag = RAGEngine(knowledge_path=project_root / "knowledge", use_local_embeddings=True)
        rag.index_documents(force=True)
        documents = list(getattr(rag, "documents", []) or [])
        doc_count = len({str(getattr(doc, "source", "")) for doc in documents if getattr(doc, "source", "")})
        chunk_count = len(documents)

        document = _build_knowledge_doc(project_root, saved_path, include_content=False)
        document["chunkCount"] = sum(1 for doc in documents if str(getattr(doc, "source", "")) == str(saved_path))

        return web.json_response({
            "ok": True,
            "saved": True,
            "document": document,
            "reindexed": True,
            "docCount": doc_count,
            "chunkCount": chunk_count,
            "updatedAt": _now_iso(),
        })

    # ── Attachment upload ─────────────────────────────────────────────────────

    async def post_attachments(req: web.Request) -> web.Response:
        """POST /api/tasks/{taskId}/attachments  — multipart/form-data
        Saves uploaded files to loot/uploads/{taskId}/ and returns metadata.
        """
        task_id = req.match_info.get("taskId", "").strip()
        if not task_id:
            return web.Response(status=400, text="taskId required")

        upload_dir = project_root / "loot" / "uploads" / task_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        saved: list[dict] = []
        try:
            reader = await req.multipart()
            async for part in reader:
                if part.name != "files":
                    continue
                filename = part.filename or f"file_{len(saved)}"
                # Sanitise filename: strip path separators
                filename = Path(filename).name or f"file_{len(saved)}"
                dest = upload_dir / filename
                # Avoid overwrite: append suffix if exists
                stem, suffix = dest.stem, dest.suffix
                counter = 1
                while dest.exists():
                    dest = upload_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

                size = 0
                with dest.open("wb") as fh:
                    while True:
                        chunk = await part.read_chunk(65536)
                        if not chunk:
                            break
                        fh.write(chunk)
                        size += len(chunk)

                saved.append({
                    "name": filename,
                    "saved_as": dest.name,
                    "size": size,
                    "path": str(dest.relative_to(project_root)),
                })
                logger.info("Attachment saved: %s (%d bytes) for task %s", dest, size, task_id)

        except Exception as exc:
            logger.exception("post_attachments error for task %s: %s", task_id, exc)
            return web.Response(status=500, text=str(exc))

        return web.json_response({"taskId": task_id, "files": saved})

    async def get_attachments(req: web.Request) -> web.Response:
        """GET /api/tasks/{taskId}/attachments — list uploaded files for a task."""
        task_id = req.match_info.get("taskId", "").strip()
        upload_dir = project_root / "loot" / "uploads" / task_id
        if not upload_dir.exists():
            return web.json_response({"taskId": task_id, "files": []})
        files = []
        for p in sorted(upload_dir.iterdir()):
            if p.is_file():
                files.append({
                    "name": p.name,
                    "saved_as": p.name,
                    "size": p.stat().st_size,
                    "path": str(p.relative_to(project_root)),
                })
        return web.json_response({"taskId": task_id, "files": files})

    # ── Memory API ────────────────────────────────────────────────────────────

    def _get_mem_store():
        try:
            from flaghunter.agents.pa_agent.strategy_memory import StrategyMemoryStore
            return StrategyMemoryStore(project_root / "loot" / "strategy_memory.json")
        except Exception:
            return None

    async def get_memory(req: web.Request) -> web.Response:
        store = _get_mem_store()
        if store is None:
            return web.json_response([])
        params = req.rel_url.query
        status_filter = params.get("status") or None
        sort_by = params.get("sort_by", "recent")
        limit = int(params.get("limit", "200"))
        try:
            entries = await store.list_entries(
                limit=limit,
                manual_status=status_filter,
                sort_by=sort_by,
            )
            return web.json_response([e.to_dict() for e in entries])
        except Exception as exc:
            logger.exception("get_memory error: %s", exc)
            return web.json_response([])

    async def get_memory_stats(req: web.Request) -> web.Response:
        store = _get_mem_store()
        if store is None:
            return web.json_response({"total": 0, "active": 0, "muted": 0, "deprecated": 0, "audit_candidates": 0})
        try:
            all_entries = await store.list_entries(limit=10000)
            total = len(all_entries)
            active = sum(1 for e in all_entries if e.metadata.manual_status == "active")
            muted = sum(1 for e in all_entries if e.metadata.manual_status == "muted")
            deprecated = sum(1 for e in all_entries if e.metadata.manual_status == "deprecated")
            audit_candidates = sum(
                1 for e in all_entries
                if e.metadata.manual_status == "active"
                and e.metadata.applied_count >= 3
                and e.metadata.success_correlation < 0.3
            )
            return web.json_response({
                "total": total,
                "active": active,
                "muted": muted,
                "deprecated": deprecated,
                "audit_candidates": audit_candidates,
            })
        except Exception as exc:
            logger.exception("get_memory_stats error: %s", exc)
            return web.json_response({"total": 0, "active": 0, "muted": 0, "deprecated": 0, "audit_candidates": 0})

    async def get_memory_entry(req: web.Request) -> web.Response:
        entry_id = req.match_info.get("entryId", "")
        store = _get_mem_store()
        if store is None:
            return web.json_response(None)
        try:
            entry = await store.get_entry(entry_id)
            if entry is None:
                return web.Response(status=404, text="Not found")
            return web.json_response(entry.to_dict())
        except Exception as exc:
            logger.exception("get_memory_entry error: %s", exc)
            return web.Response(status=500, text=str(exc))

    async def mute_memory_entry(req: web.Request) -> web.Response:
        entry_id = req.match_info.get("entryId", "")
        store = _get_mem_store()
        if store is None:
            return web.json_response({"ok": False})
        try:
            entry = await store.mute_entry(entry_id)
            if entry is None:
                return web.Response(status=404, text="Not found")
            return web.json_response(entry.to_dict())
        except Exception as exc:
            logger.exception("mute_memory_entry error: %s", exc)
            return web.Response(status=500, text=str(exc))

    async def activate_memory_entry(req: web.Request) -> web.Response:
        entry_id = req.match_info.get("entryId", "")
        store = _get_mem_store()
        if store is None:
            return web.json_response({"ok": False})
        try:
            entry = await store.activate_entry(entry_id)
            if entry is None:
                return web.Response(status=404, text="Not found")
            return web.json_response(entry.to_dict())
        except Exception as exc:
            logger.exception("activate_memory_entry error: %s", exc)
            return web.Response(status=500, text=str(exc))

    async def delete_memory_entry(req: web.Request) -> web.Response:
        entry_id = req.match_info.get("entryId", "")
        store = _get_mem_store()
        if store is None:
            return web.json_response({"ok": False})
        try:
            ok = await store.delete_entry(entry_id)
            if not ok:
                return web.Response(status=404, text="Not found")
            return web.json_response({"ok": True, "id": entry_id})
        except Exception as exc:
            logger.exception("delete_memory_entry error: %s", exc)
            return web.Response(status=500, text=str(exc))

    async def get_memory_graph(req: web.Request) -> web.Response:
        """Return nodes+edges for force-directed graph visualization."""
        store = _get_mem_store()
        if store is None:
            return web.json_response({"nodes": [], "edges": []})
        params = req.rel_url.query
        status_filter = params.get("status") or None
        try:
            entries = await store.list_entries(limit=2000, manual_status=status_filter)
        except Exception:
            return web.json_response({"nodes": [], "edges": []})

        TYPE_COLORS: dict[str, str] = {
            "web": "#4fc3f7", "crypto": "#ffb74d", "reverse": "#4db6ac",
            "pwn": "#ef5350", "misc": "#ce93d8", "forensics": "#f06292",
        }

        nodes: list[dict] = []
        node_ids: set[str] = set()
        for e in entries:
            ntype = (e.fingerprint.detected_type or "misc").lower()
            nodes.append({
                "id": e.id,
                "type": ntype,
                "color": TYPE_COLORS.get(ntype, "#90a4ae"),
                "appliedCount": e.metadata.applied_count,
                "successCorrelation": e.metadata.success_correlation,
                "status": e.metadata.manual_status,
                "solved": e.solved,
                "techStack": e.fingerprint.tech_stack,
            })
            node_ids.add(e.id)

        # Build edges: group nodes by detected_type, then connect pairs
        # within each group that share hypothesis kinds. Cap edges per node
        # to keep the graph readable and the response size manageable.
        nodes_by_type: dict[str, list[int]] = {}
        for idx, e in enumerate(entries):
            ntype = (e.fingerprint.detected_type or "misc").lower()
            nodes_by_type.setdefault(ntype, []).append(idx)

        edges: list[dict] = []
        edge_seen: set[tuple] = set()
        edge_count_per_node: dict[str, int] = {}
        MAX_EDGES_PER_NODE = 12

        for indices in nodes_by_type.values():
            for i_idx, i in enumerate(indices):
                a = entries[i]
                a_kinds = set(a.winning_hypothesis_kinds or [])
                if not a_kinds:
                    continue
                for j in indices[i_idx + 1:]:
                    if edge_count_per_node.get(a.id, 0) >= MAX_EDGES_PER_NODE:
                        break
                    b = entries[j]
                    b_kinds = set(b.winning_hypothesis_kinds or [])
                    if not b_kinds:
                        continue
                    if edge_count_per_node.get(b.id, 0) >= MAX_EDGES_PER_NODE:
                        continue
                    key = tuple(sorted([a.id, b.id]))
                    if key in edge_seen:
                        continue
                    shared_kinds = a_kinds & b_kinds
                    if not shared_kinds:
                        continue
                    edges.append({
                        "source": a.id, "target": b.id,
                        "kind": "hypothesis", "weight": len(shared_kinds),
                    })
                    edge_seen.add(key)
                    edge_count_per_node[a.id] = edge_count_per_node.get(a.id, 0) + 1
                    edge_count_per_node[b.id] = edge_count_per_node.get(b.id, 0) + 1

        return web.json_response({"nodes": nodes, "edges": edges})

    async def sse_stream(req: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse()
        resp.headers["Content-Type"] = "text/event-stream"
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["Connection"] = "keep-alive"
        resp.headers["Access-Control-Allow-Origin"] = "*"
        await resp.prepare(req)

        q = _bus.subscribe()
        try:
            # Send initial ping
            await resp.write(b"data: {\"type\":\"ping\"}\n\n")
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20.0)
                    data = json.dumps(event, ensure_ascii=False)
                    await resp.write(f"data: {data}\n\n".encode())
                except asyncio.TimeoutError:
                    await resp.write(b"data: {\"type\":\"heartbeat\"}\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            _bus.unsubscribe(q)
        return resp

    return {
        "get_status": get_status,
        "get_settings": get_settings_handler,
        "put_settings": put_settings_handler,
        "post_mcp_server": post_mcp_server,
        "post_runtime_test": post_runtime_test,
        "get_tasks": get_tasks,
        "post_task": post_task,
        "get_task": get_task,
        "stop_task": stop_task,
        "retry_task": retry_task,
        "continue_task": continue_task,
        "post_hint": post_hint,
        "get_dashboard": get_dashboard,
        "get_traces": get_traces,
        "get_trace": get_trace,
        "replay_trace": replay_trace,
        "get_logs": get_logs,
        "get_knowledge": get_knowledge,
        "post_knowledge_reindex": post_knowledge_reindex,
        "get_knowledge_doc": get_knowledge_doc,
        "open_knowledge_doc": open_knowledge_doc,
        "get_knowledge_doc_content": get_knowledge_doc_content,
        "post_knowledge_document": post_knowledge_document,
        "post_attachments": post_attachments,
        "get_attachments": get_attachments,
        "get_memory": get_memory,
        "get_memory_stats": get_memory_stats,
        "get_memory_entry": get_memory_entry,
        "mute_memory_entry": mute_memory_entry,
        "activate_memory_entry": activate_memory_entry,
        "delete_memory_entry": delete_memory_entry,
        "get_memory_graph": get_memory_graph,
        "sse_stream": sse_stream,
    }


# ── CORS middleware ───────────────────────────────────────────────────────────

@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        return web.Response(headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        })
    resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


# ── App factory ───────────────────────────────────────────────────────────────

def create_app(project_root: Path) -> web.Application:
    _load_tasks(project_root)
    _seed_aggregator_from_metrics(project_root)

    h = _make_handlers(project_root)
    app = web.Application(middlewares=[cors_middleware])

    # API routes
    app.router.add_get("/api/status", h["get_status"])
    app.router.add_get("/api/settings", h["get_settings"])
    app.router.add_put("/api/settings", h["put_settings"])
    app.router.add_post("/api/settings/mcp/servers", h["post_mcp_server"])
    app.router.add_post("/api/runtime/test", h["post_runtime_test"])
    app.router.add_get("/api/tasks", h["get_tasks"])
    app.router.add_post("/api/tasks", h["post_task"])
    app.router.add_get("/api/tasks/{taskId}", h["get_task"])
    app.router.add_post("/api/tasks/{taskId}/stop", h["stop_task"])
    app.router.add_post("/api/tasks/{taskId}/retry", h["retry_task"])
    app.router.add_post("/api/tasks/{taskId}/continue", h["continue_task"])
    app.router.add_post("/api/tasks/{taskId}/hint", h["post_hint"])
    app.router.add_get("/api/dashboard/summary", h["get_dashboard"])
    app.router.add_get("/api/traces", h["get_traces"])
    app.router.add_get("/api/traces/{runId}", h["get_trace"])
    app.router.add_post("/api/traces/{runId}/replay", h["replay_trace"])
    app.router.add_get("/api/logs", h["get_logs"])
    app.router.add_get("/api/knowledge", h["get_knowledge"])
    app.router.add_post("/api/knowledge/reindex", h["post_knowledge_reindex"])
    app.router.add_get("/api/knowledge/{docKey}/open", h["open_knowledge_doc"])
    app.router.add_get("/api/knowledge/{docKey}/content", h["get_knowledge_doc_content"])
    app.router.add_post("/api/knowledge/documents", h["post_knowledge_document"])
    app.router.add_get("/api/knowledge/{docKey}", h["get_knowledge_doc"])
    app.router.add_get("/api/tasks/{taskId}/attachments", h["get_attachments"])
    app.router.add_post("/api/tasks/{taskId}/attachments", h["post_attachments"])
    app.router.add_get("/api/memory", h["get_memory"])
    app.router.add_get("/api/memory/stats", h["get_memory_stats"])
    app.router.add_get("/api/memory/graph", h["get_memory_graph"])
    app.router.add_get("/api/memory/{entryId}", h["get_memory_entry"])
    app.router.add_post("/api/memory/{entryId}/mute", h["mute_memory_entry"])
    app.router.add_post("/api/memory/{entryId}/activate", h["activate_memory_entry"])
    app.router.add_delete("/api/memory/{entryId}", h["delete_memory_entry"])
    app.router.add_get("/api/events/stream", h["sse_stream"])

    # Static files — serve web/console/
    console_dir = project_root / "web" / "console"
    if console_dir.exists():
        app.router.add_static("/src", console_dir / "src", name="static_src")
        # Serve index.html for root and unknown paths
        async def index(_req):
            return web.FileResponse(console_dir / "index.html")
        app.router.add_get("/", index)
        app.router.add_get("/{tail:.*}", index)

    return app


def run_web_server(host: str = "127.0.0.1", port: int = 8080, project_root: Path | None = None) -> None:
    """Entry point called by the CLI command."""
    if project_root is None:
        project_root = Path(__file__).resolve().parents[2]

    app = create_app(project_root)
    logger.info(
        "web_console_bind host=%s port=%s url=http://%s:%s/ project_root=%s",
        host,
        port,
        host,
        port,
        project_root,
    )
    print(f"\n  FlagHunter Mission Control")
    print(f"  http://{host}:{port}/\n")
    web.run_app(app, host=host, port=port, print=None)
