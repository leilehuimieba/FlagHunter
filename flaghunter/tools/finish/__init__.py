"""Task completion tool for FlagHunter agent loop control."""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ...agents.pa_agent.control_receipts import record_completion_control_receipt
from ..registry import Tool as Tool
from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime
    from ..planning import TaskPlan

# Sentinel value to signal task completion
TASK_COMPLETE_SIGNAL = "__TASK_COMPLETE__"


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    SKIP = "skip"
    FAIL = "fail"


@dataclass
class PlanStep:
    id: int
    description: str
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlanStep":
        return cls(
            id=data.get("id", 0),
            description=data.get("description", ""),
            status=StepStatus(data.get("status", "pending")),
            result=data.get("result"),
        )


@dataclass
class TaskPlan:
    steps: list[PlanStep] = field(default_factory=list)
    original_request: str = ""

    def is_complete(self) -> bool:
        return all(
            s.status in (StepStatus.COMPLETE, StepStatus.SKIP) for s in self.steps
        )

    def has_failure(self) -> bool:
        return any(s.status == StepStatus.FAIL for s in self.steps)

    def clear(self) -> None:
        self.steps.clear()
        self.original_request = ""

    def get_current_step(self) -> Optional[PlanStep]:
        for s in self.steps:
            if s.status == StepStatus.PENDING:
                return s
        return None

    def get_pending_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == StepStatus.PENDING]


def _resolve_finish_target(runtime: "Runtime") -> str:
    """Resolve the most relevant target for session knowledge persistence."""
    target = getattr(runtime, "target", None)
    if isinstance(target, str) and target.strip():
        return target.strip()

    try:
        from ...workspaces.manager import WorkspaceManager

        wm = WorkspaceManager()
        active = wm.get_active()
        if active:
            last_target = wm.get_meta_field(active, "last_target")
            if isinstance(last_target, str) and last_target.strip():
                return last_target.strip()
    except Exception:
        pass

    return ""


async def _persist_session_knowledge(runtime: "Runtime") -> None:
    """Write high-value notes into the session knowledge store."""
    try:
        from ...knowledge.session_writer import write_session_to_knowledge
        from ..notes import get_all_notes_sync

        target = _resolve_finish_target(runtime)
        await write_session_to_knowledge(target=target, notes=get_all_notes_sync())
    except Exception as exc:
        logging.getLogger(__name__).exception(
            "Failed to persist session knowledge during finish: %s", exc
        )


async def _generate_auto_report(runtime: "Runtime") -> str | None:
    """Generate an HTML auto-report from accumulated notes."""
    if not (os.getenv("CPA_M3_REPORTER", "true").lower() != "false"):
        return None

    try:
        try:
            from flaghunter.cpa_modules.m3_reporter import get_report_generator, is_m3_enabled
            from flaghunter.cpa_modules.m3_reporter.report_models import ReportMeta
            from ..notes import get_all_notes_sync
        except Exception:
            return None

        if not is_m3_enabled():
            return None

        logger = logging.getLogger(__name__)
        target = _resolve_finish_target(runtime)
        report_target = target or "unknown-target"
        now = datetime.now()
        title_timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

        gen = get_report_generator()
        gen.create_report(
            meta=ReportMeta(
                title=f"Auto Report: {report_target} - {title_timestamp}",
                author="FlagHunter",
                start_date=now,
                end_date=now,
                scope=report_target,
            )
        )

        notes = get_all_notes_sync()
        vuln_severity_map = {
            "high": "high",
            "medium": "medium",
            "low": "low",
        }

        for key, note in notes.items():
            category = note.get("category")
            content = str(note.get("content", ""))
            confidence = str(note.get("confidence", "medium")).lower()
            note_metadata = note.get("metadata") or {}
            note_target = note_metadata.get("target") or target or report_target

            if category == "vulnerability":
                severity = vuln_severity_map.get(confidence, "medium")
            elif category == "credential":
                severity = "critical"
            elif category == "finding":
                severity = "info"
            else:
                continue

            gen.add_finding(
                title=key,
                severity=severity,
                description=content,
                target=note_target,
            )

        gen.finalize_report()
        html_path = gen.export_html()
        logger.info("Auto report: %s", html_path)

        # Save report path to notes for easy retrieval
        try:
            from ..notes import notes as _notes_tool

            await _notes_tool(
                {
                    "action": "create",
                    "key": f"auto_report_{report_target}",
                    "value": str(html_path),
                    "category": "artifact",
                    "source": "m3_reporter",
                },
                runtime,
            )
        except Exception:
            pass
        return str(html_path)
    except Exception as e:
        logging.getLogger(__name__).warning("Auto-report failed: %s", e, exc_info=True)
        try:
            from flaghunter.session.notifier import notify

            notify("warning", f"Auto-report failed: {e}")
        except Exception:
            pass
    return None


def _runtime_ctf_state(runtime: "Runtime") -> Any | None:
    return getattr(runtime, "ctf_state", None) or getattr(runtime, "state", None)


def _record_finish_control_receipt(
    runtime: "Runtime",
    *,
    action: str,
    step_id: Any = None,
    mode: str = "single",
    success: bool,
    stop_reason: str,
    finish_status: str = "",
    output_summary: str = "",
) -> None:
    state = _runtime_ctf_state(runtime)
    if state is None:
        return
    try:
        record_completion_control_receipt(
            state,
            producer="control:finish",
            success=success,
            stop_reason=stop_reason,
            finish_status=finish_status,
            input_summary=(
                f"mode={mode} action={action or ''} step_id={step_id or ''}".strip()
            ),
            output_summary=output_summary,
            answer_kind="plan_completion",
            source_channel="finish_tool",
        )
    except Exception:
        logging.getLogger(__name__).debug(
            "Failed to record finish control receipt", exc_info=True
        )


def _record_report_control_receipt(
    runtime: "Runtime",
    *,
    html_path: str | None,
    success: bool,
    stop_reason: str,
) -> None:
    state = _runtime_ctf_state(runtime)
    if state is None:
        return
    try:
        artifact_refs = [html_path] if html_path else []
        record_completion_control_receipt(
            state,
            producer="control:report",
            success=success,
            stop_reason=stop_reason,
            finish_status="answered" if success else "attempted",
            input_summary="auto_report",
            output_summary="auto report generated" if success else "auto report unavailable",
            artifact_refs=artifact_refs,
            answer_kind="auto_report",
            source_channel="m3_reporter",
        )
    except Exception:
        logging.getLogger(__name__).debug(
            "Failed to record report control receipt", exc_info=True
        )


def _process_single_finish(plan, action: str, step_id, result: str = "", reason: str = "") -> tuple[str, bool]:
    """Process a single finish action. Returns (message, is_fail)."""
    step = next((s for s in plan.steps if s.id == step_id), None)
    if not step:
        valid_ids = [s.id for s in plan.steps]
        return f"Error: Step {step_id} not found. Valid IDs: {valid_ids}", False

    if action == "complete":
        step.status = StepStatus.COMPLETE
        step.result = result
        lines = [f"Step {step_id} complete"]
        if result:
            lines.append(f"Result: {result}")
        return "\n".join(lines), False

    elif action == "skip":
        if not reason:
            return "Error: 'reason' required for skip action.", False
        step.status = StepStatus.SKIP
        step.result = f"Skipped: {reason}"
        return f"Step {step_id} skipped: {reason}", False

    elif action == "fail":
        if not reason:
            return "Error: 'reason' required for fail action.", False
        step.status = StepStatus.FAIL
        step.result = f"Failed: {reason}"
        return f"Step {step_id} marked as FAILED: {reason}. Initiating replanning...", True

    return f"Error: Unknown action '{action}'. Use 'complete', 'skip', or 'fail'.", False


@register_tool(
    name="finish",
    description=(
        "Mark plan steps as complete, skipped, or failed. "
        "Supports two modes: (1) single-step via action+step_id, "
        "(2) batch via 'steps' array. "
        "Actions: 'complete' (mark step done), 'skip' (step not applicable), "
        "'fail' (step failed, invalidating plan). "
        "Once all steps are complete/skipped, task automatically finishes."
    ),
    schema=ToolSchema(
        properties={
            "action": {
                "type": "string",
                "enum": ["complete", "skip", "fail"],
                "description": "Action for single-step mode",
            },
            "step_id": {
                "type": "integer",
                "description": "Step number (1-indexed) for single-step mode",
            },
            "result": {
                "type": "string",
                "description": "[complete only] What was accomplished",
            },
            "reason": {
                "type": "string",
                "description": "[skip/fail only] Why step is being skipped or failed",
            },
            "steps": {
                "type": "array",
                "description": "Batch mode: array of {action, step_id, result?, reason?}",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["complete", "skip", "fail"]},
                        "step_id": {"type": "integer"},
                        "result": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["action", "step_id"],
                },
            },
        },
        required=[],
    ),
    category="workflow",
)
async def finish(arguments: dict, runtime: "Runtime") -> str:
    """Mark plan steps as complete or skipped. Accesses plan via runtime.plan."""
    plan = getattr(runtime, "plan", None)
    if plan is None or len(plan.steps) == 0:
        return "No active plan."

    # Batch mode via steps array
    batch_steps = arguments.get("steps")
    if batch_steps and isinstance(batch_steps, list):
        messages: list[str] = []
        has_fail = False
        for item in batch_steps:
            action = item.get("action", "")
            step_id = item.get("step_id")
            result = item.get("result", "")
            reason = item.get("reason", "")
            msg, is_fail = _process_single_finish(plan, action, step_id, result, reason)
            messages.append(msg)
            if is_fail:
                has_fail = True

        # After batch processing, check completion
        if plan.is_complete() and not has_fail:
            await _persist_session_knowledge(runtime)
            html_path = await _generate_auto_report(runtime)
            if html_path:
                _record_report_control_receipt(
                    runtime,
                    html_path=html_path,
                    success=True,
                    stop_reason="all_steps_complete",
                )
            _record_finish_control_receipt(
                runtime,
                action="batch",
                mode="batch",
                success=True,
                stop_reason="all_steps_complete",
                output_summary="All steps complete",
            )
            messages.append("All steps complete")
        elif not has_fail:
            next_step = plan.get_current_step()
            if next_step:
                messages.append(f"Next: Step {next_step.id}")

        return "\n".join(messages)

    # Legacy single-step mode
    action = arguments.get("action", "")
    step_id = arguments.get("step_id")
    result = arguments.get("result", "")
    reason = arguments.get("reason", "")

    msg, is_fail = _process_single_finish(plan, action, step_id, result, reason)

    if "Error:" in msg:
        return msg

    if action == "complete":
        if plan.is_complete():
            await _persist_session_knowledge(runtime)
            html_path = await _generate_auto_report(runtime)
            if html_path:
                _record_report_control_receipt(
                    runtime,
                    html_path=html_path,
                    success=True,
                    stop_reason="all_steps_complete",
                )
            _record_finish_control_receipt(
                runtime,
                action=action,
                step_id=step_id,
                success=True,
                stop_reason="all_steps_complete",
                output_summary="All steps complete",
            )
            msg += "\nAll steps complete"
        else:
            next_step = plan.get_current_step()
            if next_step:
                msg += f"\nNext: Step {next_step.id}"

    elif action == "skip":
        if plan.is_complete():
            await _persist_session_knowledge(runtime)
            html_path = await _generate_auto_report(runtime)
            if html_path:
                _record_report_control_receipt(
                    runtime,
                    html_path=html_path,
                    success=True,
                    stop_reason="all_steps_complete",
                )
            _record_finish_control_receipt(
                runtime,
                action=action,
                step_id=step_id,
                success=True,
                stop_reason="all_steps_complete",
                output_summary="All steps complete",
            )

    return msg


class CompletionReport:
    """Structured completion report for task results."""

    def __init__(
        self,
        status: str = "success",
        summary: str = "",
        findings: Optional[List[str]] = None,
        artifacts: Optional[List[str]] = None,
        recommendations: Optional[List[str]] = None,
    ):
        self.status = status
        self.summary = summary
        self.findings = findings or []
        self.artifacts = artifacts or []
        self.recommendations = recommendations or []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status,
            "summary": self.summary,
            "findings": self.findings,
            "artifacts": self.artifacts,
            "recommendations": self.recommendations,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "CompletionReport":
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls(**data)

    def format_display(self) -> str:
        """Format for human-readable display."""
        lines = []

        # Status indicator
        status_icons = {"success": "✓", "partial": "◐", "failed": "✗"}
        icon = status_icons.get(self.status, "•")
        lines.append(f"{icon} Status: {self.status.upper()}")
        lines.append("")

        # Summary
        lines.append(f"Summary: {self.summary}")

        # Findings
        if self.findings:
            lines.append("")
            lines.append("Findings:")
            for finding in self.findings:
                lines.append(f"  • {finding}")

        # Artifacts
        if self.artifacts:
            lines.append("")
            lines.append("Artifacts:")
            for artifact in self.artifacts:
                lines.append(f"  📄 {artifact}")

        # Recommendations
        if self.recommendations:
            lines.append("")
            lines.append("Recommendations:")
            for rec in self.recommendations:
                lines.append(f"  → {rec}")

        return "\n".join(lines)


def is_task_complete(result: str) -> bool:
    """Check if a tool result signals task completion."""
    return result.startswith(TASK_COMPLETE_SIGNAL)


def extract_completion_summary(result: str) -> str:
    """Extract the summary from a task_complete result (legacy support)."""
    if is_task_complete(result):
        data = result[len(TASK_COMPLETE_SIGNAL) + 1 :]  # +1 for the colon
        # Try to parse as JSON for new format
        try:
            report = CompletionReport.from_json(data)
            return report.summary
        except (json.JSONDecodeError, TypeError):
            # Fall back to raw string for legacy format
            return data
    return result


def extract_completion_report(result: str) -> Optional[CompletionReport]:
    """Extract the full structured report from a task_complete result."""
    if is_task_complete(result):
        data = result[len(TASK_COMPLETE_SIGNAL) + 1 :]
        try:
            return CompletionReport.from_json(data)
        except (json.JSONDecodeError, TypeError):
            # Legacy format - wrap in report
            return CompletionReport(status="success", summary=data)
    return None
