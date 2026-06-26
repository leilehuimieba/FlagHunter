"""Control-decision application from task blackboard (debt ledger 第五波·刀17).

Extracted from web_server.py. This narrow themed cluster builds the per-task
blackboard snapshot used for control decisions, seeds it from a source task on
replay/retry, and applies (or follow-up re-applies) a resolved control decision
to a task. Members call only each other plus the shared serialize-task helpers
``_normalized_blackboard_snapshot`` / ``_merge_blackboard_snapshots``
(web_serialize_task) and upstream contract builders
``build_task_blackboard_snapshot`` (blackboard_lite) /
``resolve_control_decision`` / ``build_decision_record`` (control_contract), so
the cluster is down-closed with zero upward dependency on web_server. web_server
re-imports the set so stay-behind callers (``_build_ingress_handoff`` and the
replay / retry / continue ingress paths) resolve unchanged.
"""

from __future__ import annotations

from typing import Any

from .blackboard_lite import build_task_blackboard_snapshot
from .control_contract import build_decision_record, resolve_control_decision
from .web_serialize_task import (
    _merge_blackboard_snapshots,
    _normalized_blackboard_snapshot,
)


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
