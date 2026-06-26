"""Task mode / goal / asset contract normalization (debt ledger 第五波·刀12).

Extracted from web_server.py. This themed cluster projects an inbound task
payload onto its normalized contract: resolving the run mode (web vs ctf, via
``resolve_mode_contract``), filling an effective goal, and normalizing the
challenge-path / artifact-path asset contract. Members call only each other, the
horizontal sibling ``mode_router`` (web_server's own upstream — imports nothing
from web_server, so no cycle), and the shared leaf ``_normalize_string_list`` in
web_leaf_utils. web_server re-imports the set so the route-handler callers in
``_make_handlers`` resolve ``web_server._apply_mode_contract`` etc. unchanged.

Note: ``_latest_user_hint`` is deliberately NOT moved here — despite the original
candidate list grouping it with the asset contract, its only caller is
``_ctf_dispatcher_hint`` (ctf-dispatcher cluster), so it stays behind in
web_server.
"""

from __future__ import annotations

from typing import Any

from .mode_router import resolve_mode_contract
from .web_leaf_utils import _normalize_string_list


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
