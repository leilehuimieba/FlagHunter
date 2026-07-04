from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .claim_views import preferred_flag_summary
from .ctf_state import CTFState
from .evidence_snapshot import build_p2_evidence_snapshot
from .ledger_event_views import build_p2_ledger_event_readback
from .reasoning_evidence_context import build_evidence_reasoning_context
from .task_dag_plan import build_task_dag_plan_readback
from flaghunter.harness.artifact_registry import ArtifactRegistry
from flaghunter.harness.checkpoint_store import CheckpointStore
from flaghunter.harness.session_ledger import SessionLedger


def _normalize_artifact_roots(
    artifact_root: str | Path | list[str | Path] | tuple[str | Path, ...],
) -> list[Path]:
    if isinstance(artifact_root, (list, tuple)):
        items = artifact_root
    else:
        items = [artifact_root]
    roots: list[Path] = []
    seen: set[str] = set()
    for item in items:
        path = Path(item)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        roots.append(path)
    return roots


def _format_claim_evidence_summary(refs: list[dict[str, Any]], *, limit: int = 3) -> str:
    parts: list[str] = []
    for item in list(refs or [])[: max(0, int(limit))]:
        claim_id = str(item.get("claimId") or "").strip()
        kind = str(item.get("kind") or "").strip()
        level = str(item.get("level") or "").strip()
        status = str(item.get("status") or "").strip()
        preview = _prompt_safe_context_preview(item.get("contentPreview")).strip()
        trace_id = str(
            item.get("primaryTraceId")
            or item.get("sourceTraceId")
            or ""
        ).strip()
        receipt_id = str(item.get("sourceReceiptId") or "").strip()
        source_tool = str(item.get("sourceTool") or "").strip()
        latest_decision = str(item.get("latestVerificationDecision") or "").strip()
        segments = [
            value
            for value in [
                claim_id,
                f"{kind}/{level}/{status}".strip("/"),
                preview,
                f"trace={trace_id}" if trace_id else "",
                f"receipt={receipt_id}" if receipt_id else "",
                f"tool={source_tool}" if source_tool else "",
                f"decision={latest_decision}" if latest_decision else "",
            ]
            if value
        ]
        if segments:
            parts.append("[" + " ".join(segments) + "]")
    return " ".join(parts)


def _format_p3_solve_summary(summary: dict[str, Any]) -> str:
    node_count = int(summary.get("nodeCount", 0) or 0)
    edge_count = int(summary.get("edgeCount", 0) or 0)
    brief_count = int(summary.get("taskBriefCount", 0) or 0)
    receipt_count = int(summary.get("solveNodeReceiptCount", 0) or 0)
    crew_worker_count = int(summary.get("crewWorkerCount", 0) or 0)
    crew_receipt_count = int(summary.get("crewReceiptCount", 0) or 0)
    if not any(
        [
            node_count,
            edge_count,
            brief_count,
            receipt_count,
            crew_worker_count,
            crew_receipt_count,
        ]
    ):
        return ""
    parts = [
        f"solve_nodes={node_count}",
        f"solve_edges={edge_count}",
        f"task_briefs={brief_count}",
        f"node_receipts={receipt_count}",
    ]
    if crew_worker_count:
        parts.append(f"crew_workers={crew_worker_count}")
    if crew_receipt_count:
        parts.append(f"crew_receipts={crew_receipt_count}")
    receipt_status_counts = (
        summary.get("receiptStatusCounts")
        if isinstance(summary.get("receiptStatusCounts"), dict)
        else {}
    )
    if receipt_status_counts:
        statuses = [
            f"{key}:{receipt_status_counts[key]}"
            for key in sorted(receipt_status_counts)
            if str(key).strip()
        ]
        if statuses:
            parts.append("node_receipt_statuses=" + ",".join(statuses))
    worker_type_counts = (
        summary.get("crewWorkerTypeCounts")
        if isinstance(summary.get("crewWorkerTypeCounts"), dict)
        else {}
    )
    if worker_type_counts:
        worker_types = [
            f"{key}:{worker_type_counts[key]}"
            for key in sorted(worker_type_counts)
            if str(key).strip()
        ]
        if worker_types:
            parts.append("worker_types=" + ",".join(worker_types))
    return " ".join(parts)


def _format_task_dag_plan_summary(summary: dict[str, Any]) -> str:
    node_count = int(summary.get("nodeCount", 0) or 0)
    edge_count = int(summary.get("edgeCount", 0) or 0)
    if not node_count and not edge_count:
        return ""
    parts = [
        f"task_dag_nodes={node_count}",
        f"task_dag_edges={edge_count}",
    ]
    status_counts = (
        summary.get("statusCounts")
        if isinstance(summary.get("statusCounts"), dict)
        else {}
    )
    if status_counts:
        statuses = [
            f"{key}:{status_counts[key]}"
            for key in sorted(status_counts)
            if str(key).strip()
        ]
        if statuses:
            parts.append("task_dag_statuses=" + ",".join(statuses))
    restore_warning_count = int(summary.get("restoreWarningCount", 0) or 0)
    if restore_warning_count:
        parts.append(f"task_dag_restore_warnings={restore_warning_count}")
    return " ".join(parts)


_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(token|api[_-]?key|password|secret|session|cookie|authorization)"
)


def _prompt_safe_context_preview(value: Any, *, limit: int = 160) -> str:
    text = _redact_context_text(value)
    if _looks_like_raw_body(text):
        return "<redacted raw body>"[: max(0, int(limit))]
    return text[: max(0, int(limit))]


def _looks_like_raw_body(text: str) -> bool:
    if not text:
        return False
    return any(
        re.search(pattern, text)
        for pattern in (
            r"(?im)^\s*PING\s+",
            r"(?im)^\s*\d+\s+bytes\s+from\s+",
            r"(?im)^\s*uid=\d+\(",
            r"(?im)^\s*gid=\d+\(",
            r"(?im)^\s*HTTP/\d(?:\.\d)?\s+\d{3}\b",
            r"(?is)<!doctype\s+html|<html[\s>]",
        )
    )


def _redact_context_text(value: Any) -> str:
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


def _safe_context_value(value: Any, *, key: str = "", limit: int = 500) -> Any:
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if _SENSITIVE_KEY_RE.search(str(key or "")):
        return "<redacted>"
    if isinstance(value, dict):
        return {
            str(item_key): _safe_context_value(item_value, key=str(item_key), limit=limit)
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_context_value(item, limit=limit) for item in value]
    return _redact_context_text(value)[: max(0, int(limit))]


def _safe_context_payload(payload: Any, *, limit: int = 500) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): _safe_context_value(value, key=str(key), limit=limit)
        for key, value in payload.items()
    }


class SessionContextView:
    """Read a compact, queryable run context from harness stores."""

    def __init__(
        self,
        *,
        ledger_root: str | Path,
        artifact_root: str | Path | list[str | Path] | tuple[str | Path, ...],
        checkpoint_root: str | Path,
    ) -> None:
        self._ledger = SessionLedger(ledger_root)
        self._artifact_roots = _normalize_artifact_roots(artifact_root)
        self._artifacts = [ArtifactRegistry(root) for root in self._artifact_roots]
        self._checkpoints = CheckpointStore(checkpoint_root)

    def build_run_context(
        self,
        run_id: str,
        *,
        event_limit: int = 20,
        artifact_limit: int = 20,
    ) -> dict[str, Any]:
        normalized_run_id = str(run_id or "").strip()
        events = self._ledger.tail_events(normalized_run_id, limit=event_limit)
        artifacts: list[dict[str, Any]] = []
        for registry in self._artifacts:
            artifacts.extend(registry.list_artifacts(normalized_run_id))
        if artifact_limit >= 0:
            artifacts = artifacts[-max(0, artifact_limit):]
        latest_checkpoint = self._checkpoints.latest_checkpoint(normalized_run_id)

        context = {
            "runId": normalized_run_id,
            "recentEvents": [
                {
                    "type": str(item.get("event_type") or ""),
                    "t": item.get("ts"),
                    "payload": _safe_context_payload(item.get("payload") or {}),
                }
                for item in events
            ],
            "artifacts": [
                {
                    "artifactId": str(item.get("artifact_id") or ""),
                    "kind": _redact_context_text(item.get("kind"))[:200],
                    "title": _redact_context_text(item.get("title"))[:200],
                    "path": _safe_context_value(item.get("path")),
                    "location": _safe_context_value(item.get("location")),
                    "producer": _redact_context_text(item.get("producer"))[:200],
                    "metadata": _safe_context_payload(
                        item.get("metadata") or {},
                        limit=200,
                    ),
                    "t": item.get("ts"),
                }
                for item in artifacts
            ],
            "latestCheckpoint": None,
            "resumeContext": None,
            "resumeIngress": None,
        }

        if latest_checkpoint:
            snapshot = CTFState.from_snapshot(dict(latest_checkpoint.get("state") or {}))
            flag_summary = preferred_flag_summary(snapshot)
            evidence_snapshot = build_p2_evidence_snapshot(
                snapshot,
                trace_ref_limit=5,
                claim_evidence_limit=5,
                audit_claim_limit=5,
                audit_trace_limit=10,
                audit_verification_record_limit=10,
                preview_limit=160,
            )
            trace_refs = list(evidence_snapshot["traceRefs"])
            claim_evidence_refs = list(evidence_snapshot["claimEvidenceRefs"])
            audit_evidence_export = dict(evidence_snapshot["auditEvidenceExport"])
            p3_solve_snapshot = dict(evidence_snapshot.get("p3SolveSnapshot") or {})
            evidence_reasoning_context = build_evidence_reasoning_context(
                snapshot,
                limit=5,
                preview_limit=160,
            )
            task_dag_plan_readback = build_task_dag_plan_readback(
                snapshot.get_task_dag_plan(),
                node_limit=5,
                edge_limit=10,
                preview_limit=160,
            )
            context["latestCheckpoint"] = {
                "checkpointId": str(latest_checkpoint.get("checkpoint_id") or ""),
                "label": str(latest_checkpoint.get("label") or ""),
                "t": latest_checkpoint.get("ts"),
                "metadata": _safe_context_payload(
                    latest_checkpoint.get("metadata") or {},
                    limit=200,
                ),
                "stopReason": str(audit_evidence_export.get("stopReason") or ""),
                "verifiedFlags": list(flag_summary["verifiedFlags"]),
                "runtimeFlags": list(flag_summary["runtimeFlags"]),
                "rejectedFlags": list(flag_summary["rejectedFlags"]),
                "retractedFlags": list(flag_summary["retractedFlags"]),
                "artifactCount": len(snapshot.artifacts),
                "observationCount": len(snapshot.observations),
                "traceRefs": trace_refs,
                "claimEvidenceRefs": claim_evidence_refs,
                "auditEvidenceExport": audit_evidence_export,
                "p3SolveSnapshot": p3_solve_snapshot,
                "evidenceReasoningContext": evidence_reasoning_context,
                "taskDagPlanReadback": task_dag_plan_readback,
            }

        recent_event_types = [
            str(item.get("type") or "").strip()
            for item in list(context.get("recentEvents") or [])
            if str(item.get("type") or "").strip()
        ]
        for event in context["recentEvents"]:
            if str(event.get("type") or "").strip() != "dispatcher_started":
                continue
            payload = dict(event.get("payload") or {})
            has_resume_context = bool(payload.get("has_resume_context"))
            resume_run_id = str(payload.get("resume_run_id") or "").strip()
            resume_checkpoint_id = str(payload.get("resume_checkpoint_id") or "").strip()
            if not (has_resume_context or resume_run_id or resume_checkpoint_id):
                continue
            context["resumeIngress"] = {
                "hasResumeContext": has_resume_context or bool(resume_run_id or resume_checkpoint_id),
                "runId": resume_run_id,
                "checkpointId": resume_checkpoint_id,
                "sourceEvent": "dispatcher_started",
            }
            break
        latest_checkpoint_summary = (
            context.get("latestCheckpoint")
            if isinstance(context.get("latestCheckpoint"), dict)
            else None
        )
        if recent_event_types or context["artifacts"] or latest_checkpoint_summary:
            checkpoint_label = (
                str(latest_checkpoint_summary.get("label") or "").strip()
                if latest_checkpoint_summary
                else ""
            )
            stop_reason = (
                str(latest_checkpoint_summary.get("stopReason") or "").strip()
                if latest_checkpoint_summary
                else ""
            )
            verified_flags = (
                [
                    str(item).strip()
                    for item in list(latest_checkpoint_summary.get("verifiedFlags") or [])
                    if str(item).strip()
                ]
                if latest_checkpoint_summary
                else []
            )
            runtime_flags = (
                [
                    str(item).strip()
                    for item in list(latest_checkpoint_summary.get("runtimeFlags") or [])
                    if str(item).strip()
                ]
                if latest_checkpoint_summary
                else []
            )
            rejected_flags = (
                [
                    str(item).strip()
                    for item in list(latest_checkpoint_summary.get("rejectedFlags") or [])
                    if str(item).strip()
                ]
                if latest_checkpoint_summary
                else []
            )
            retracted_flags = (
                [
                    str(item).strip()
                    for item in list(
                        latest_checkpoint_summary.get("retractedFlags")
                        or latest_checkpoint_summary.get("rejectedFlags")
                        or []
                    )
                    if str(item).strip()
                ]
                if latest_checkpoint_summary
                else []
            )
            artifact_refs = [
                {
                    "artifactId": str(item.get("artifactId") or ""),
                    "kind": str(item.get("kind") or ""),
                    "title": str(item.get("title") or ""),
                    "location": item.get("location"),
                    "path": item.get("path"),
                }
                for item in list(context.get("artifacts") or [])
            ]
            trace_refs = (
                list(latest_checkpoint_summary.get("traceRefs") or [])
                if latest_checkpoint_summary
                else []
            )
            claim_evidence_refs = (
                list(latest_checkpoint_summary.get("claimEvidenceRefs") or [])
                if latest_checkpoint_summary
                else []
            )
            audit_evidence_export = (
                latest_checkpoint_summary.get("auditEvidenceExport")
                if latest_checkpoint_summary
                and isinstance(latest_checkpoint_summary.get("auditEvidenceExport"), dict)
                else None
            )
            p3_solve_snapshot = (
                latest_checkpoint_summary.get("p3SolveSnapshot")
                if latest_checkpoint_summary
                and isinstance(latest_checkpoint_summary.get("p3SolveSnapshot"), dict)
                else None
            )
            evidence_reasoning_context = (
                latest_checkpoint_summary.get("evidenceReasoningContext")
                if latest_checkpoint_summary
                and isinstance(
                    latest_checkpoint_summary.get("evidenceReasoningContext"),
                    dict,
                )
                else None
            )
            task_dag_plan_readback = (
                latest_checkpoint_summary.get("taskDagPlanReadback")
                if latest_checkpoint_summary
                and isinstance(
                    latest_checkpoint_summary.get("taskDagPlanReadback"),
                    dict,
                )
                else None
            )
            p3_solve_summary = (
                dict(p3_solve_snapshot.get("summary") or {})
                if p3_solve_snapshot
                else {}
            )
            evidence_reasoning_summary = (
                dict(evidence_reasoning_context.get("summary") or {})
                if evidence_reasoning_context
                else {}
            )
            task_dag_plan_summary = (
                dict(task_dag_plan_readback.get("summary") or {})
                if task_dag_plan_readback
                else {}
            )
            summary_parts = [f"run_id={normalized_run_id}"]
            if checkpoint_label:
                summary_parts.append(f"latest_checkpoint={checkpoint_label}")
            if stop_reason:
                summary_parts.append(f"stop_reason={stop_reason}")
            if verified_flags:
                summary_parts.append("verified_flags=" + ", ".join(verified_flags))
            if runtime_flags:
                summary_parts.append("runtime_flags=" + ", ".join(runtime_flags))
            if retracted_flags:
                summary_parts.append("retracted_flags=" + ", ".join(retracted_flags))
            if rejected_flags:
                summary_parts.append("rejected_flags=" + ", ".join(rejected_flags))
            if recent_event_types:
                summary_parts.append("recent_events=" + ", ".join(recent_event_types))
            artifact_titles = [
                str(item.get("title") or "").strip()
                for item in artifact_refs
                if str(item.get("title") or "").strip()
            ]
            if artifact_titles:
                summary_parts.append("artifacts=" + ", ".join(artifact_titles))
            evidence_summary = _format_claim_evidence_summary(claim_evidence_refs)
            if evidence_summary:
                summary_parts.append("claim_evidence=" + evidence_summary)
            p3_summary_text = _format_p3_solve_summary(p3_solve_summary)
            if p3_summary_text:
                summary_parts.append(p3_summary_text)
            task_dag_plan_text = _format_task_dag_plan_summary(task_dag_plan_summary)
            if task_dag_plan_text:
                summary_parts.append(task_dag_plan_text)
            evidence_reasoning_text = str(
                evidence_reasoning_summary.get("text") or ""
            ).strip()
            if evidence_reasoning_text:
                summary_parts.append(evidence_reasoning_text)
            context["resumeContext"] = {
                "runId": normalized_run_id,
                "checkpointId": (
                    str(latest_checkpoint_summary.get("checkpointId") or "").strip()
                    if latest_checkpoint_summary
                    else ""
                ),
                "checkpointLabel": checkpoint_label,
                "stopReason": stop_reason,
                "verifiedFlags": verified_flags,
                "runtimeFlags": runtime_flags,
                "rejectedFlags": rejected_flags,
                "retractedFlags": retracted_flags,
                "recentEventTypes": recent_event_types,
                "artifactRefs": artifact_refs,
                "summary": "; ".join(summary_parts),
            }
            if trace_refs:
                context["resumeContext"]["traceRefs"] = trace_refs
            if claim_evidence_refs:
                context["resumeContext"]["claimEvidenceRefs"] = claim_evidence_refs
            if audit_evidence_export:
                audit_summary = dict(audit_evidence_export.get("summary") or {})
                audit_summary["schemaVersion"] = str(
                    audit_evidence_export.get("schemaVersion") or ""
                )
                context["resumeContext"]["hasAuditEvidenceExport"] = True
                context["resumeContext"]["auditEvidenceSummary"] = audit_summary
            if p3_solve_summary:
                context["resumeContext"]["p3SolveSummary"] = p3_solve_summary
            if task_dag_plan_text:
                context["resumeContext"]["taskDagPlanSummary"] = {
                    "nodeCount": int(task_dag_plan_summary.get("nodeCount", 0) or 0),
                    "edgeCount": int(task_dag_plan_summary.get("edgeCount", 0) or 0),
                    "statusCounts": dict(task_dag_plan_summary.get("statusCounts") or {}),
                    "restoreWarningCount": int(
                        task_dag_plan_summary.get("restoreWarningCount", 0) or 0
                    ),
                }
            if evidence_reasoning_summary:
                context["resumeContext"]["hasEvidenceReasoningContext"] = True
                context["resumeContext"]["evidenceReasoningSummary"] = (
                    evidence_reasoning_summary
                )
            ledger_readback = build_p2_ledger_event_readback(
                list(context.get("recentEvents") or []),
                limit=10,
            )
            if ledger_readback["refs"]:
                context["resumeContext"]["ledgerEventRefs"] = ledger_readback["refs"]
                context["resumeContext"]["ledgerEventSummary"] = ledger_readback[
                    "summary"
                ]

        return context

    def build_blackboard_view(
        self,
        run_id: str,
        *,
        hints: list[str] | None = None,
        observation_limit: int = 12,
        intent_limit: int = 12,
    ) -> dict[str, Any]:
        """Project the latest checkpointed CTFState into a Fact/Intent/Hint view.

        Post-hoc / UI counterpart to the live projection (Workstream B): rebuilds
        state from the most recent checkpoint for ``run_id`` and runs
        ``project_blackboard``. Returns an empty board (hints preserved) when no
        checkpoint exists yet.
        """
        from .blackboard import project_blackboard

        normalized_hints = [str(h).strip() for h in (hints or []) if str(h or "").strip()]
        normalized_run_id = str(run_id or "").strip()
        latest_checkpoint = self._checkpoints.latest_checkpoint(normalized_run_id)
        if not latest_checkpoint:
            return {"facts": [], "intents": [], "hints": normalized_hints}
        state = CTFState.from_snapshot(dict(latest_checkpoint.get("state") or {}))
        return project_blackboard(
            state,
            hints=normalized_hints,
            observation_limit=observation_limit,
            intent_limit=intent_limit,
        )


def build_workspace_run_context(
    workspace_root: str | Path,
    run_id: str,
    *,
    event_limit: int = 20,
    artifact_limit: int = 20,
) -> dict[str, Any]:
    root = Path(workspace_root)
    view = SessionContextView(
        ledger_root=root / "loot" / "session_ledgers",
        artifact_root=[
            root / "loot" / "artifact_registry",
            root / "loot" / "artifacts",
        ],
        checkpoint_root=root / "loot" / "checkpoints",
    )
    return view.build_run_context(
        str(run_id or "").strip(),
        event_limit=event_limit,
        artifact_limit=artifact_limit,
    )
