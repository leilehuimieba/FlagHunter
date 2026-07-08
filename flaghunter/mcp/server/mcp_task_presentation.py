"""Task-inspection presentation helpers for the MCP server tools.

First physical-split slice extracted from the ``mcp_tools`` god-module (~2094
lines), applying the same behavior-preserving pattern used to split
``interface.web_server``: move a cohesive, down-closed, unpatched leaf cluster to
a sibling and re-import it back into the ``mcp_tools`` namespace so every
reference (``mcp_tools._derived_target_origin`` etc.) still resolves.

These four functions append human-readable lines to the ``get_task_status`` /
``get_task_result`` tool output (or derive a target-origin label). They are pure
leaves: they call no other ``mcp_tools`` function, touch no module state, and are
not part of the test monkeypatch surface — their only callers are the decorated
``get_task_status`` / ``get_task_result`` tools, which stay in ``mcp_tools`` and
resolve these names via re-import. The lone external name, ``TaskEntry``, is used
only as a lazy annotation (``from __future__ import annotations`` is active in
both modules), so it is imported under ``TYPE_CHECKING`` only — no runtime import
of ``mcp_tools`` and therefore no import cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mcp_tools import TaskEntry


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
