"""Task-entry contract/normalization helpers for the MCP server tools.

Second physical-split slice extracted from the ~2094-line ``mcp_tools`` god-module,
same behavior-preserving pattern as ``mcp_task_presentation``: move a cohesive,
down-closed, unpatched leaf cluster to a sibling and re-import it into the
``mcp_tools`` namespace.

These five functions normalize request args and apply them onto a ``TaskEntry`` at
task setup (resume contract, local-asset contract, blocked-status marking, CTF
run-artifact path assignment, and the shared string-list normalizer). They call no
other ``mcp_tools`` function (except each other), touch no module state, and are
not part of the test monkeypatch surface. Their callers — the decorated
``run_task``/``run_task_async`` tools and the (patched) ``_ctf_dispatcher_hint``/
``_sync_runtime_challenge_context`` helpers — all stay in ``mcp_tools`` and resolve
these names via re-import.

Deliberately NOT moved: ``_resolve_target_scope`` (reads ``_primary_agent`` module
state → would need mutable ``mcp_tools`` state, a cycle) and
``_resolve_ingress_mode_contract`` (calls ``resolve_mode_contract``, which tests
monkeypatch in the ``mcp_tools`` namespace — moving it would silently break that
patch, the from-import rebind trap). ``TaskEntry`` is a lazy annotation only
(``from __future__ import annotations`` active in both modules), imported under
``TYPE_CHECKING`` — no runtime ``mcp_tools`` import, no cycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mcp_tools import TaskEntry


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
