"""CTF dispatcher / crew run-loops + platform switch helpers mixed into FlagHunterTUI (债池五波·TUI 刀 17, god-class).

Extracted from tui.py. The two ``@work`` autonomous CTF run-loops —
``_run_ctf_dispatcher_mode`` (single dispatcher) and ``_run_ctf_crew_dispatcher_mode``
(crew swarm) — plus their platform-switch helpers: crew stop-reason derivation,
auto-switch context resolution / decision, next-queue-url resolution, switch-context
carry-forward, and platform run-meta writer. Members call each other plus stay-behind
helpers (``self._add_*`` / ``_render_last_ctf_*`` / ``_start_ctf_execution``) resolved
at runtime through the FlagHunterTUI instance MRO; the ``@work`` decorator is scanned
off this mixin's MRO entry at class creation. Module-level deps: ``asyncio`` / ``time``
/ ``Any`` / ``work`` / ``urllib.parse`` helpers; all CTF/platform backends are lazy
inside the bodies.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from textual import work


class CtfRunnerMixin:
    """CTF dispatcher / crew run-loops + platform-switch helpers for FlagHunterTUI."""

    @work(thread=False)
    async def _run_ctf_dispatcher_mode(
        self,
        url: str,
        goal: str,
        chtype: str,
        hint: str,
        submit_profile: dict[str, Any] | None = None,
        runner_config: dict[str, Any] | None = None,
    ) -> None:
        """Run the deterministic CTF dispatcher instead of the generic agent loop."""
        runtime = self.runtime or getattr(self.agent, "runtime", None)
        if runtime is None:
            self._add_system("[!] Runtime not ready")
            return

        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", "agent")

        try:
            from ..agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
            from ..agents.pa_agent.platform_runner import (
                PlatformAutonomyRunner,
                PlatformRunConfig,
            )

            current_url = url
            current_goal = goal
            current_type = chtype
            current_hint = hint
            current_submit_profile = dict(submit_profile or {})
            raw_runner_config = dict(runner_config or {})
            resume_autonomy_state = raw_runner_config.pop("_autonomy_resume_state", None)
            resume_reason = str(raw_runner_config.pop("_autonomy_resume_reason", "") or "").strip()
            run_mode = str(raw_runner_config.get("mode") or "switch").strip().lower()
            if run_mode not in {"single", "switch", "drain"}:
                run_mode = "switch"
            normalized_runner_config = {
                "mode": run_mode,
                "max_challenges": max(
                    1, int(raw_runner_config.get("max_challenges") or 4)
                ),
                "timebox_seconds": max(
                    1, int(raw_runner_config.get("timebox_seconds") or 900)
                ),
                "max_consecutive_stops": max(
                    1, int(raw_runner_config.get("max_consecutive_stops") or 2)
                ),
            }
            runner = PlatformAutonomyRunner()
            auto_switch_depth = 0
            initial_key = (
                f"{str(current_submit_profile.get('challenge_id') or '').strip()}|{current_url}"
            )
            runtime_config = PlatformRunConfig(**normalized_runner_config)
            if isinstance(resume_autonomy_state, dict):
                autonomy_state = runner.restore(
                    resume_autonomy_state,
                    config=runtime_config,
                    initial_visit_key=initial_key.strip("|"),
                    resume_reason=resume_reason or "resume",
                )
            else:
                autonomy_state = runner.start(
                    runtime_config,
                    initial_visit_key=initial_key.strip("|"),
                )
            autonomy_end_reason = "not_started"

            while True:
                challenge_started_at = time.time()
                dispatcher = CTFTaskDispatcher(
                    runtime=runtime,
                    progress_callback=self._add_system,
                    llm=getattr(self.agent, "llm", None),
                )
                self._last_ctf_dispatcher = dispatcher
                solve_result = await dispatcher.run(
                    target=current_url,
                    goal=current_goal,
                    type=current_type,
                    hint=current_hint,
                    submit_profile=current_submit_profile,
                )
                self._last_ctf_result = solve_result
                self._last_ctf_state = (
                    dispatcher.state.to_dict() if dispatcher.state is not None else None
                )
                current_state = self._last_ctf_state or {}
                stop_report = (
                    current_state.get("stop_report")
                    if isinstance(current_state, dict)
                    else {}
                ) or {}
                stop_reason = str(
                    stop_report.get("reason")
                    or current_state.get("stop_reason")
                    or solve_result.reason
                    or ""
                )
                current_profile = None
                if isinstance(current_state, dict):
                    for item in reversed(current_state.get("meta_reasonings") or []):
                        if (
                            isinstance(item, dict)
                            and item.get("type") == "platform_profile_snapshot"
                        ):
                            current_profile = item
                            break
                current_challenge_id = str(
                    (current_profile or {}).get("challenge_id")
                    or current_submit_profile.get("challenge_id")
                    or ""
                ).strip()
                current_challenge_name = str(
                    (current_profile or {}).get("challenge_name")
                    or (current_profile or {}).get("name")
                    or ""
                ).strip()
                if not current_challenge_name and isinstance(current_state, dict):
                    for item in reversed(current_state.get("meta_reasonings") or []):
                        if (
                            isinstance(item, dict)
                            and item.get("type") == "platform_challenge_alignment"
                        ):
                            current_challenge_name = str(
                                item.get("challenge_name") or ""
                            ).strip()
                            if current_challenge_name:
                                break
                runner.record_result(
                    autonomy_state,
                    challenge_id=current_challenge_id,
                    challenge_name=current_challenge_name,
                    url=current_url,
                    result=solve_result,
                    stop_reason=stop_reason,
                    started_at=challenge_started_at,
                    ended_at=time.time(),
                )
                queue_snapshot = None
                if isinstance(current_state, dict):
                    for item in reversed(current_state.get("meta_reasonings") or []):
                        if (
                            isinstance(item, dict)
                            and item.get("type") == "platform_task_queue_snapshot"
                        ):
                            queue_snapshot = item
                            break
                    self._last_ctf_state = self._write_platform_run_meta(
                        current_state,
                        autonomy_state=autonomy_state,
                        autonomy_end_reason=autonomy_end_reason,
                    )

                if solve_result.success:
                    self._add_system(
                        "\n".join(
                            [
                                "[CTF dispatcher] success",
                                f"flag: {solve_result.flag}",
                                f"chain_used: {solve_result.chain_used}",
                                f"reason: {solve_result.reason}",
                            ]
                        )
                    )
                    if dispatcher.state is not None and dispatcher.state.stop_report:
                        self._add_system(self._render_last_ctf_stop_report())
                        self._add_system(self._render_last_ctf_reasoning())
                        self._show_ctf_memory_panel()
                    self._set_status("complete", "agent")
                else:
                    lines = [
                        "[CTF dispatcher] stopped",
                        f"chain_used: {solve_result.chain_used}",
                        f"reason: {solve_result.reason}",
                    ]
                    if solve_result.missing_tools:
                        lines.append(
                            "missing_tools: " + ", ".join(solve_result.missing_tools)
                        )
                    self._add_system("\n".join(lines))
                    if dispatcher.state is not None and dispatcher.state.stop_report:
                        self._add_system(self._render_last_ctf_stop_report())
                        self._add_system(self._render_last_ctf_reasoning())
                        self._show_ctf_memory_panel()

                should_continue, autonomy_end_reason = runner.should_continue(
                    autonomy_state,
                    operator_stop=bool(getattr(self, "_should_stop", False)),
                    queue_snapshot=queue_snapshot,
                )
                if not should_continue:
                    break

                next_ctx = self._resolve_ctf_auto_switch_context(
                    result=solve_result,
                    current_url=current_url,
                    current_goal=current_goal,
                    current_type=current_type,
                    current_hint=current_hint,
                    current_submit_profile=current_submit_profile,
                    auto_switch_depth=auto_switch_depth,
                    visited_keys=autonomy_state.visited_keys,
                )
                if next_ctx is None:
                    autonomy_end_reason = "queue_switch_unavailable"
                    break

                autonomy_end_reason = "continue"
                runner.mark_switch(
                    autonomy_state,
                    str(next_ctx.get("visit_key") or ""),
                    reason=str(next_ctx.get("switch_reason") or ""),
                    source=str(next_ctx.get("switch_source") or "platform_queue"),
                )
                auto_switch_depth += 1
                current_url = str(next_ctx["url"])
                current_goal = str(next_ctx["goal"])
                current_type = str(next_ctx["type"])
                current_hint = str(next_ctx["hint"])
                current_submit_profile = dict(next_ctx.get("submit_profile") or {})
                if isinstance(self._last_ctf_state, dict):
                    meta_reasonings = list(self._last_ctf_state.get("meta_reasonings") or [])
                    meta_reasonings.append(
                        {
                            "type": "platform_queue_switch_decision",
                            "switch_reason": str(next_ctx.get("switch_reason") or ""),
                            "switch_source": str(next_ctx.get("switch_source") or "platform_queue"),
                            "skipped_candidates": list(next_ctx.get("skipped_candidates") or []),
                            "next_challenge_id": str(current_submit_profile.get("challenge_id") or ""),
                            "next_url": current_url,
                        }
                    )
                    self._last_ctf_state["meta_reasonings"] = meta_reasonings
                self._last_ctf_context = {
                    "url": current_url,
                    "goal": current_goal,
                    "type": current_type,
                    "hint": current_hint,
                    "submit_profile": dict(current_submit_profile),
                    "runner_config": dict(normalized_runner_config),
                    "execution_mode": "dispatcher",
                    "switch_reason": str(next_ctx.get("switch_reason") or ""),
                    "switch_source": str(next_ctx.get("switch_source") or "platform_queue"),
                    "skipped_candidates": list(next_ctx.get("skipped_candidates") or []),
                    "auto_switch_depth": auto_switch_depth,
                    "visited_queue_keys": sorted(
                        key for key in autonomy_state.visited_keys if key
                    ),
                    "autonomy_state": autonomy_state.to_dict(),
                }
                self._add_system(
                    "\n".join(
                        [
                            "[CTF queue] auto-switch engaged",
                            f"next_url: {current_url}",
                            f"next_challenge_id: {current_submit_profile.get('challenge_id', '')}",
                            f"depth: {auto_switch_depth}",
                            f"switch_reason: {next_ctx.get('switch_reason', '')}",
                            f"runner_mode: {normalized_runner_config['mode']}",
                        ]
                    )
                )

            if isinstance(self._last_ctf_state, dict):
                current_state = self._last_ctf_state
                self._last_ctf_state = self._write_platform_run_meta(
                    current_state,
                    autonomy_state=autonomy_state,
                    autonomy_end_reason=autonomy_end_reason,
                )

            if self._last_ctf_context:
                self._last_ctf_context["runner_config"] = dict(normalized_runner_config)
                self._last_ctf_context["autonomy_state"] = autonomy_state.to_dict()
                self._last_ctf_context["autonomy_end_reason"] = autonomy_end_reason
                self._last_ctf_context["execution_mode"] = str(
                    self._last_ctf_context.get("execution_mode") or "dispatcher"
                )

            await asyncio.sleep(1)
            self._set_status("idle", "assist")
        except asyncio.CancelledError:
            self._add_system("[!] Cancelled")
            self._set_status("idle", "assist")
        except Exception as e:
            self._add_system(f"[!] CTF dispatcher error: {e}")
            self._set_status("error")
        finally:
            await self._save_current_conversation()
            self._is_running = False

    @work(thread=False)
    async def _run_ctf_crew_dispatcher_mode(
        self,
        url: str,
        goal: str,
        chtype: str,
        hint: str,
        submit_profile: dict[str, Any] | None = None,
        runner_config: dict[str, Any] | None = None,
    ) -> None:
        """Run the CTF dispatcher through CTFCrewCoordinator."""
        runtime = self.runtime or getattr(self.agent, "runtime", None)
        if runtime is None:
            self._add_system("[!] Runtime not ready")
            return

        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", "crew")

        try:
            from ..agents.crew.swarm_bridge import run_ctf_dispatcher_worker
            from ..agents.pa_agent.ctf_crew_coordinator import CTFCrewCoordinator
            from ..agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher, SolveResult
            from ..agents.pa_agent.ctf_planner import detect_type
            from ..agents.pa_agent.ctf_state import CTFState
            from ..agents.pa_agent.platform_runner import (
                PlatformAutonomyRunner,
                PlatformRunConfig,
            )

            current_url = url
            current_goal = goal
            current_type = chtype
            current_hint = hint
            current_submit_profile = dict(submit_profile or {})
            raw_runner_config = dict(runner_config or {})
            resume_autonomy_state = raw_runner_config.pop("_autonomy_resume_state", None)
            resume_reason = str(raw_runner_config.pop("_autonomy_resume_reason", "") or "").strip()
            run_mode = str(raw_runner_config.get("mode") or "switch").strip().lower()
            if run_mode not in {"single", "switch", "drain"}:
                run_mode = "switch"
            normalized_runner_config = {
                "mode": run_mode,
                "max_challenges": max(1, int(raw_runner_config.get("max_challenges") or 4)),
                "timebox_seconds": max(1, int(raw_runner_config.get("timebox_seconds") or 900)),
                "max_consecutive_stops": max(1, int(raw_runner_config.get("max_consecutive_stops") or 2)),
            }
            runner = PlatformAutonomyRunner()
            auto_switch_depth = 0
            initial_key = f"{str(current_submit_profile.get('challenge_id') or '').strip()}|{current_url}"
            runtime_config = PlatformRunConfig(**normalized_runner_config)
            if isinstance(resume_autonomy_state, dict):
                autonomy_state = runner.restore(
                    resume_autonomy_state,
                    config=runtime_config,
                    initial_visit_key=initial_key.strip("|"),
                    resume_reason=resume_reason or "resume",
                )
            else:
                autonomy_state = runner.start(
                    runtime_config,
                    initial_visit_key=initial_key.strip("|"),
                )
            autonomy_end_reason = "not_started"

            while True:
                challenge_started_at = time.time()
                requested_type = str(current_type or "auto").strip().lower() or "auto"
                planning_dispatcher = CTFTaskDispatcher(
                    runtime=runtime,
                    progress_callback=self._add_system,
                    llm=getattr(self.agent, "llm", None),
                )
                planning_dispatcher.state = CTFState(target=current_url, goal=current_goal)
                planning_dispatcher._apply_submit_profile(current_submit_profile)
                self._carry_forward_platform_switch_context(
                    planning_dispatcher.state,
                    execution_mode="crew",
                    current_url=current_url,
                    current_submit_profile=current_submit_profile,
                )
                self._last_ctf_dispatcher = planning_dispatcher

                await planning_dispatcher._snapshot_platform_context(current_url)
                await planning_dispatcher.capability_registry.full_check()
                planning_dispatcher.state.capabilities = (
                    planning_dispatcher.capability_registry.to_dict()
                )

                page_features = await planning_dispatcher._phase_recon(current_url)
                alignment = planning_dispatcher._align_platform_challenge(current_url, page_features)
                if alignment is not None and planning_dispatcher.state is not None:
                    planning_dispatcher.state.meta_reasonings.append(
                        {
                            "type": "platform_challenge_alignment",
                            **alignment,
                        }
                    )
                    aligned_id = str(alignment.get("challenge_id") or "").strip()
                    if aligned_id and not planning_dispatcher.state.submit_challenge_id:
                        planning_dispatcher.state.submit_challenge_id = aligned_id

                already_solved = bool(alignment and alignment.get("already_solved") is True)
                if already_solved:
                    stop_reason = "challenge_already_solved"
                    planning_dispatcher.state.stop_reason = stop_reason
                    planning_dispatcher.reasoning_layer.generate_stop_report(
                        planning_dispatcher.state,
                        reason=stop_reason,
                        missing_capabilities=[],
                    )
                    solve_result = SolveResult(
                        success=False,
                        flag=None,
                        chain_used=[],
                        notes=[],
                        missing_tools=[],
                        reason=planning_dispatcher._build_already_solved_reason(),
                    )
                    summary = None
                    detected_type = requested_type
                else:
                    detected_type = (
                        requested_type
                        if requested_type not in {"", "auto"}
                        else detect_type(
                            f"{page_features.get('html', '')}\n{page_features.get('content', '')}",
                            current_url,
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

                        self._update_crew_worker(worker_id, status="running")

                        hint_blocks = [str(current_hint or "").strip()]
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

                        dispatcher = CTFTaskDispatcher(
                            runtime=runtime,
                            progress_callback=lambda message, wid=worker_id: self._add_system(
                                f"[CTF crew:{wid}] {message}"
                            ),
                            llm=getattr(self.agent, "llm", None),
                        )

                        try:
                            result = await run_ctf_dispatcher_worker(
                                dispatcher,
                                target=current_url,
                                goal=current_goal,
                                chtype=detected_type,
                                hint=worker_hint,
                                submit_profile=dict(current_submit_profile or {}),
                                worker_id=worker_id,
                                worker_type=worker_type,
                                cancel_event=cancel_event,
                            )
                        except asyncio.CancelledError:
                            self._update_crew_worker(worker_id, status="cancelled")
                            raise
                        except Exception:
                            self._update_crew_worker(worker_id, status="error")
                            raise

                        state_diff = dict(result.get("state_diff") or {})
                        findings_count = len(list(result.get("candidate_flags") or []))
                        findings_count += len(list(state_diff.get("runtime_flags") or []))
                        if result.get("verified_flag"):
                            findings_count += 1

                        self._update_crew_worker(
                            worker_id,
                            status="complete" if not result.get("cancelled") else "cancelled",
                            findings=findings_count,
                        )
                        return result

                    coordinator = CTFCrewCoordinator(
                        state=planning_dispatcher.state,
                        verifier=planning_dispatcher.verifier,
                        worker_runner=_worker_runner,
                        progress_callback=self._add_system,
                    )
                    self._current_crew = coordinator
                    self._show_sidebar()

                    preview_specs = coordinator.build_worker_specs(
                        target=current_url,
                        page_features=page_features,
                    )
                    for spec in preview_specs:
                        self._add_crew_worker(spec.worker_id, spec.worker_type, spec.task)

                    summary = await coordinator.run_with_shadow_graph(
                        target=current_url,
                        page_features=page_features,
                    )
                    stop_reason = self._derive_ctf_crew_stop_reason(summary)
                    coordinator.state.stop_reason = stop_reason
                    planning_dispatcher.reasoning_layer.generate_stop_report(
                        coordinator.state,
                        reason=stop_reason,
                        missing_capabilities=[],
                    )
                    missing_tools = sorted(
                        {
                            tool
                            for item in summary.worker_results.values()
                            for tool in list(item.get("missing_tools") or [])
                        }
                    )
                    solve_result = SolveResult(
                        success=bool(summary.verified_flag),
                        flag=summary.verified_flag,
                        chain_used=[worker_id for worker_id in summary.started_workers],
                        notes=[],
                        missing_tools=missing_tools,
                        reason=stop_reason,
                    )

                self._last_ctf_result = solve_result
                self._last_ctf_state = (
                    planning_dispatcher.state.to_dict() if planning_dispatcher.state is not None else None
                )
                current_state = self._last_ctf_state or {}
                stop_report = (
                    current_state.get("stop_report") if isinstance(current_state, dict) else {}
                ) or {}
                stop_reason = str(
                    stop_report.get("reason")
                    or current_state.get("stop_reason")
                    or solve_result.reason
                    or ""
                )
                current_profile = None
                if isinstance(current_state, dict):
                    for item in reversed(current_state.get("meta_reasonings") or []):
                        if isinstance(item, dict) and item.get("type") == "platform_profile_snapshot":
                            current_profile = item
                            break
                current_challenge_id = str(
                    (current_profile or {}).get("challenge_id")
                    or current_submit_profile.get("challenge_id")
                    or ""
                ).strip()
                current_challenge_name = str(
                    (current_profile or {}).get("challenge_name")
                    or (current_profile or {}).get("name")
                    or ""
                ).strip()
                if not current_challenge_name and isinstance(current_state, dict):
                    for item in reversed(current_state.get("meta_reasonings") or []):
                        if isinstance(item, dict) and item.get("type") == "platform_challenge_alignment":
                            current_challenge_name = str(item.get("challenge_name") or "").strip()
                            if current_challenge_name:
                                break

                runner.record_result(
                    autonomy_state,
                    challenge_id=current_challenge_id,
                    challenge_name=current_challenge_name,
                    url=current_url,
                    result=solve_result,
                    stop_reason=stop_reason,
                    started_at=challenge_started_at,
                    ended_at=time.time(),
                )
                queue_snapshot = None
                if isinstance(current_state, dict):
                    for item in reversed(current_state.get("meta_reasonings") or []):
                        if isinstance(item, dict) and item.get("type") == "platform_task_queue_snapshot":
                            queue_snapshot = item
                            break
                    self._last_ctf_state = self._write_platform_run_meta(
                        current_state,
                        autonomy_state=autonomy_state,
                        autonomy_end_reason=autonomy_end_reason,
                    )

                if solve_result.success:
                    self._add_system(
                        "\n".join(
                            [
                                "[CTF crew] success",
                                f"flag: {solve_result.flag}",
                                f"chain_used: {solve_result.chain_used}",
                                f"reason: {solve_result.reason}",
                            ]
                        )
                    )
                    self._set_status("complete", "crew")
                else:
                    lines = [
                        "[CTF crew] stopped",
                        f"chain_used: {solve_result.chain_used}",
                        f"reason: {solve_result.reason}",
                    ]
                    if solve_result.missing_tools:
                        lines.append("missing_tools: " + ", ".join(solve_result.missing_tools))
                    if summary is not None:
                        lines.extend(
                            [
                                f"workers_started: {', '.join(summary.started_workers) or 'none'}",
                                f"workers_completed: {', '.join(summary.completed_workers) or 'none'}",
                                f"workers_cancelled: {', '.join(summary.cancelled_workers) or 'none'}",
                            ]
                        )
                    self._add_system("\n".join(lines))
                    self._set_status("idle", "crew")

                if planning_dispatcher.state is not None and planning_dispatcher.state.stop_report:
                    self._add_system(self._render_last_ctf_stop_report())
                    self._add_system(self._render_last_ctf_reasoning())
                    self._show_ctf_memory_panel()

                should_continue, autonomy_end_reason = runner.should_continue(
                    autonomy_state,
                    operator_stop=bool(getattr(self, "_should_stop", False)),
                    queue_snapshot=queue_snapshot,
                )
                if not should_continue:
                    break

                next_ctx = self._resolve_ctf_auto_switch_context(
                    result=solve_result,
                    current_url=current_url,
                    current_goal=current_goal,
                    current_type=current_type,
                    current_hint=current_hint,
                    current_submit_profile=current_submit_profile,
                    auto_switch_depth=auto_switch_depth,
                    visited_keys=autonomy_state.visited_keys,
                )
                if next_ctx is None:
                    autonomy_end_reason = "queue_switch_unavailable"
                    break

                autonomy_end_reason = "continue"
                runner.mark_switch(
                    autonomy_state,
                    str(next_ctx.get("visit_key") or ""),
                    reason=str(next_ctx.get("switch_reason") or ""),
                    source=str(next_ctx.get("switch_source") or "platform_queue"),
                )
                auto_switch_depth += 1
                current_url = str(next_ctx["url"])
                current_goal = str(next_ctx["goal"])
                current_type = str(next_ctx["type"])
                current_hint = str(next_ctx["hint"])
                current_submit_profile = dict(next_ctx.get("submit_profile") or {})
                if isinstance(self._last_ctf_state, dict):
                    meta_reasonings = list(self._last_ctf_state.get("meta_reasonings") or [])
                    meta_reasonings.append(
                        {
                            "type": "platform_queue_switch_decision",
                            "switch_reason": str(next_ctx.get("switch_reason") or ""),
                            "switch_source": str(next_ctx.get("switch_source") or "platform_queue"),
                            "skipped_candidates": list(next_ctx.get("skipped_candidates") or []),
                            "next_challenge_id": str(current_submit_profile.get("challenge_id") or ""),
                            "next_url": current_url,
                        }
                    )
                    self._last_ctf_state["meta_reasonings"] = meta_reasonings
                self._last_ctf_context = {
                    "url": current_url,
                    "goal": current_goal,
                    "type": current_type,
                    "hint": current_hint,
                    "submit_profile": dict(current_submit_profile),
                    "runner_config": dict(normalized_runner_config),
                    "execution_mode": "crew",
                    "switch_reason": str(next_ctx.get("switch_reason") or ""),
                    "switch_source": str(next_ctx.get("switch_source") or "platform_queue"),
                    "skipped_candidates": list(next_ctx.get("skipped_candidates") or []),
                    "auto_switch_depth": auto_switch_depth,
                    "visited_queue_keys": sorted(key for key in autonomy_state.visited_keys if key),
                    "autonomy_state": autonomy_state.to_dict(),
                }
                self._add_system(
                    "\n".join(
                        [
                            "[CTF crew queue] auto-switch engaged",
                            f"next_url: {current_url}",
                            f"next_challenge_id: {current_submit_profile.get('challenge_id', '')}",
                            f"depth: {auto_switch_depth}",
                            f"switch_reason: {next_ctx.get('switch_reason', '')}",
                            f"runner_mode: {normalized_runner_config['mode']}",
                        ]
                    )
                )

            if isinstance(self._last_ctf_state, dict):
                current_state = self._last_ctf_state
                self._last_ctf_state = self._write_platform_run_meta(
                    current_state,
                    autonomy_state=autonomy_state,
                    autonomy_end_reason=autonomy_end_reason,
                )

            if self._last_ctf_context:
                self._last_ctf_context["runner_config"] = dict(normalized_runner_config)
                self._last_ctf_context["autonomy_state"] = autonomy_state.to_dict()
                self._last_ctf_context["autonomy_end_reason"] = autonomy_end_reason
                self._last_ctf_context["execution_mode"] = str(
                    self._last_ctf_context.get("execution_mode") or "crew"
                )

            await asyncio.sleep(1)
            self._set_status("idle", "crew")
        except asyncio.CancelledError:
            if self._current_crew:
                await self._current_crew.cancel()
            self._add_system("[!] Cancelled")
            self._set_status("idle", "crew")
        except Exception as e:
            self._add_system(f"[!] CTF crew error: {e}")
            self._set_status("error")
        finally:
            self._current_crew = None
            await self._save_current_conversation()
            self._is_running = False

    def _derive_ctf_crew_stop_reason(self, summary: Any) -> str:
        # Single source of truth lives in the shared headless crew runner so the
        # TUI and the CLI/web crew path (D4) agree on stop-reason normalization.
        from ..agents.pa_agent.ctf_crew_runner import derive_crew_stop_reason

        return derive_crew_stop_reason(summary)

    def _resolve_ctf_auto_switch_context(
        self,
        *,
        result: Any,
        current_url: str,
        current_goal: str,
        current_type: str,
        current_hint: str,
        current_submit_profile: dict[str, Any] | None,
        auto_switch_depth: int,
        visited_keys: set[str],
    ) -> dict[str, Any] | None:
        state = getattr(self, "_last_ctf_state", None) or {}
        if not self._should_auto_switch_ctf_task(
            state=state,
            result=result,
            auto_switch_depth=auto_switch_depth,
        ):
            return None

        snapshot = None
        for item in reversed(state.get("meta_reasonings") or []):
            if isinstance(item, dict) and item.get("type") == "platform_task_queue_snapshot":
                snapshot = item
                break
        if not snapshot:
            return None

        profile = None
        for item in reversed(state.get("meta_reasonings") or []):
            if isinstance(item, dict) and item.get("type") == "platform_profile_snapshot":
                profile = item
                break
        current_challenge_id = ""
        if profile:
            current_challenge_id = str(profile.get("challenge_id") or "").strip()

        from ..agents.pa_agent.platform_orchestrator import PlatformTaskOrchestrator

        selection = PlatformTaskOrchestrator().select_next_task(
            snapshot,
            current_challenge_id=current_challenge_id,
            visited_keys=visited_keys,
        )
        next_task = selection.get("task")
        if not isinstance(next_task, dict):
            return None

        next_url = self._resolve_next_ctf_queue_url(
            current_url=current_url,
            current_submit_profile=current_submit_profile or {},
            current_challenge_id=current_challenge_id,
            next_task=next_task,
        )
        if not next_url:
            return None

        submit_profile = dict(current_submit_profile or {})
        next_challenge_id = str(next_task.get("challenge_id") or "").strip()
        if next_challenge_id:
            submit_profile["challenge_id"] = next_challenge_id

        queue_hint = (
            f"[Platform queue switch]\n"
            f"- Previous challenge stopped with reason: {getattr(result, 'reason', '')}\n"
            f"- Switched to next queue candidate `{next_task.get('name', '')}` ({next_challenge_id}).\n"
            f"- Switch reason: {selection.get('switch_reason', '')}\n"
            f"- Preserve platform submit profile and continue autonomous solving."
        )
        next_hint = (
            f"{current_hint}\n\n{queue_hint}" if current_hint else queue_hint
        )
        return {
            "url": next_url,
            "goal": current_goal,
            "type": current_type,
            "hint": next_hint,
            "submit_profile": submit_profile,
            "visit_key": f"{next_challenge_id}|{next_url}",
            "switch_reason": str(selection.get("switch_reason") or ""),
            "switch_source": str(selection.get("switch_source") or "platform_queue"),
            "skipped_candidates": list(selection.get("skipped_candidates") or []),
        }

    def _should_auto_switch_ctf_task(
        self,
        *,
        state: dict[str, Any],
        result: Any,
        auto_switch_depth: int,
    ) -> bool:
        if auto_switch_depth >= 3:
            return False
        if getattr(self, "_should_stop", False):
            return False

        stop_report = state.get("stop_report") or {}
        reason = str(stop_report.get("reason") or getattr(result, "reason", "") or "").strip().lower()
        if getattr(result, "success", False):
            return True
        if reason in {
            "challenge_already_solved",
            "all_hypotheses_exhausted",
            "capability_ceiling",
            "stopped",
            "candidate_only",
        }:
            return True
        if "already solved" in reason:
            return True
        if "未命中 flag" in str(getattr(result, "reason", "") or ""):
            return True
        return False

    def _resolve_next_ctf_queue_url(
        self,
        *,
        current_url: str,
        current_submit_profile: dict[str, Any],
        current_challenge_id: str,
        next_task: dict[str, Any],
    ) -> str:
        task_url = str(next_task.get("url") or "").strip()
        if task_url:
            if task_url.startswith("http://") or task_url.startswith("https://"):
                return task_url
            base_url = str(current_submit_profile.get("base_url") or "").strip()
            if base_url:
                return urljoin(base_url.rstrip("/") + "/", task_url.lstrip("/"))

        next_id = str(next_task.get("challenge_id") or "").strip()
        if not next_id:
            return ""

        parsed = urlparse(current_url)
        params = parse_qs(parsed.query)
        replaced = False
        for key in ("challenge_id", "cid", "id", "task_id", "room_code"):
            if key in params:
                params[key] = [next_id]
                replaced = True
        if replaced:
            new_query = urlencode(params, doseq=True)
            return parsed._replace(query=new_query).geturl()

        path_parts = parsed.path.split("/")
        if current_challenge_id:
            replaced_parts = [
                next_id if part == current_challenge_id else part for part in path_parts
            ]
            if replaced_parts != path_parts:
                return parsed._replace(path="/".join(replaced_parts)).geturl()

        base_url = str(current_submit_profile.get("base_url") or "").strip()
        if base_url:
            return urljoin(base_url.rstrip("/") + "/", f"challenges/{next_id}")
        return ""

    def _carry_forward_platform_switch_context(
        self,
        state: Any,
        *,
        execution_mode: str,
        current_url: str,
        current_submit_profile: dict[str, Any] | None,
    ) -> None:
        if state is None or not hasattr(state, "meta_reasonings"):
            return

        previous_context = getattr(self, "_last_ctf_context", None) or {}
        if str(previous_context.get("execution_mode") or "").strip() != execution_mode:
            return

        previous_profile = dict(previous_context.get("submit_profile") or {})
        current_profile = dict(current_submit_profile or {})
        current_challenge_id = str(current_profile.get("challenge_id") or "").strip()
        previous_challenge_id = str(previous_profile.get("challenge_id") or "").strip()
        if current_challenge_id and previous_challenge_id and current_challenge_id != previous_challenge_id:
            return

        switch_reason = str(previous_context.get("switch_reason") or "").strip()
        switch_source = str(previous_context.get("switch_source") or "").strip()
        if not switch_reason and not switch_source:
            return

        carryover = {
            "type": "platform_switch_carryover_context",
            "execution_mode": execution_mode,
            "current_url": current_url,
            "challenge_id": current_challenge_id or previous_challenge_id,
            "switch_reason": switch_reason,
            "switch_source": switch_source or "platform_queue",
            "skipped_candidates": list(previous_context.get("skipped_candidates") or []),
            "auto_switch_depth": int(previous_context.get("auto_switch_depth") or 0),
            "visited_queue_keys": list(previous_context.get("visited_queue_keys") or []),
        }

        meta_reasonings = list(getattr(state, "meta_reasonings", []) or [])
        meta_reasonings = [
            item
            for item in meta_reasonings
            if not (
                isinstance(item, dict)
                and item.get("type")
                in {"platform_switch_carryover_context", "platform_queue_switch_decision"}
            )
        ]
        meta_reasonings.append(carryover)
        meta_reasonings.append(
            {
                "type": "platform_queue_switch_decision",
                "switch_reason": carryover["switch_reason"],
                "switch_source": carryover["switch_source"],
                "skipped_candidates": list(carryover["skipped_candidates"]),
                "next_challenge_id": carryover["challenge_id"],
                "next_url": current_url,
            }
        )
        state.meta_reasonings = meta_reasonings

    def _write_platform_run_meta(
        self,
        state: dict[str, Any],
        *,
        autonomy_state: Any,
        autonomy_end_reason: str,
    ) -> dict[str, Any]:
        if not isinstance(state, dict):
            return state

        elapsed_seconds = round(max(0.0, time.time() - autonomy_state.started_at), 3)
        summary = autonomy_state.to_dict()
        summary.update(
            {
                "type": "platform_autonomy_run_summary",
                "end_reason": autonomy_end_reason,
                "elapsed_seconds": elapsed_seconds,
                "challenge_count": len(autonomy_state.records),
            }
        )
        last_record = summary.get("records", [])[-1] if summary.get("records") else {}
        stop_summary = {
            "type": "platform_run_stop_summary",
            "end_reason": autonomy_end_reason,
            "elapsed_seconds": elapsed_seconds,
            "challenge_count": len(autonomy_state.records),
            "consecutive_stops": summary.get("consecutive_stops", 0),
            "blocked_reasons": list(summary.get("blocked_reasons") or []),
            "skip_reasons": list(summary.get("skip_reasons") or []),
            "resume_count": summary.get("resume_count", 0),
            "resumed_from_record_count": summary.get("resumed_from_record_count", 0),
            "resume_reason": str(summary.get("resume_reason") or ""),
            "last_switch_reason": str(summary.get("last_switch_reason") or ""),
            "last_switch_source": str(summary.get("last_switch_source") or ""),
            "switch_events": list(summary.get("switch_events") or [])[-3:],
            "last_record": dict(last_record) if isinstance(last_record, dict) else {},
        }

        meta_reasonings = list(state.get("meta_reasonings") or [])
        meta_reasonings = [
            item
            for item in meta_reasonings
            if not (
                isinstance(item, dict)
                and item.get("type")
                in {"platform_autonomy_run_summary", "platform_run_stop_summary"}
            )
        ]
        meta_reasonings.extend([summary, stop_summary])
        state["meta_reasonings"] = meta_reasonings
        return state
