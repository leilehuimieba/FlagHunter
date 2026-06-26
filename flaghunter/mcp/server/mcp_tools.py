from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, Type

from ...interface.blackboard_lite import (
    build_entry_blackboard_snapshot,
    format_blackboard_snapshot_lines,
    normalize_blackboard_snapshot,
)
from ...interface.control_contract import (
    build_control_decision_parts,
    build_decision_record,
    resolve_control_decision,
    strongest_hypothesis_contract,
)
from ...interface.mode_router import resolve_mode_contract
from ...session.event_bus import EventBus
from .mcp_core import ToolRegistry

if TYPE_CHECKING:
    from flaghunter.agents.pa_agent import FlagHunterAgent
    from flaghunter.llm import LLM
    from flaghunter.runtime.runtime import Runtime

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_primary_agent: Optional[FlagHunterAgent] = None
_LLMClass: Optional[Type[LLM]] = None
_RuntimeClass: Optional[Type[Runtime]] = None
_llm_kwargs: dict[str, Any] = {}
_runtime_kwargs: dict[str, Any] = {}

# MCP server events flow through one neutral EventBus (architecture invariant
# I3 — single event source). _emit() publishes; the optional UI hook (the TUI
# in MCP observation mode) is just a subscriber, registered via set_ui_hook.
_event_bus = EventBus()
_ui_hook: Optional[Callable[[str, dict], None]] = None
_ui_hook_unsub: Optional[Callable[[], None]] = None


def get_event_bus() -> EventBus:
    """Return the module-level neutral event bus (for observers/tests)."""
    return _event_bus


def set_ui_hook(hook: Optional[Callable[[str, dict], None]]) -> None:
    """Register (or clear) the UI event hook by (un)subscribing it on the
    neutral event bus.  Single-hook semantics preserved; thread-safe write."""
    global _ui_hook, _ui_hook_unsub
    if _ui_hook_unsub is not None:
        _ui_hook_unsub()
        _ui_hook_unsub = None
    _ui_hook = hook
    if hook is not None:
        _ui_hook_unsub = _event_bus.subscribe(lambda ev: hook(ev.type, ev.data))


def _emit(event: str, data: dict) -> None:
    """Publish a UI event onto the neutral bus (subscriber errors isolated)."""
    _event_bus.emit(event, data, source="mcp")


_tasks: dict[str, TaskEntry] = {}
_memory: dict[str, dict[str, str]] = {}
_logs: list[dict[str, str]] = []
_LOG_MAX = 500

# Outgoing JSON-RPC notification queue.
# _drive_task() puts a "notifications/task_completed" message here when an
# async task finishes.  The FIFO transport (run_stdio_fifo) drains this queue
# concurrently and forwards every message to the parent agent.
_outgoing_queue: asyncio.Queue = asyncio.Queue()


def get_outgoing_queue() -> asyncio.Queue:
    """Return the module-level outgoing notification queue."""
    return _outgoing_queue


def _read_local_env() -> dict[str, str]:
    env_path = Path(".env")
    result: dict[str, str] = {}
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def _current_model_readiness() -> dict[str, Any]:
    from ...config.settings import (
        get_settings,
        resolve_model_provider,
        resolve_model_readiness,
    )

    env = _read_local_env()
    settings = get_settings()
    api_base = env.get(
        "LITELLM_API_BASE",
        env.get("OPENAI_API_BASE", os.getenv("LITELLM_API_BASE") or os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL") or ""),
    )
    anthropic_api_key = env.get("ANTHROPIC_API_KEY") or settings.anthropic_api_key
    openai_api_key = env.get("OPENAI_API_KEY") or settings.openai_api_key
    provider = resolve_model_provider(
        explicit_provider=env.get("FH_PROVIDER", os.getenv("FH_PROVIDER", "")),
        api_base=api_base,
        openai_api_key=openai_api_key,
        anthropic_api_key=anthropic_api_key,
    )
    active_api_key = anthropic_api_key if provider == "anthropic" else openai_api_key
    return resolve_model_readiness(
        provider=provider,
        model=env.get("FLAGHUNTER_MODEL") or settings.model or "",
        api_base=api_base,
        api_key=active_api_key,
    )


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def bootstrap(
    primary_agent: "FlagHunterAgent",
    llm_class: Type["LLM"],
    runtime_class: Type["Runtime"],
    llm_kwargs: Optional[dict[str, Any]] = None,
    runtime_kwargs: Optional[dict[str, Any]] = None,
) -> None:
    """
    Called once from server.py after _initialize() has built every component.
    The primary_agent is used ONLY as a configuration source — never to execute tasks.
    """
    global _primary_agent, _LLMClass, _RuntimeClass, _llm_kwargs, _runtime_kwargs
    _primary_agent = primary_agent
    _LLMClass = llm_class
    _RuntimeClass = runtime_class
    _llm_kwargs = llm_kwargs or {}
    _runtime_kwargs = runtime_kwargs or {}
    _log("info", "mcp_tools bootstrapped.")


# ---------------------------------------------------------------------------
# TaskEntry
# ---------------------------------------------------------------------------


@dataclass
class TaskEntry:
    id: str
    task: str
    status: str  # pending | running | done | error | cancelled
    created_at: str
    agent: "FlagHunterAgent"
    target: Optional[str] = None
    scope: list[str] = field(default_factory=list)
    finished_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    thinking: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, object]] = field(default_factory=list)
    tool_results: list[dict[str, object]] = field(default_factory=list)
    notes_snapshot: Optional[str] = None
    mode: Optional[str] = None
    modeSubtype: Optional[str] = None
    goalStyle: Optional[str] = None
    challengePath: Optional[str] = None
    artifactPaths: list[str] = field(default_factory=list)
    finalFlag: Optional[str] = None
    ctfChainUsed: list[str] = field(default_factory=list)
    ctfMissingTools: list[str] = field(default_factory=list)
    ctfNotes: list[str] = field(default_factory=list)
    runId: Optional[str] = None
    ledgerPath: Optional[str] = None
    checkpointPath: Optional[str] = None
    resumeFromRunId: Optional[str] = None
    resumeFromCheckpointId: Optional[str] = None
    resumeSummary: Optional[str] = None
    controlDecision: Optional[dict[str, object]] = None
    decisionRecords: list[dict[str, object]] = field(default_factory=list)
    ingressHandoff: Optional[dict[str, object]] = None
    ctfStateSnapshot: Optional[dict[str, object]] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _log(level: str, message: str) -> None:
    _logs.append(
        {"ts": datetime.utcnow().isoformat(), "level": level, "message": message}
    )
    if len(_logs) > _LOG_MAX:
        _logs.pop(0)


async def _make_agent(target: Optional[str], scope: list[str]) -> "FlagHunterAgent":
    """Construct a fresh agent for each task — no shared mutable state between runs."""
    from flaghunter.agents.pa_agent import FlagHunterAgent

    if _LLMClass is None or _RuntimeClass is None:
        raise RuntimeError("bootstrap() must be called before running tasks.")

    runtime = _RuntimeClass(**_runtime_kwargs)
    await runtime.start()

    return FlagHunterAgent(
        llm=_LLMClass(**_llm_kwargs),
        tools=list(_primary_agent.get_tools()) if _primary_agent else [],
        runtime=runtime,
        target=target,
        scope=scope,
        max_iterations=getattr(_primary_agent, "max_iterations", 30),
    )


def _resolve_target_scope(args: dict[str, object]) -> tuple[Optional[str], list[str]]:
    target = (
        str(args["target"])
        if "target" in args
        else getattr(_primary_agent, "target", None)
    )
    scope = list(args["scope"]) if "scope" in args else list(getattr(_primary_agent, "scope", []))  # type: ignore[arg-type]
    return target, scope


def _resolve_ingress_mode_contract(args: dict[str, object]) -> dict[str, str]:
    payload = {
        key: args[key]
        for key in ("task", "target", "mode", "ctfType", "resumeContext", "challengePath", "artifactPaths")
        if key in args
    }
    return resolve_mode_contract(payload)


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _apply_local_asset_contract(entry: TaskEntry, args: dict[str, object]) -> None:
    challenge_path = str(args.get("challengePath") or "").strip()
    entry.challengePath = challenge_path or None
    entry.artifactPaths = _normalize_string_list(args.get("artifactPaths"))


def _apply_resume_contract(entry: TaskEntry, args: dict[str, object]) -> None:
    raw = args.get("resumeContext")
    if not isinstance(raw, dict):
        entry.resumeFromRunId = None
        entry.resumeFromCheckpointId = None
        entry.resumeSummary = None
        return
    entry.resumeFromRunId = str(raw.get("runId") or "").strip() or None
    entry.resumeFromCheckpointId = str(raw.get("checkpointId") or "").strip() or None
    entry.resumeSummary = str(raw.get("summary") or "").strip() or None


def _normalized_blackboard_snapshot(snapshot: dict[str, object] | None) -> dict[str, object]:
    return normalize_blackboard_snapshot(snapshot)  # type: ignore[arg-type]


def _entry_blackboard_snapshot_for_decision(
    entry: TaskEntry,
    explicit_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    if isinstance(explicit_snapshot, dict) and explicit_snapshot:
        return _normalized_blackboard_snapshot(explicit_snapshot)
    return _normalized_blackboard_snapshot(build_entry_blackboard_snapshot(entry))


def _apply_control_decision(
    entry: TaskEntry,
    *,
    blackboard_snapshot: dict[str, object] | None = None,
) -> None:
    entry.controlDecision = resolve_control_decision(
        {
            "mode": entry.mode,
            "target": entry.target,
            "challengePath": entry.challengePath,
            "artifactPaths": list(entry.artifactPaths or []),
            "resumeFromRunId": entry.resumeFromRunId,
            "resumeFromCheckpointId": entry.resumeFromCheckpointId,
            "resumeSummary": entry.resumeSummary,
            "blackboardSnapshot": _entry_blackboard_snapshot_for_decision(
                entry,
                blackboard_snapshot,
            ),
        }
    )
    entry.decisionRecords = [
        build_decision_record(entry.controlDecision, source="mcp_ingress")
    ]


def _build_ingress_handoff(
    entry: TaskEntry,
    *,
    blackboard_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    snapshot = _entry_blackboard_snapshot_for_decision(entry, blackboard_snapshot)
    challenge_context = _entry_challenge_context(entry)
    resume_context = (
        dict(challenge_context.get("resumeContext") or {})
        if isinstance(challenge_context.get("resumeContext"), dict)
        else {}
    )
    decision = entry.controlDecision if isinstance(entry.controlDecision, dict) else {}
    resume_bootstrap: dict[str, object] | None = None
    if str(decision.get("decisionKind") or "").strip() == "resume_execute":
        resume_bootstrap = {
            "nextAction": str(decision.get("nextAction") or "").strip() or "resume_from_checkpoint",
            "runId": str(resume_context.get("runId") or "").strip(),
            "checkpointId": str(resume_context.get("checkpointId") or "").strip(),
            "summary": str(resume_context.get("summary") or "").strip(),
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
    strongest_hypothesis = strongest_hypothesis_contract(decision, snapshot)
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
                for item in list(snapshot.get("facts") or [])
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
                for item in list(snapshot.get("pendingVerifications") or [])
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
                for item in list(snapshot.get("facts") or [])
                if isinstance(item, dict) and str(item.get("kind") or "").strip() == "verified_flag"
            ),
            "",
        )
        if verified_flag:
            handoff["verifiedFlag"] = verified_flag
    return handoff


def _entry_session_context(entry: TaskEntry) -> dict[str, object]:
    run_id = str(getattr(entry, "runId", "") or "").strip()
    if not run_id:
        return {}
    try:
        from ...agents.pa_agent.session_context import build_workspace_run_context

        ledger_path = str(getattr(entry, "ledgerPath", "") or "").strip()
        checkpoint_path = str(getattr(entry, "checkpointPath", "") or "").strip()
        workspace_root = (
            Path(ledger_path).parent.parent.parent
            if ledger_path and len(Path(ledger_path).parts) >= 3
            else Path.cwd()
        )
        if checkpoint_path and len(Path(checkpoint_path).parts) >= 3:
            checkpoint_workspace_root = Path(checkpoint_path).parent.parent.parent
            if checkpoint_workspace_root.exists():
                workspace_root = checkpoint_workspace_root
        context = build_workspace_run_context(
            workspace_root,
            run_id,
            event_limit=20,
            artifact_limit=20,
        )
    except Exception:
        return {}
    return dict(context) if isinstance(context, dict) else {}


def _append_blackboard_snapshot_lines(
    lines: list[str],
    entry: TaskEntry,
    *,
    run_context: dict[str, object] | None = None,
) -> None:
    session_context = run_context if isinstance(run_context, dict) else _entry_session_context(entry)
    snapshot = build_entry_blackboard_snapshot(
        entry,
        session_context=session_context,
    )
    lines.extend(format_blackboard_snapshot_lines(snapshot))


def _append_run_context_lines(lines: list[str], run_context: dict[str, object] | None) -> None:
    if not isinstance(run_context, dict) or not run_context:
        return
    latest_checkpoint = (
        dict(run_context.get("latestCheckpoint") or {})
        if isinstance(run_context.get("latestCheckpoint"), dict)
        else {}
    )
    artifacts = [
        item for item in list(run_context.get("artifacts") or []) if isinstance(item, dict)
    ]
    if latest_checkpoint:
        lines.append("[latest_checkpoint]")
        for key in ("checkpointId", "label", "stopReason"):
            value = str(latest_checkpoint.get(key) or "").strip()
            if value:
                lines.append(f"{key}={value}")
        verified_flags = [
            str(item).strip()
            for item in list(latest_checkpoint.get("verifiedFlags") or [])
            if str(item).strip()
        ]
        if verified_flags:
            lines.append("verifiedFlags=" + ", ".join(verified_flags))
    if artifacts:
        lines.append("[registered_artifacts]")
        for item in artifacts:
            for key in ("artifactId", "kind", "title", "location", "path", "producer"):
                value = str(item.get(key) or "").strip()
                if value:
                    lines.append(f"{key}={value}")


def _append_minimal_decision_record_lines(lines: list[str], records: list[dict[str, object]]) -> None:
    if not records:
        return
    record = records[0] if isinstance(records[0], dict) else {}
    kind = str(record.get("kind") or "").strip()
    source = str(record.get("source") or "").strip()
    next_action = str(record.get("nextAction") or "").strip()
    driver = str(record.get("driver") or "").strip()
    if kind:
        lines.append(f"decision_record_kind: {kind}")
    if source:
        lines.append(f"decision_record_source: {source}")
    if next_action:
        lines.append(f"decision_record_next_action: {next_action}")
        if driver:
            lines.append(f"decision_record_driver: {driver}")


def _build_next_action_explanation(entry: TaskEntry) -> dict[str, str | None]:
    decision = entry.controlDecision if isinstance(entry.controlDecision, dict) else {}
    if not decision:
        return {}
    decision_kind = str(decision.get("decisionKind") or "").strip()
    next_action = str(decision.get("nextAction") or "").strip()
    if not decision_kind and not next_action:
        return {}
    driver = str(decision.get("driver") or "").strip()
    if not driver and next_action == "resume_from_checkpoint":
        driver = "task.resume_context"
    if not driver and next_action == "bootstrap_local_assets":
        driver = "task.local_assets"
    reason = str(decision.get("reason") or "").strip()
    summary_parts: list[str] = []
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
        "summary": " ".join(summary_parts) if summary_parts else None,
    }


def _append_next_action_explanation_lines(lines: list[str], entry: TaskEntry) -> None:
    explanation = _build_next_action_explanation(entry)
    if not explanation:
        return
    decision_kind = str(explanation.get("decisionKind") or "").strip()
    next_action = str(explanation.get("nextAction") or "").strip()
    driver = str(explanation.get("driver") or "").strip()
    reason = str(explanation.get("reason") or "").strip()
    summary = str(explanation.get("summary") or "").strip()
    if decision_kind:
        lines.append(f"next_action_decision_kind: {decision_kind}")
    if next_action:
        lines.append(f"next_action: {next_action}")
    if driver:
        lines.append(f"next_action_driver: {driver}")
    if reason:
        lines.append(f"next_action_reason: {reason}")
    if summary:
        lines.append(f"next_action_summary: {summary}")


def _mark_entry_blocked(entry: TaskEntry, reason: str | None = None) -> None:
    entry.status = "blocked"
    entry.result = None
    if reason:
        entry.error = reason


def _assign_ctf_run_artifacts(entry: TaskEntry) -> None:
    if str(entry.mode or "").strip() != "ctf":
        return
    if not entry.runId:
        entry.runId = f"mcp-ctf-{entry.id}"

    from ...harness.checkpoint_store import CheckpointStore
    from ...harness.session_ledger import SessionLedger

    ledger_path = SessionLedger(Path("loot") / "session_ledgers").path_for_run(entry.runId)
    checkpoint_path = CheckpointStore(Path("loot") / "checkpoints").path_for_run(entry.runId)
    entry.ledgerPath = str(ledger_path).replace("\\", "/")
    entry.checkpointPath = str(checkpoint_path).replace("\\", "/")


def _entry_challenge_context(entry: TaskEntry) -> dict[str, object]:
    context: dict[str, object] = {
        "challengePath": entry.challengePath,
        "artifactPaths": list(entry.artifactPaths or []),
    }
    if entry.resumeFromRunId or entry.resumeFromCheckpointId or entry.resumeSummary:
        context["resumeContext"] = {
            "runId": str(entry.resumeFromRunId or "").strip(),
            "checkpointId": str(entry.resumeFromCheckpointId or "").strip(),
            "summary": str(entry.resumeSummary or "").strip(),
        }
    return context


def _sync_runtime_challenge_context(entry: TaskEntry, dispatcher: object) -> None:
    runtime_context = getattr(dispatcher, "_challenge_context", None)
    if not isinstance(runtime_context, dict):
        return
    handoff = dict(entry.ingressHandoff or {}) if isinstance(entry.ingressHandoff, dict) else {}
    challenge_context = (
        dict(handoff.get("challengeContext") or {})
        if isinstance(handoff.get("challengeContext"), dict)
        else _entry_challenge_context(entry)
    )
    for key in ("challengePath", "derivedTarget", "derivedTargetSource", "derivedTargetComposePath"):
        value = str(runtime_context.get(key) or "").strip()
        if value:
            challenge_context[key] = value
    artifact_paths = _normalize_string_list(runtime_context.get("artifactPaths"))
    if artifact_paths:
        challenge_context["artifactPaths"] = artifact_paths
    handoff["challengeContext"] = challenge_context
    entry.ingressHandoff = handoff
    derived_target = str(challenge_context.get("derivedTarget") or "").strip()
    if derived_target and not str(entry.target or "").strip():
        entry.target = derived_target


def _append_derived_target_context_lines(lines: list[str], challenge_context: object) -> None:
    if not isinstance(challenge_context, dict):
        return
    derived_target = str(challenge_context.get("derivedTarget") or "").strip()
    derived_target_source = str(challenge_context.get("derivedTargetSource") or "").strip()
    derived_target_compose_path = str(challenge_context.get("derivedTargetComposePath") or "").strip()
    if derived_target:
        lines.append(f"derived_target: {derived_target}")
    if derived_target_source:
        lines.append(f"derived_target_source: {derived_target_source}")
    if derived_target_compose_path:
        lines.append(f"derived_target_compose_path: {derived_target_compose_path}")


def _derived_target_origin(entry: TaskEntry, challenge_context: object) -> str:
    if not isinstance(challenge_context, dict):
        return ""
    has_derived_target = bool(
        str(challenge_context.get("derivedTarget") or "").strip()
        or str(challenge_context.get("derivedTargetSource") or "").strip()
        or str(challenge_context.get("derivedTargetComposePath") or "").strip()
    )
    if not has_derived_target:
        return ""
    handoff = entry.ingressHandoff if isinstance(entry.ingressHandoff, dict) else {}
    resume_bootstrap = (
        dict(handoff.get("resumeBootstrap") or {})
        if isinstance(handoff.get("resumeBootstrap"), dict)
        else {}
    )
    resume_context = (
        dict(challenge_context.get("resumeContext") or {})
        if isinstance(challenge_context.get("resumeContext"), dict)
        else {}
    )
    has_lineage = bool(
        str(entry.resumeFromRunId or "").strip()
        or str(entry.resumeFromCheckpointId or "").strip()
        or str(resume_bootstrap.get("runId") or "").strip()
        or str(resume_bootstrap.get("checkpointId") or "").strip()
        or str(resume_context.get("runId") or "").strip()
        or str(resume_context.get("checkpointId") or "").strip()
    )
    return "inherited_lineage" if has_lineage else "runtime_derived"


def _ctf_dispatcher_hint(entry: TaskEntry) -> str:
    base_hint = str(entry.task or "").strip()
    decision = entry.controlDecision if isinstance(entry.controlDecision, dict) else {}
    blackboard_snapshot = build_entry_blackboard_snapshot(entry)
    handoff = entry.ingressHandoff if isinstance(entry.ingressHandoff, dict) else {}
    challenge_context = (
        dict(handoff.get("challengeContext") or {})
        if isinstance(handoff.get("challengeContext"), dict)
        else _entry_challenge_context(entry)
    )
    structured_parts: list[str] = []
    decision_parts = build_control_decision_parts(
        decision, blackboard_snapshot, endpoint_fallback=str(handoff.get("endpoint") or "").strip()
    )
    if decision_parts:
        structured_parts.append("[control_decision]\n" + "\n".join(decision_parts))
    challenge_path = str(challenge_context.get("challengePath") or "").strip()
    artifact_paths = _normalize_string_list(challenge_context.get("artifactPaths"))
    if challenge_path:
        structured_parts.append(f"challengePath={challenge_path}")
    if artifact_paths:
        structured_parts.append("artifactPaths=" + "; ".join(artifact_paths))
    resume_context = (
        dict(challenge_context.get("resumeContext") or {})
        if isinstance(challenge_context.get("resumeContext"), dict)
        else {}
    )
    resume_summary = str(resume_context.get("summary") or "").strip()
    resume_run_id = str(resume_context.get("runId") or "").strip()
    resume_checkpoint_id = str(resume_context.get("checkpointId") or "").strip()
    if resume_summary:
        structured_parts.append("[resume_context]\nsummary=" + resume_summary)
    resume_bootstrap = (
        dict(handoff.get("resumeBootstrap") or {})
        if isinstance(handoff.get("resumeBootstrap"), dict)
        else {}
    )
    resume_bootstrap_run_id = str(resume_bootstrap.get("runId") or resume_run_id or "").strip()
    resume_bootstrap_checkpoint_id = str(resume_bootstrap.get("checkpointId") or resume_checkpoint_id or "").strip()
    resume_bootstrap_summary = str(resume_bootstrap.get("summary") or resume_summary or "").strip()
    resume_bootstrap_action = str(resume_bootstrap.get("nextAction") or "resume_from_checkpoint").strip()
    if resume_bootstrap_run_id or resume_bootstrap_checkpoint_id or resume_bootstrap_summary:
        resume_bootstrap_parts = [f"nextAction={resume_bootstrap_action}"]
        if resume_bootstrap_run_id:
            resume_bootstrap_parts.append(f"runId={resume_bootstrap_run_id}")
        if resume_bootstrap_checkpoint_id:
            resume_bootstrap_parts.append(f"checkpointId={resume_bootstrap_checkpoint_id}")
        if resume_bootstrap_summary:
            resume_bootstrap_parts.append(f"summary={resume_bootstrap_summary}")
        structured_parts.append("[resume_bootstrap]\n" + "\n".join(resume_bootstrap_parts))
    if not structured_parts:
        return base_hint
    structured_hint = "[local_ctf_assets]\n" + "\n".join(structured_parts)
    if base_hint:
        return base_hint + "\n\n" + structured_hint
    return structured_hint


async def _run_ctf_dispatcher_with_handoff(
    dispatcher: object,
    *,
    target: str,
    goal: str,
    ctf_type: str,
    hint: str,
    challenge_context: dict[str, object],
    ingress_handoff: dict[str, object] | None,
    run_id: str | None = None,
) -> object:
    kwargs: dict[str, object] = {
        "target": target,
        "goal": goal,
        "type": ctf_type,
        "hint": hint,
        "challenge_context": challenge_context,
    }
    if run_id is not None:
        kwargs["run_id"] = run_id
    try:
        return await dispatcher.run(**kwargs, ingress_handoff=ingress_handoff)
    except TypeError as exc:
        if "ingress_handoff" not in str(exc):
            raise
        return await dispatcher.run(**kwargs)


async def _capture_notes_snapshot(agent: "FlagHunterAgent") -> Optional[str]:
    try:
        notes_tool = next((t for t in agent.tools if t.name == "notes"), None)
        if notes_tool is None:
            return None
        result = await notes_tool.execute({"action": "list"}, agent.runtime)
        return result if isinstance(result, str) else None
    except Exception as exc:
        _log("warning", f"notes snapshot failed: {exc}")
        return None


async def _drive_task(entry: TaskEntry) -> None:
    """Run the agent loop, recording all output into the TaskEntry."""
    entry.status = "running"
    output_parts: list[str] = []

    _emit(
        "task_start",
        {
            "task_id": entry.id,
            "task": entry.task,
            "target": entry.target,
        },
    )

    try:
        if entry.mode == "ctf":
            from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

            if not isinstance(entry.ingressHandoff, dict):
                _apply_control_decision(entry)
                entry.ingressHandoff = _build_ingress_handoff(entry)
            dispatcher = CTFTaskDispatcher(
                runtime=entry.agent.runtime,
                progress_callback=lambda message: _log("info", f"ctf.dispatcher [{entry.id}]: {message}"),
            )
            solve_result = await _run_ctf_dispatcher_with_handoff(
                dispatcher,
                target=entry.target or "",
                goal=entry.task,
                ctf_type=entry.modeSubtype or "auto",
                hint=_ctf_dispatcher_hint(entry),
                challenge_context=_entry_challenge_context(entry),
                ingress_handoff=(
                    dict(entry.ingressHandoff or {})
                    if isinstance(entry.ingressHandoff, dict)
                    else None
                ),
                run_id=entry.runId,
            )
            entry.finalFlag = getattr(solve_result, "flag", None)
            entry.ctfChainUsed = [
                str(item) for item in (getattr(solve_result, "chain_used", None) or []) if str(item or "").strip()
            ]
            entry.ctfMissingTools = [
                str(item) for item in (getattr(solve_result, "missing_tools", None) or []) if str(item or "").strip()
            ]
            entry.ctfNotes = [
                str(item) for item in (getattr(solve_result, "notes", None) or []) if str(item or "").strip()
            ]
            _sync_runtime_challenge_context(entry, dispatcher)
            dispatcher_state = getattr(dispatcher, "state", None)
            if dispatcher_state is not None and hasattr(dispatcher_state, "to_snapshot"):
                try:
                    entry.ctfStateSnapshot = dispatcher_state.to_snapshot()
                except Exception:
                    pass
            entry.result = str(
                getattr(solve_result, "flag", "")
                or getattr(solve_result, "reason", "")
                or "Done (no text output)."
            )
            entry.status = "done"
            entry.notes_snapshot = await _capture_notes_snapshot(entry.agent)
        else:
            async for response in entry.agent.run_mcp(entry.task):

                if entry.status == "cancelled":
                    entry.agent.cleanup_after_cancel()
                    break

                if response.content and response.tool_calls:
                    entry.thinking.append(response.content.strip())
                    _emit(
                        "thinking",
                        {"content": response.content.strip(), "task_id": entry.id},
                    )
                elif response.content:
                    output_parts.append(response.content.strip())
                    _emit(
                        "content",
                        {"content": response.content.strip(), "task_id": entry.id},
                    )

                for call in response.tool_calls or []:
                    entry.tool_calls.append(
                        {
                            "id": call.id,
                            "name": call.name,
                            "arguments": call.arguments,
                        }
                    )
                    _emit(
                        "tool_call",
                        {
                            "task_id": entry.id,
                            "id": call.id,
                            "name": call.name,
                            "arguments": call.arguments,
                        },
                    )

                for result in response.tool_results or []:
                    entry.tool_results.append(
                        {
                            "tool_call_id": result.tool_call_id,
                            "tool_name": result.tool_name,
                            "success": result.success,
                            "result": result.result if result.success else None,
                            "error": result.error if not result.success else None,
                        }
                    )
                    _emit(
                        "tool_result",
                        {
                            "task_id": entry.id,
                            "tool_call_id": result.tool_call_id,
                            "tool_name": result.tool_name,
                            "success": result.success,
                            "result": result.result if result.success else result.error,
                        },
                    )

            if entry.status != "cancelled":
                entry.result = "\n".join(output_parts) or "Done (no text output)."
                entry.status = "done"
                entry.notes_snapshot = await _capture_notes_snapshot(entry.agent)

    except asyncio.CancelledError:
        entry.status = "cancelled"
        entry.agent.cleanup_after_cancel()
        _log("info", f"Task {entry.id} cancelled.")

    except Exception as exc:
        entry.status = "error"
        entry.error = str(exc)
        _log("error", f"Task {entry.id} error: {exc}")

    finally:
        entry.finished_at = datetime.utcnow().isoformat()
        _log("info", f"Task {entry.id} finished — status={entry.status}")
        _emit(
            "task_done",
            {
                "task_id": entry.id,
                "status": entry.status,
                "result": entry.result,
                "error": entry.error,
            },
        )
        try:
            _outgoing_queue.put_nowait(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/task_completed",
                    "params": {
                        "task_id": entry.id,
                        "status": entry.status,
                        "task": entry.task[:120],
                    },
                }
            )
        except Exception:
            pass


def _create_task(
    task: str, agent: "FlagHunterAgent", target: Optional[str], scope: list[str]
) -> TaskEntry:
    entry = TaskEntry(
        id=str(uuid.uuid4())[:8],
        task=task,
        status="pending",
        created_at=datetime.utcnow().isoformat(),
        agent=agent,
        target=target,
        scope=scope,
    )
    _tasks[entry.id] = entry
    return entry


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------

mcp_tool_registry = ToolRegistry()


# ===========================================================================
# GROUP: SERVER STATUS & CONFIG
# ===========================================================================


@mcp_tool_registry.register(
    name="get_server_status",
    description=(
        "Return the live status of the MCP server: readiness, task counts by state, "
        "primary target/scope, and memory store size."
    ),
    schema={"type": "object", "properties": {}, "required": []},
)
async def get_server_status(args: dict[str, object]) -> str:
    by_status = {s: [] for s in ("pending", "running", "done", "error", "cancelled")}
    for e in _tasks.values():
        by_status.get(e.status, []).append(e.id)
    model_readiness = _current_model_readiness()

    lines: list[str] = [
        f"ready:      {_primary_agent is not None}",
        f"model_ready: {model_readiness['ready']}",
        f"model_readiness_reason: {model_readiness['reason']}",
        f"active:     {len(by_status['pending']) + len(by_status['running'])}",
        f"done:       {len(by_status['done'])}",
        f"error:      {len(by_status['error'])}",
        f"cancelled:  {len(by_status['cancelled'])}",
        f"memory_keys:{len(_memory)}",
    ]
    if _primary_agent:
        lines += [
            f"primary_target: {getattr(_primary_agent, 'target', 'none')}",
            f"primary_scope:  {getattr(_primary_agent, 'scope', [])}",
            f"max_iterations: {_primary_agent.max_iterations}",
        ]
    active_ids = by_status["pending"] + by_status["running"]
    if active_ids:
        lines.append("active_ids: " + ", ".join(active_ids))
    return "\n".join(lines)


@mcp_tool_registry.register(
    name="get_config",
    description="Return the primary agent configuration: target, scope, max_iterations, and tool list.",
    schema={"type": "object", "properties": {}, "required": []},
)
async def get_config(args: dict[str, object]) -> str:
    if not _primary_agent:
        return "[error] Primary agent not initialised."
    tools = [t.name for t in _primary_agent.get_tools()]
    _llm = getattr(_primary_agent, "llm", None)
    active_model = getattr(_llm, "model", None) if _llm is not None else None
    return "\n".join(
        [
            f"target:         {getattr(_primary_agent, 'target', 'none')}",
            f"scope:          {getattr(_primary_agent, 'scope', [])}",
            f"max_iterations: {_primary_agent.max_iterations}",
            f"model:          {active_model or 'none'}",
            f"tools ({len(tools)}): {', '.join(tools)}",
        ]
    )


@mcp_tool_registry.register(
    name="update_config",
    description="Update the primary agent configuration. Changes apply to all subsequent tasks.",
    schema={
        "type": "object",
        "properties": {
            "target": {"type": "string"},
            "scope": {"type": "array", "items": {"type": "string"}},
            "max_iterations": {"type": "integer"},
            "model": {"type": "string"},
        },
        "required": [],
    },
)
async def update_config(args: dict[str, object]) -> str:
    if not _primary_agent:
        return "[error] Primary agent not initialised."
    updated: list[str] = []
    # target/scope/max_iterations have NO settings-singleton reader — the agent's
    # own attributes are their only live path, so write the agent directly (a
    # singleton write here would be dead config, the anti-pattern we fight).
    if "target" in args:
        _primary_agent.target = str(args["target"])
        updated.append(f"target → {args['target']}")
    if "scope" in args:
        _primary_agent.scope = list(args["scope"])  # type: ignore[arg-type]
        updated.append(f"scope → {args['scope']}")
    if "max_iterations" in args:
        _primary_agent.max_iterations = int(args["max_iterations"])  # type: ignore[arg-type]
        updated.append(f"max_iterations → {args['max_iterations']}")
    if "model" in args:
        # model is the one field with a settings-singleton reader
        # (delegate_task sub-agents read get_settings().model), so it needs the
        # double write — the last model write-side bypass on this entry:
        #   1) publish to the singleton so sub-agents/web converge (mirrors
        #      initializer's resolve→publish single-source invariant);
        #   2) re-point the primary agent's live LLM so its OWN subsequent runs
        #      use the new model (the main loop reads self.llm.model live).
        from ...config.settings import update_settings

        model = str(args["model"])
        update_settings(model=model)
        if getattr(_primary_agent, "llm", None) is not None:
            _primary_agent.llm.set_model(model)
        updated.append(f"model → {model}")
    return (
        "Updated:\n" + "\n".join(updated)
        if updated
        else "No recognised fields provided."
    )


# ===========================================================================
# GROUP: TASK EXECUTION
# ===========================================================================


@mcp_tool_registry.register(
    name="run_task",
    description=(
        "Submit a task and BLOCK until it completes. "
        "Use for short tasks where the result is needed immediately."
    ),
    schema={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Fully-specified task prompt"},
            "target": {
                "type": "string",
                "description": "Override primary target for this task",
            },
            "scope": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Override scope for this task",
            },
            "mode": {
                "type": "string",
                "description": "Task mode: auto | pentest | ctf",
            },
            "ctfType": {
                "type": "string",
                "description": "Optional CTF subtype hint: web | crypto | reverse | pwn | misc",
            },
            "resumeContext": {
                "type": "object",
                "description": "Optional prior run resume context with runId/checkpointId/summary",
            },
            "challengePath": {
                "type": "string",
                "description": "Optional local challenge root path for CTF tasks",
            },
            "artifactPaths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional local artifact/source paths associated with the challenge",
            },
            "blackboardSnapshot": {
                "type": "object",
                "description": "Optional ingress blackboard truth snapshot with facts and pendingVerifications",
            },
        },
        "required": ["task"],
    },
)
async def run_task(args: dict[str, object]) -> str:
    if not _primary_agent:
        return "[error] Primary agent not initialised."
    readiness = _current_model_readiness()
    if not readiness.get("ready"):
        return f"[error] model_not_ready: {readiness.get('reason')}"

    target, scope = _resolve_target_scope(args)
    mode_contract = _resolve_ingress_mode_contract(args)
    try:
        agent = await _make_agent(target, scope)
    except Exception as exc:
        return f"[error] Failed to create agent: {exc}"

    entry = _create_task(str(args["task"]), agent, target, scope)
    entry.mode = mode_contract["mode"]
    entry.modeSubtype = mode_contract["modeSubtype"]
    entry.goalStyle = mode_contract["goalStyle"]
    _apply_resume_contract(entry, args)
    _apply_local_asset_contract(entry, args)
    _assign_ctf_run_artifacts(entry)
    explicit_blackboard_snapshot = (
        args.get("blackboardSnapshot") if isinstance(args.get("blackboardSnapshot"), dict) else None
    )
    _apply_control_decision(
        entry,
        blackboard_snapshot=explicit_blackboard_snapshot,
    )
    entry.ingressHandoff = _build_ingress_handoff(
        entry,
        blackboard_snapshot=explicit_blackboard_snapshot,
    )
    _log("info", f"run_task [{entry.id}]: {entry.task[:80]}")
    if entry.controlDecision and entry.controlDecision.get("shouldRun") is False:
        _mark_entry_blocked(entry, str(entry.controlDecision.get("reason") or "blocked"))
        lines = [f"[status] {entry.status}"]
        lines.append(f"[mode] {entry.mode}")
        lines.append(f"[mode_subtype] {entry.modeSubtype}")
        lines.append(f"[goal_style] {entry.goalStyle}")
        lines.append(f"[control_decision] {entry.controlDecision.get('decisionKind')}")
        return "\n".join(lines)

    await _drive_task(entry)

    if entry.status == "error":
        return f"[error] {entry.error}"

    lines = [f"[result]\n{entry.result}"]
    lines.append(f"[mode] {entry.mode}")
    lines.append(f"[mode_subtype] {entry.modeSubtype}")
    lines.append(f"[goal_style] {entry.goalStyle}")
    if isinstance(entry.controlDecision, dict):
        lines.append(f"[control_decision] {entry.controlDecision.get('decisionKind')}")
    if entry.runId:
        lines.append(f"[run_id] {entry.runId}")
    if entry.ledgerPath:
        lines.append(f"[ledger_path] {entry.ledgerPath}")
    if entry.checkpointPath:
        lines.append(f"[checkpoint_path] {entry.checkpointPath}")
    if entry.resumeFromRunId:
        lines.append(f"[resume_from_run] {entry.resumeFromRunId}")
    if entry.resumeFromCheckpointId:
        lines.append(f"[resume_from_checkpoint] {entry.resumeFromCheckpointId}")
    if entry.challengePath:
        lines.append(f"[challenge_path] {entry.challengePath}")
    if entry.artifactPaths:
        lines.append("[artifact_paths] " + "; ".join(entry.artifactPaths))
    if entry.tool_calls:
        lines.append(
            "[tools_used] " + ", ".join(str(c["name"]) for c in entry.tool_calls)
        )
    if entry.notes_snapshot:
        lines.append(f"[notes_snapshot]\n{entry.notes_snapshot}")
    return "\n".join(lines)


@mcp_tool_registry.register(
    name="run_task_async",
    description=(
        "Submit a task and return IMMEDIATELY with a task_id. "
        "Use get_task_status to poll, or await_tasks to block until done."
    ),
    schema={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Fully-specified task prompt"},
            "target": {
                "type": "string",
                "description": "Override primary target for this task",
            },
            "scope": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Override scope for this task",
            },
            "mode": {
                "type": "string",
                "description": "Task mode: auto | pentest | ctf",
            },
            "ctfType": {
                "type": "string",
                "description": "Optional CTF subtype hint: web | crypto | reverse | pwn | misc",
            },
            "resumeContext": {
                "type": "object",
                "description": "Optional prior run resume context with runId/checkpointId/summary",
            },
            "challengePath": {
                "type": "string",
                "description": "Optional local challenge root path for CTF tasks",
            },
            "artifactPaths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional local artifact/source paths associated with the challenge",
            },
            "blackboardSnapshot": {
                "type": "object",
                "description": "Optional ingress blackboard truth snapshot with facts and pendingVerifications",
            },
        },
        "required": ["task"],
    },
)
async def run_task_async(args: dict[str, object]) -> str:
    if not _primary_agent:
        return "[error] Primary agent not initialised."
    readiness = _current_model_readiness()
    if not readiness.get("ready"):
        return f"[error] model_not_ready: {readiness.get('reason')}"

    target, scope = _resolve_target_scope(args)
    mode_contract = _resolve_ingress_mode_contract(args)
    try:
        agent = await _make_agent(target, scope)
    except Exception as exc:
        return f"[error] Failed to create agent: {exc}"

    entry = _create_task(str(args["task"]), agent, target, scope)
    entry.mode = mode_contract["mode"]
    entry.modeSubtype = mode_contract["modeSubtype"]
    entry.goalStyle = mode_contract["goalStyle"]
    _apply_resume_contract(entry, args)
    _apply_local_asset_contract(entry, args)
    _assign_ctf_run_artifacts(entry)
    explicit_blackboard_snapshot = (
        args.get("blackboardSnapshot") if isinstance(args.get("blackboardSnapshot"), dict) else None
    )
    _apply_control_decision(
        entry,
        blackboard_snapshot=explicit_blackboard_snapshot,
    )
    entry.ingressHandoff = _build_ingress_handoff(
        entry,
        blackboard_snapshot=explicit_blackboard_snapshot,
    )
    if entry.controlDecision and entry.controlDecision.get("shouldRun") is False:
        _mark_entry_blocked(entry, str(entry.controlDecision.get("reason") or "blocked"))
    else:
        asyncio.create_task(_drive_task(entry))
    _log("info", f"run_task_async [{entry.id}]: {entry.task[:80]}")
    lines = [
        f"task_id: {entry.id}\n"
        f"status: {entry.status}\n"
        f"task: {entry.task}\n"
        f"mode: {entry.mode}\n"
        f"mode_subtype: {entry.modeSubtype}\n"
        f"goal_style: {entry.goalStyle}"
    ]
    if isinstance(entry.controlDecision, dict):
        lines.append(f"\ncontrol_decision: {entry.controlDecision.get('decisionKind')}")
    next_action_explanation = _build_next_action_explanation(entry)
    if next_action_explanation.get("decisionKind"):
        lines.append(f"\nnext_action_decision_kind: {next_action_explanation.get('decisionKind')}")
    if next_action_explanation.get("nextAction"):
        lines.append(f"\nnext_action: {next_action_explanation.get('nextAction')}")
    if next_action_explanation.get("driver"):
        lines.append(f"\nnext_action_driver: {next_action_explanation.get('driver')}")
    if next_action_explanation.get("reason"):
        lines.append(f"\nnext_action_reason: {next_action_explanation.get('reason')}")
    if next_action_explanation.get("summary"):
        lines.append(f"\nnext_action_summary: {next_action_explanation.get('summary')}")
    if entry.runId:
        lines.append(f"\nrun_id: {entry.runId}")
    if entry.ledgerPath:
        lines.append(f"\nledger_path: {entry.ledgerPath}")
    if entry.checkpointPath:
        lines.append(f"\ncheckpoint_path: {entry.checkpointPath}")
    if entry.resumeFromRunId:
        lines.append(f"\nresume_from_run: {entry.resumeFromRunId}")
    if entry.resumeFromCheckpointId:
        lines.append(f"\nresume_from_checkpoint: {entry.resumeFromCheckpointId}")
    if entry.challengePath:
        lines.append(f"\nchallenge_path: {entry.challengePath}")
    if entry.artifactPaths:
        lines.append("\nartifact_paths: " + "; ".join(entry.artifactPaths))
    return "".join(lines)


# ===========================================================================
# GROUP: TASK INSPECTION
# ===========================================================================


@mcp_tool_registry.register(
    name="list_tasks",
    description="List all tasks with their status, target, and task summary.",
    schema={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "Filter: pending | running | done | error | cancelled",
            },
            "limit": {
                "type": "integer",
                "description": "Max entries, most recent first (default 20)",
            },
        },
        "required": [],
    },
)
async def list_tasks(args: dict[str, object]) -> str:
    entries = sorted(_tasks.values(), key=lambda e: e.created_at, reverse=True)
    if "status" in args:
        entries = [e for e in entries if e.status == str(args["status"])]
    entries = entries[: int(args.get("limit") or 20)]  # type: ignore[arg-type]
    if not entries:
        return "No tasks found."
    lines: list[str] = []
    for e in entries:
        summary = e.task[:55] + ("…" if len(e.task) > 55 else "")
        target = f" target={e.target}" if e.target else ""
        local_assets = f" challenge_path={e.challengePath}" if e.challengePath else ""
        mode = (
            f" mode={e.mode}/{e.modeSubtype}"
            if e.mode and e.modeSubtype
            else f" mode={e.mode}"
            if e.mode
            else ""
        )
        control_decision = (
            f" decision={e.controlDecision.get('decisionKind')}"
            if isinstance(e.controlDecision, dict) and e.controlDecision.get("decisionKind")
            else ""
        )
        next_action_explanation = _build_next_action_explanation(e)
        next_action = (
            f" next_action={next_action_explanation.get('nextAction')}"
            if next_action_explanation.get("nextAction")
            else ""
        )
        chain = f" chain={','.join(e.ctfChainUsed)}" if e.ctfChainUsed else ""
        lines.append(f"[{e.id}] {e.status:10s}{target}{local_assets}{mode}{control_decision}{next_action}{chain} | {e.created_at} | {summary}")
    return "\n".join(lines)


@mcp_tool_registry.register(
    name="get_task_status",
    description="Poll the current status and result preview of a task by task_id.",
    schema={
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"],
    },
)
async def get_task_status(args: dict[str, object]) -> str:
    entry = _tasks.get(str(args["task_id"]))
    if not entry:
        return f"[error] No task with id '{args['task_id']}'"
    lines: list[str] = [
        f"task_id:    {entry.id}",
        f"status:     {entry.status}",
        f"task:       {entry.task}",
        f"target:     {entry.target or 'none'}",
        f"created_at: {entry.created_at}",
    ]
    if entry.mode:
        lines.append(f"mode:       {entry.mode}")
    if entry.modeSubtype:
        lines.append(f"mode_subtype: {entry.modeSubtype}")
    if entry.goalStyle:
        lines.append(f"goal_style: {entry.goalStyle}")
    if isinstance(entry.controlDecision, dict) and entry.controlDecision.get("decisionKind"):
        lines.append(f"control_decision: {entry.controlDecision.get('decisionKind')}")
    _append_next_action_explanation_lines(lines, entry)
    _append_minimal_decision_record_lines(lines, entry.decisionRecords)
    if entry.runId:
        lines.append(f"run_id:     {entry.runId}")
    if entry.ledgerPath:
        lines.append(f"ledger_path: {entry.ledgerPath}")
    if entry.checkpointPath:
        lines.append(f"checkpoint_path: {entry.checkpointPath}")
    if entry.resumeFromRunId:
        lines.append(f"resume_from_run: {entry.resumeFromRunId}")
    if entry.resumeFromCheckpointId:
        lines.append(f"resume_from_checkpoint: {entry.resumeFromCheckpointId}")
    if entry.challengePath:
        lines.append(f"challenge_path: {entry.challengePath}")
    if entry.artifactPaths:
        lines.append("artifact_paths: " + "; ".join(entry.artifactPaths))
    challenge_context = (
        dict(entry.ingressHandoff.get("challengeContext") or {})
        if isinstance(entry.ingressHandoff, dict) and isinstance(entry.ingressHandoff.get("challengeContext"), dict)
        else {}
    )
    run_context = _entry_session_context(entry)
    _append_derived_target_context_lines(lines, challenge_context)
    derived_target_origin = _derived_target_origin(entry, challenge_context)
    if derived_target_origin:
        lines.append(f"derived_target_origin: {derived_target_origin}")
    if entry.finished_at:
        lines.append(f"finished_at: {entry.finished_at}")
    if entry.finalFlag:
        lines.append(f"final_flag: {entry.finalFlag}")
    if entry.ctfChainUsed:
        lines.append("ctf_chain_used: " + ", ".join(entry.ctfChainUsed))
    if entry.ctfMissingTools:
        lines.append("ctf_missing_tools: " + ", ".join(entry.ctfMissingTools))
    if entry.ctfNotes:
        lines.append("ctf_notes: " + " | ".join(entry.ctfNotes))
    _append_blackboard_snapshot_lines(lines, entry, run_context=run_context)
    _append_run_context_lines(lines, run_context)
    if entry.status == "done" and entry.result:
        lines.append(f"result (preview):\n{entry.result[:300]}")
    if entry.status == "error":
        lines.append(f"error: {entry.error}")
    if entry.tool_calls:
        lines.append(
            "tools_used: " + ", ".join(str(c["name"]) for c in entry.tool_calls)
        )
    return "\n".join(lines)


@mcp_tool_registry.register(
    name="get_task_result",
    description=(
        "Retrieve the full result of a completed task: final summary, "
        "thinking steps, tool calls and results, and notes snapshot."
    ),
    schema={
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"],
    },
)
async def get_task_result(args: dict[str, object]) -> str:
    entry = _tasks.get(str(args["task_id"]))
    if not entry:
        return f"[error] No task with id '{args['task_id']}'"
    if entry.status in ("pending", "running"):
        return f"[info] Task {entry.id} is still {entry.status}."

    lines: list[str] = [
        f"task_id:     {entry.id}",
        f"status:      {entry.status}",
        f"task:        {entry.task}",
        f"target:      {entry.target or 'none'}",
        f"scope:       {entry.scope}",
        f"created_at:  {entry.created_at}",
        f"finished_at: {entry.finished_at}",
    ]
    if entry.mode:
        lines.append(f"mode:        {entry.mode}")
    if entry.modeSubtype:
        lines.append(f"mode_subtype: {entry.modeSubtype}")
    if entry.goalStyle:
        lines.append(f"goal_style:  {entry.goalStyle}")
    if isinstance(entry.controlDecision, dict) and entry.controlDecision.get("decisionKind"):
        lines.append(f"control_decision: {entry.controlDecision.get('decisionKind')}")
    _append_next_action_explanation_lines(lines, entry)
    _append_minimal_decision_record_lines(lines, entry.decisionRecords)
    if entry.runId:
        lines.append(f"run_id:      {entry.runId}")
    if entry.ledgerPath:
        lines.append(f"ledger_path: {entry.ledgerPath}")
    if entry.checkpointPath:
        lines.append(f"checkpoint_path: {entry.checkpointPath}")
    if entry.resumeFromRunId:
        lines.append(f"resume_from_run: {entry.resumeFromRunId}")
    if entry.resumeFromCheckpointId:
        lines.append(f"resume_from_checkpoint: {entry.resumeFromCheckpointId}")
    if entry.challengePath:
        lines.append(f"challenge_path: {entry.challengePath}")
    if entry.artifactPaths:
        lines.append("artifact_paths: " + "; ".join(entry.artifactPaths))
    challenge_context = (
        dict(entry.ingressHandoff.get("challengeContext") or {})
        if isinstance(entry.ingressHandoff, dict) and isinstance(entry.ingressHandoff.get("challengeContext"), dict)
        else {}
    )
    run_context = _entry_session_context(entry)
    _append_derived_target_context_lines(lines, challenge_context)
    derived_target_origin = _derived_target_origin(entry, challenge_context)
    if derived_target_origin:
        lines.append(f"derived_target_origin: {derived_target_origin}")
    if entry.finalFlag:
        lines.append(f"final_flag:  {entry.finalFlag}")
    if entry.ctfChainUsed:
        lines.append("\n[ctf_chain_used]")
        lines.extend(f"  {item}" for item in entry.ctfChainUsed)
    if entry.ctfMissingTools:
        lines.append("\n[ctf_missing_tools]")
        lines.extend(f"  {item}" for item in entry.ctfMissingTools)
    if entry.ctfNotes:
        lines.append("\n[ctf_notes]")
        lines.extend(f"  {item}" for item in entry.ctfNotes)
    _append_blackboard_snapshot_lines(lines, entry, run_context=run_context)
    _append_run_context_lines(lines, run_context)
    if entry.thinking:
        lines.append("\n[thinking]")
        lines.extend(f"  {t}" for t in entry.thinking)
    if entry.tool_calls:
        lines.append("\n[tool_calls]")
        for c in entry.tool_calls:
            lines.append(f"  {c['name']}({c['arguments']})")
    if entry.tool_results:
        lines.append("\n[tool_results]")
        for r in entry.tool_results:
            if r["success"]:
                lines.append(f"  ✓ {r['tool_name']}: {str(r['result'] or '')[:200]}")
            else:
                lines.append(f"  ✗ {r['tool_name']} [FAILED]: {r['error']}")
    if entry.result:
        lines.append(f"\n[result]\n{entry.result}")
    if entry.notes_snapshot:
        lines.append(f"\n[notes_snapshot]\n{entry.notes_snapshot}")
    if entry.error:
        lines.append(f"\n[error]\n{entry.error}")
    return "\n".join(lines)


@mcp_tool_registry.register(
    name="await_tasks",
    description=(
        "Block until ALL given task_ids have finished (done / error / cancelled). "
        "Polls every 500 ms; returns a one-line summary per task."
    ),
    schema={
        "type": "object",
        "properties": {
            "task_ids": {"type": "array", "items": {"type": "string"}},
            "timeout_seconds": {
                "type": "number",
                "description": "Max wait (default 120)",
            },
        },
        "required": ["task_ids"],
    },
)
async def await_tasks(args: dict[str, object]) -> str:
    task_ids = [str(tid) for tid in args["task_ids"]]  # type: ignore[union-attr]
    timeout = float(args.get("timeout_seconds") or 120)  # type: ignore[arg-type]
    elapsed = 0.0

    while elapsed < timeout:
        if all(
            tid in _tasks and _tasks[tid].status not in ("pending", "running")
            for tid in task_ids
        ):
            break
        await asyncio.sleep(0.5)
        elapsed += 0.5

    lines: list[str] = []
    for tid in task_ids:
        entry = _tasks.get(tid)
        if not entry:
            lines.append(f"[{tid}] NOT FOUND")
        elif entry.status == "done":
            lines.append(
                f"[{tid}] done      | {(entry.result or '')[:120].replace(chr(10), ' ')}"
            )
        elif entry.status == "error":
            lines.append(f"[{tid}] error     | {entry.error}")
        elif entry.status == "cancelled":
            lines.append(f"[{tid}] cancelled")
        else:
            lines.append(f"[{tid}] {entry.status} (timed out after {timeout}s)")
    return "\n".join(lines)


# ===========================================================================
# GROUP: TASK CONTROL
# ===========================================================================


@mcp_tool_registry.register(
    name="cancel_task",
    description="Cancel a running or pending task.",
    schema={
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"],
    },
)
async def cancel_task(args: dict[str, object]) -> str:
    entry = _tasks.get(str(args["task_id"]))
    if not entry:
        return f"[error] No task with id '{args['task_id']}'"
    if entry.status not in ("pending", "running"):
        return f"[info] Task {entry.id} is already '{entry.status}', cannot cancel."
    entry.status = "cancelled"
    entry.finished_at = datetime.utcnow().isoformat()
    _log("info", f"cancel_task [{entry.id}]")
    return f"[ok] Task {entry.id} marked for cancellation."


# ===========================================================================
# GROUP: TOOL MANAGEMENT
# ===========================================================================


@mcp_tool_registry.register(
    name="list_tools",
    description="List all tools available to tasks, expanding any RAG optimizer.",
    schema={"type": "object", "properties": {}, "required": []},
)
async def list_tools(args: dict[str, object]) -> str:
    if not _primary_agent:
        return "[error] Primary agent not initialised."
    tools = _primary_agent.get_tools()
    if not tools:
        return "No tools registered."
    lines = [f"{t.name}: {getattr(t, 'description', '')}" for t in tools]
    return f"Total tools: {len(lines)}\n" + "\n".join(lines)


@mcp_tool_registry.register(
    name="enable_tool",
    description="Enable a tool on the primary agent by name.",
    schema={
        "type": "object",
        "properties": {"tool_name": {"type": "string"}},
        "required": ["tool_name"],
    },
)
async def enable_tool(args: dict[str, object]) -> str:
    if not _primary_agent:
        return "[error] Primary agent not initialised."
    name = str(args["tool_name"])
    for tool in _primary_agent.tools:
        if tool.name == name:
            tool.enabled = True
            _log("info", f"enable_tool: {name}")
            return f"[ok] Tool '{name}' enabled."
    return f"[error] Tool '{name}' not found."


@mcp_tool_registry.register(
    name="disable_tool",
    description="Disable a tool on the primary agent by name.",
    schema={
        "type": "object",
        "properties": {"tool_name": {"type": "string"}},
        "required": ["tool_name"],
    },
)
async def disable_tool(args: dict[str, object]) -> str:
    if not _primary_agent:
        return "[error] Primary agent not initialised."
    name = str(args["tool_name"])
    for tool in _primary_agent.tools:
        if tool.name == name:
            tool.enabled = False
            _log("info", f"disable_tool: {name}")
            return f"[ok] Tool '{name}' disabled."
    return f"[error] Tool '{name}' not found."


# ===========================================================================
# GROUP: CONVERSATION HISTORY
# ===========================================================================


@mcp_tool_registry.register(
    name="get_conversation_history",
    description=(
        "Return the conversation history of a task by task_id, "
        "or the primary agent if omitted."
    ),
    schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Omit for primary agent"},
            "limit": {
                "type": "integer",
                "description": "Max messages, most recent first (default 20)",
            },
        },
        "required": [],
    },
)
async def get_conversation_history(args: dict[str, object]) -> str:
    if "task_id" in args:
        entry = _tasks.get(str(args["task_id"]))
        if not entry:
            return f"[error] No task with id '{args['task_id']}'"
        agent = entry.agent
    else:
        if not _primary_agent:
            return "[error] Primary agent not initialised."
        agent = _primary_agent

    history = agent.conversation_history[-int(args.get("limit") or 20) :]  # type: ignore[arg-type]
    if not history:
        return "No conversation history."

    lines: list[str] = []
    for msg in history:
        role = msg.role.upper()
        content = (msg.content or "").strip()[:200]
        if msg.tool_calls:
            lines.append(
                f"[{role}] (tool_calls: {', '.join(c.name for c in msg.tool_calls)}) {content}"
            )
        elif msg.tool_results:
            lines.append(
                f"[{role}] (tool_results: {', '.join(r.tool_name for r in msg.tool_results)})"
            )
        else:
            lines.append(f"[{role}] {content}")
    return "\n".join(lines)


@mcp_tool_registry.register(
    name="reset_conversation",
    description="Reset the conversation history of a task, or the primary agent if omitted.",
    schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Omit for primary agent"},
        },
        "required": [],
    },
)
async def reset_conversation(args: dict[str, object]) -> str:
    if "task_id" in args:
        entry = _tasks.get(str(args["task_id"]))
        if not entry:
            return f"[error] No task with id '{args['task_id']}'"
        entry.agent.reset()
        _log("info", f"reset_conversation [{args['task_id']}]")
        return f"[ok] Task {args['task_id']} conversation reset."
    if not _primary_agent:
        return "[error] Primary agent not initialised."
    _primary_agent.reset()
    _log("info", "reset_conversation [primary]")
    return "[ok] Primary agent conversation reset."


# ===========================================================================
# GROUP: MEMORY
# ===========================================================================


@mcp_tool_registry.register(
    name="store_memory",
    description="Persist a key-value pair to the in-memory store.",
    schema={
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": ["key", "value"],
    },
)
async def store_memory(args: dict[str, object]) -> str:
    key = str(args["key"])
    _memory[key] = {
        "value": str(args["value"]),
        "stored_at": datetime.utcnow().isoformat(),
    }
    return f"[ok] Stored key '{key}'"


@mcp_tool_registry.register(
    name="retrieve_memory",
    description=(
        "Retrieve a value by exact key, search by substring, "
        "or list all keys (omit both arguments)."
    ),
    schema={
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "search": {"type": "string"},
        },
        "required": [],
    },
)
async def retrieve_memory(args: dict[str, object]) -> str:
    if "key" in args:
        mem = _memory.get(str(args["key"]))
        if not mem:
            return f"[error] Key '{args['key']}' not found"
        return (
            f"key: {args['key']}\nvalue: {mem['value']}\nstored_at: {mem['stored_at']}"
        )
    if "search" in args:
        matches = {
            k: v for k, v in _memory.items() if str(args["search"]).lower() in k.lower()
        }
        return (
            "\n".join(f"{k}: {v['value'][:80]}" for k, v in matches.items())
            or f"No keys matching '{args['search']}'"
        )
    return (
        "\n".join(f"{k}: {v['value'][:80]}" for k, v in _memory.items())
        or "Memory is empty."
    )


@mcp_tool_registry.register(
    name="clear_memory",
    description="Delete a specific memory key, or wipe all memory with scope='all'.",
    schema={
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "scope": {
                "type": "string",
                "description": "Pass 'all' to clear everything",
            },
        },
        "required": [],
    },
)
async def clear_memory(args: dict[str, object]) -> str:
    if "key" in args:
        key = str(args["key"])
        if key not in _memory:
            return f"[error] Key '{key}' not found"
        del _memory[key]
        return f"[ok] Deleted '{key}'"
    if args.get("scope") == "all":
        count = len(_memory)
        _memory.clear()
        return f"[ok] Cleared {count} entries"
    return "[error] Provide 'key' or scope='all'."


# ===========================================================================
# GROUP: OBSERVABILITY
# ===========================================================================


@mcp_tool_registry.register(
    name="get_logs",
    description="Return recent execution logs. Optionally filter by level: info | warning | error.",
    schema={
        "type": "object",
        "properties": {
            "level": {"type": "string"},
            "limit": {"type": "integer", "description": "Max lines (default 50)"},
        },
        "required": [],
    },
)
async def get_logs(args: dict[str, object]) -> str:
    entries = list(reversed(_logs))
    if "level" in args:
        entries = [e for e in entries if e["level"] == str(args["level"])]
    entries = entries[: int(args.get("limit") or 50)]  # type: ignore[arg-type]
    if not entries:
        return "No log entries found."
    return "\n".join(
        f"[{e['ts']}] [{e['level'].upper():7s}] {e['message']}" for e in entries
    )


@mcp_tool_registry.register(
    name="get_metrics",
    description="Return runtime metrics: task counts, success rate, total tool calls, memory and log sizes.",
    schema={"type": "object", "properties": {}, "required": []},
)
async def get_metrics(args: dict[str, object]) -> str:
    total = len(_tasks)
    done = sum(1 for e in _tasks.values() if e.status == "done")
    errors = sum(1 for e in _tasks.values() if e.status == "error")
    canc = sum(1 for e in _tasks.values() if e.status == "cancelled")
    active = sum(1 for e in _tasks.values() if e.status in ("pending", "running"))
    return "\n".join(
        [
            f"total_tasks:      {total}",
            f"active:           {active}",
            f"completed:        {done}",
            f"errors:           {errors}",
            f"cancelled:        {canc}",
            f"success_rate:     {f'{done / total * 100:.1f}%' if total else 'n/a'}",
            f"total_tool_calls: {sum(len(e.tool_calls) for e in _tasks.values())}",
            f"memory_keys:      {len(_memory)}",
            f"log_entries:      {len(_logs)}",
        ]
    )
