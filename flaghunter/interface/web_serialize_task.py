"""Task serialization + blackboard-snapshot merge builders.

Extracted from web_server.py (god-module 分簇·刀6, 债池第五波). This themed
cluster normalizes a raw task dict into its API projection (`_serialize_task`)
and its supporting helpers — capability flags, collection normalization,
detail defaults, and blackboard-snapshot merge. It is down-closed: members call
only each other plus already-extracted siblings (web_leaf_utils, blackboard_lite,
web_decision_summaries), so it carries no upward dependency on web_server.
"""

from __future__ import annotations

from typing import Any

from .blackboard_lite import (
    build_task_blackboard_snapshot,
    normalize_blackboard_snapshot,
    serialize_blackboard_snapshot,
)
from .web_decision_summaries import (
    _build_action_path_summary,
    _build_active_decision_summary,
    _build_decision_provenance_summary,
    _build_next_action_explanation,
)
from .web_leaf_utils import _duration_ms_for_task, _normalize_string_list


def _task_capabilities(task: dict[str, Any]) -> dict[str, bool]:
    status = str(task.get("status") or "")
    return {
        "hint": True,
        "stop": status in {"queued", "running"},
        "continue": status == "running",
        "retry": status in {"success", "failed", "stopped"},
        "attachments": True,
    }


def _task_detail_defaults() -> dict[str, list[Any]]:
    return {
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
        "artifactPaths": [],
        "ctfChainUsed": [],
        "ctfMissingTools": [],
        "ctfNotes": [],
    }


def _normalize_task_collections(task: dict[str, Any]) -> dict[str, Any]:
    item = dict(task)
    defaults = _task_detail_defaults()
    for key, default in defaults.items():
        value = item.get(key)
        item[key] = value if isinstance(value, list) else list(default)
    item["hints"] = [hint for hint in item["hints"] if isinstance(hint, dict)]
    item["messages"] = [message for message in item["messages"] if isinstance(message, dict)]
    item["plan"] = [step for step in item["plan"] if isinstance(step, dict)]
    item["notes"] = [note for note in item["notes"] if isinstance(note, dict)]
    item["knowledgeHits"] = [hit for hit in item["knowledgeHits"] if isinstance(hit, dict)]
    item["attachments"] = [attachment for attachment in item["attachments"] if isinstance(attachment, dict)]
    item["artifactPaths"] = _normalize_string_list(item["artifactPaths"])
    item["ctfChainUsed"] = _normalize_string_list(item["ctfChainUsed"])
    item["ctfMissingTools"] = _normalize_string_list(item["ctfMissingTools"])
    item["ctfNotes"] = _normalize_string_list(item["ctfNotes"])
    challenge_path = str(item.get("challengePath") or "").strip()
    item["challengePath"] = challenge_path or None
    return item


def _serialize_task(task: dict[str, Any]) -> dict[str, Any]:
    item = _normalize_task_collections(task)
    item["durationMs"] = _duration_ms_for_task(item)
    blackboard_snapshot = _merge_blackboard_snapshots(
        build_task_blackboard_snapshot(item),
        item.get("blackboardSnapshot") if isinstance(item.get("blackboardSnapshot"), dict) else None,
    )
    serialized_blackboard_snapshot = serialize_blackboard_snapshot(blackboard_snapshot)
    decision_provenance = _build_decision_provenance_summary(
        item.get("controlDecision"),
        serialized_blackboard_snapshot,
    )
    action_path_summary = _build_action_path_summary(
        item.get("controlDecision"),
        serialized_blackboard_snapshot,
        decision_provenance,
    )
    next_action_explanation = _build_next_action_explanation(
        item.get("controlDecision"),
        action_path_summary,
        decision_provenance,
    )
    if next_action_explanation:
        item["nextActionExplanation"] = next_action_explanation
    item["activeDecisionSummary"] = _build_active_decision_summary(
        serialized_blackboard_snapshot,
    )
    item["capabilities"] = _task_capabilities(item)
    return item


def _normalized_blackboard_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return normalize_blackboard_snapshot(snapshot)


def _merge_blackboard_snapshots(
    primary: dict[str, Any] | None,
    secondary: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = _normalized_blackboard_snapshot(primary)
    fallback = _normalized_blackboard_snapshot(secondary)
    list_keys = (
        "facts",
        "hypotheses",
        "pendingVerifications",
        "decisions",
        "candidates",
        "actionResults",
    )
    dict_keys = ("recommendedAction", "activeDecision")
    for key in list_keys:
        if not merged[key] and fallback[key]:
            merged[key] = list(fallback[key])
    for key in dict_keys:
        if not merged[key] and fallback[key]:
            merged[key] = dict(fallback[key])
            continue
        if merged[key] and fallback[key]:
            merged_dict = dict(merged[key])
            fallback_dict = dict(fallback[key])
            for fallback_key, fallback_value in fallback_dict.items():
                if fallback_key not in merged_dict or merged_dict.get(fallback_key) in (None, "", [], {}):
                    merged_dict[fallback_key] = fallback_value
            merged[key] = merged_dict
    return merged
