"""Headless single-challenge CTF crew solve — shared across entry points.

CTF crew (CTFCrewCoordinator: multi-worker, shared CTFState, cancel-on-verified)
used to be reachable **only from the TUI** (`_run_ctf_crew_dispatcher_mode`),
which wraps it in a platform-autonomy multi-challenge loop and the sidebar UI.
CLI and web could only run the single-worker `CTFTaskDispatcher`.

This module extracts the per-challenge crew *core* into a headless, UI-agnostic
helper so CLI and web can run a CTF challenge through the crew coordinator too
(D4 — capability parity). Progress is a plain ``str`` callback; worker lifecycle
is an optional ``(worker_id, event, data)`` callback (no-op by default), so the
TUI's sidebar updates can ride on the same helper without this module importing
any interface code.

It deliberately does **not** include the TUI's platform-autonomy loop
(queue/switch/drain across challenges) — that stays in the TUI. This is the
single-challenge unit CLI/web need; the autonomy loop can call it per challenge.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from .ctf_state import CTFState

#: ``(worker_id, event, data)`` — event ∈ {"spawn","running","complete","cancelled","error"}.
WorkerEvent = Callable[[str, str, dict[str, Any]], None]


def derive_crew_stop_reason(summary: Any) -> str:
    """Normalize a ``CrewRunSummary`` into a canonical stop reason.

    Single source of truth for the crew stop-reason mapping (the TUI delegates
    here). Pure: depends only on ``summary``.
    """
    base_reason = str(getattr(summary, "stop_reason", "") or "").strip()
    if base_reason in {"flag_verified", "crew_timeout"} or base_reason.startswith("worker_error:"):
        return base_reason

    worker_results = dict(getattr(summary, "worker_results", {}) or {})
    reasons = [
        str(item.get("reason") or "").strip().lower()
        for item in worker_results.values()
        if isinstance(item, dict)
    ]
    missing_tools = [
        tool
        for item in worker_results.values()
        if isinstance(item, dict)
        for tool in list(item.get("missing_tools") or [])
    ]
    if any("wrong flag feedback" in reason for reason in reasons):
        return "wrong_flag_feedback"
    if any("already solved" in reason for reason in reasons):
        return "challenge_already_solved"
    if missing_tools or any(
        token in reason
        for reason in reasons
        for token in ("capability_ceiling", "侦察依赖缺失", "missing tool", "missing_tools")
    ):
        return "capability_ceiling"
    if base_reason == "workers_completed":
        return "all_hypotheses_exhausted"
    return base_reason or "workers_completed"


async def run_ctf_crew_solve(
    *,
    runtime: Any,
    llm: Any,
    target: str,
    goal: str,
    chtype: str = "auto",
    hint: str = "",
    submit_profile: dict[str, Any] | None = None,
    challenge_context: dict[str, Any] | None = None,
    progress_callback: Callable[[str], None] | None = None,
    worker_event: WorkerEvent | None = None,
    profile: str = "ctf",
) -> tuple[Any, Any]:
    """Run ONE CTF challenge through ``CTFCrewCoordinator``; return (SolveResult, dispatcher).

    Mirrors the per-challenge core of the TUI crew path but headless — no
    sidebar, no platform-autonomy loop. The second element is the planning
    ``CTFTaskDispatcher`` (exposes ``.state`` for chains/notes/stop_report and
    ``._challenge_context`` for derived-target sync), so every entry point gets
    what it needs from the one returned artifact.
    """
    from ..crew.swarm_bridge import run_ctf_dispatcher_worker
    from .ctf_crew_coordinator import CTFCrewCoordinator
    from .ctf_dispatcher import CTFTaskDispatcher, SolveResult
    from .ctf_planner import detect_type

    emit = progress_callback or (lambda _message: None)
    notify_worker = worker_event or (lambda _worker_id, _event, _data: None)

    planning_dispatcher = CTFTaskDispatcher(
        runtime=runtime,
        progress_callback=emit,
        llm=llm,
        profile=profile,
    )
    planning_dispatcher.state = CTFState(target=target, goal=goal)
    planning_dispatcher.state.apply_profile(planning_dispatcher.profile)  # P5
    submit = dict(submit_profile or {})
    if submit:
        planning_dispatcher._apply_submit_profile(submit)
    if isinstance(challenge_context, dict):
        planning_dispatcher._challenge_context = challenge_context

    requested_type = str(chtype or "auto").strip().lower() or "auto"

    await planning_dispatcher._snapshot_platform_context(target)
    await planning_dispatcher.capability_registry.full_check()
    planning_dispatcher.state.capabilities = planning_dispatcher.capability_registry.to_dict()

    page_features = await planning_dispatcher._phase_recon(target)
    alignment = planning_dispatcher._align_platform_challenge(target, page_features)
    if alignment is not None and planning_dispatcher.state is not None:
        planning_dispatcher.state.meta_reasonings.append(
            {"type": "platform_challenge_alignment", **alignment}
        )
        aligned_id = str(alignment.get("challenge_id") or "").strip()
        if aligned_id and not planning_dispatcher.state.submit_challenge_id:
            planning_dispatcher.state.submit_challenge_id = aligned_id

    if bool(alignment and alignment.get("already_solved") is True):
        stop_reason = "challenge_already_solved"
        planning_dispatcher.state.stop_reason = stop_reason
        planning_dispatcher.reasoning_layer.generate_stop_report(
            planning_dispatcher.state, reason=stop_reason, missing_capabilities=[]
        )
        return (
            SolveResult(
                success=False,
                flag=None,
                chain_used=[],
                notes=[],
                missing_tools=[],
                reason=planning_dispatcher._build_already_solved_reason(),
            ),
            planning_dispatcher,
        )

    detected_type = (
        requested_type
        if requested_type not in {"", "auto"}
        else detect_type(
            f"{page_features.get('html', '')}\n{page_features.get('content', '')}",
            target,
        )
    )
    planning_dispatcher.state.detected_type = detected_type
    planning_dispatcher.hypothesis_engine.generate(planning_dispatcher.state)

    async def _worker_runner(
        spec: dict[str, Any],
        shared_state: Any,
        cancel_event: asyncio.Event,
    ) -> dict[str, Any]:
        worker_id = str(spec.get("worker_id") or "worker")
        worker_type = str(spec.get("worker_type") or "worker")
        metadata = dict(spec.get("metadata") or {})
        target_filter = str(spec.get("target_filter") or "").strip()
        notify_worker(worker_id, "running", {})

        hint_blocks = [str(hint or "").strip()]
        if worker_type == "recon" and target_filter:
            hint_blocks.append(
                f"[Crew directive]\nFocus recon on namespace `{target_filter}` and nearby endpoints first."
            )
        hypothesis_kind = str(metadata.get("hypothesis_kind") or "").strip()
        if hypothesis_kind:
            hint_blocks.append(
                f"[Crew directive]\nPrioritize hypothesis `{hypothesis_kind}`. Only pivot when this branch is exhausted."
            )
        if worker_type == "llm_explorer":
            hint_blocks.append(
                "[Crew directive]\nExplore the unknown surface and produce at least one new actionable observation."
            )
        worker_hint = "\n\n".join(block for block in hint_blocks if block)

        worker_dispatcher = CTFTaskDispatcher(
            runtime=runtime,
            progress_callback=lambda message, wid=worker_id: emit(f"[CTF crew:{wid}] {message}"),
            llm=llm,
            profile=profile,
        )
        try:
            result = await run_ctf_dispatcher_worker(
                worker_dispatcher,
                target=target,
                goal=goal,
                chtype=detected_type,
                hint=worker_hint,
                submit_profile=dict(submit or {}),
                worker_id=worker_id,
                worker_type=worker_type,
                cancel_event=cancel_event,
            )
        except asyncio.CancelledError:
            notify_worker(worker_id, "cancelled", {})
            raise
        except Exception:
            notify_worker(worker_id, "error", {})
            raise

        state_diff = dict(result.get("state_diff") or {})
        findings_count = len(list(result.get("candidate_flags") or []))
        findings_count += len(list(state_diff.get("runtime_flags") or []))
        if result.get("verified_flag"):
            findings_count += 1
        notify_worker(
            worker_id,
            "complete" if not result.get("cancelled") else "cancelled",
            {"findings": findings_count},
        )
        return result

    coordinator = CTFCrewCoordinator(
        state=planning_dispatcher.state,
        verifier=planning_dispatcher.verifier,
        worker_runner=_worker_runner,
        progress_callback=emit,
    )
    for spec in coordinator.build_worker_specs(target=target, page_features=page_features):
        notify_worker(spec.worker_id, "spawn", {"worker_type": spec.worker_type, "task": spec.task})

    summary = await coordinator.run_with_shadow_graph(target=target, page_features=page_features)
    stop_reason = derive_crew_stop_reason(summary)
    coordinator.state.stop_reason = stop_reason
    planning_dispatcher.reasoning_layer.generate_stop_report(
        coordinator.state, reason=stop_reason, missing_capabilities=[]
    )
    missing_tools = sorted(
        {
            tool
            for item in summary.worker_results.values()
            for tool in list(item.get("missing_tools") or [])
        }
    )
    return (
        SolveResult(
            success=bool(summary.verified_flag),
            flag=summary.verified_flag,
            chain_used=[worker_id for worker_id in summary.started_workers],
            notes=[],
            missing_tools=missing_tools,
            reason=stop_reason,
        ),
        planning_dispatcher,
    )


__all__ = ["run_ctf_crew_solve", "derive_crew_stop_reason", "WorkerEvent"]
