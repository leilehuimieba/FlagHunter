"""CTF challenge-context projection & lineage (debt ledger 第五波·刀13).

Extracted from web_server.py. This themed cluster builds and propagates a task's
CTF challenge context — challenge path / artifact paths / resume context, plus
runtime- and source-derived-target inheritance for the ingress handoff. Members
call only each other and the shared leaf ``_normalize_string_list`` in
web_leaf_utils, so the cluster is down-closed with zero upward dependency on
web_server. It is the base of the ingress-handoff (簇7) and dispatcher-hint (簇8)
clusters, so it is extracted first; those callers stay behind and resolve
``web_server._build_ctf_challenge_context`` via re-import unchanged.
"""

from __future__ import annotations

from typing import Any

from .web_leaf_utils import _normalize_string_list


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
