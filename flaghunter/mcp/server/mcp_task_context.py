"""TaskEntry context extractors for the MCP server tools.

Fourth physical-split slice extracted from the ~2094-line ``mcp_tools`` god-module,
same behavior-preserving pattern as ``mcp_task_presentation`` / ``mcp_task_contracts``
/ ``mcp_model_readiness``: move a cohesive, down-closed, unpatched leaf cluster to a
sibling and re-import it into the ``mcp_tools`` namespace.

These two functions derive read-only context dicts from a ``TaskEntry`` — the local
challenge/resume contract (``_entry_challenge_context``) and the workspace run
context reconstructed from ledger/checkpoint paths (``_entry_session_context``).
They call no other ``mcp_tools`` function, touch no module state, and are not part
of the test monkeypatch surface (verified against every ``setattr(mcp_tools, ...)``
target). Their many callers stay in ``mcp_tools`` and resolve these names via
re-import — including the patched task-driving helpers (``_drive_task``,
``_ctf_dispatcher_hint``, ``_build_ingress_handoff``, ``_sync_runtime_challenge_context``,
``_append_blackboard_snapshot_lines``) and the decorated ``get_task_status`` /
``get_task_result`` tools. ``TaskEntry`` is a lazy annotation only
(``from __future__ import annotations`` active in both modules), imported under
``TYPE_CHECKING`` — no runtime ``mcp_tools`` import, no cycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mcp_tools import TaskEntry


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
