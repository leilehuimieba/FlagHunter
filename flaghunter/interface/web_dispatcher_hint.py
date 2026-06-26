"""CTF dispatcher hint construction (debt ledger 第五波·刀18).

Extracted from web_server.py. This themed cluster builds the structured hint
string handed to the CTF dispatcher: it picks the latest meaningful user hint
and assembles a ``[local_ctf_assets]`` block from the task's control decision,
blackboard snapshot, challenge context and resume bootstrap. Members call only
each other plus the shared leaf ``_normalize_string_list`` (web_leaf_utils),
the already-extracted ``_build_ctf_challenge_context`` (web_challenge_context),
and upstream contract builders ``build_task_blackboard_snapshot``
(blackboard_lite) / ``build_control_decision_parts`` (control_contract), so the
cluster is down-closed with zero upward dependency on web_server. web_server
re-imports the set so the stay-behind caller (the run-agent-task ingress path)
resolves unchanged. Note: cli.py and mcp_tools define their own independent
``_ctf_dispatcher_hint``; only the web_server copy moves here.
"""

from __future__ import annotations

from typing import Any

from .blackboard_lite import build_task_blackboard_snapshot
from .control_contract import build_control_decision_parts
from .web_challenge_context import _build_ctf_challenge_context
from .web_leaf_utils import _normalize_string_list


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
