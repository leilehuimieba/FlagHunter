"""Crew-mode worker UI + lifecycle mixed into FlagHunterTUI (债池五波·TUI 刀14, god-class).

Extracted from tui.py. The multi-agent crew feature: crew stats / spinner / worker
panels (add/update), worker-label formatting, the worker-event handler, tool-to-worker
attach, the ``@on(Tree.NodeSelected)`` worker-tree selection handler, the ``@work``
``_run_crew_mode`` runner, and ``_cancel_crew``. Members call each other plus
stay-behind helpers (``self._add_*`` / ``_set_status`` / ``_build_prior_context``)
resolved at runtime through the FlagHunterTUI instance MRO. Decorator refs (on / work
/ Tree) and rich/textual primitives are imported here; agent backends are lazy inside
the bodies.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from rich.text import Text
from textual import on, work
from textual.widgets import Static, Tree


class CrewMixin:
    """Crew-mode worker UI + run/cancel lifecycle for FlagHunterTUI."""

    def _update_crew_stats(self) -> None:
        """Update crew stats panel."""
        try:
            import time

            text = Text()

            # Elapsed time
            text.append("Time:   ", style="bold #d4d4d4")
            if self._crew_start_time:
                elapsed = time.time() - self._crew_start_time
                if elapsed < 60:
                    time_str = f"{int(elapsed)}s"
                elif elapsed < 3600:
                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    time_str = f"{mins}m {secs}s"
                else:
                    hrs = int(elapsed // 3600)
                    mins = int((elapsed % 3600) // 60)
                    time_str = f"{hrs}h {mins}m"
                text.append(time_str, style="#9a9a9a")
            else:
                text.append("--", style="#525252")

            text.append("\n")

            # Tokens used
            text.append("Tokens: ", style="bold #d4d4d4")
            if self._crew_tokens_used > 0:
                if self._crew_tokens_used >= 1000:
                    token_str = f"{self._crew_tokens_used / 1000:.1f}k"
                else:
                    token_str = str(self._crew_tokens_used)
                text.append(token_str, style="#9a9a9a")
            else:
                text.append("--", style="#525252")

            stats = self.query_one("#crew-stats", Static)
            stats.update(text)
            stats.border_title = "# Stats"
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to hide sidebar: %s", e)
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to hide sidebar: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about hide_sidebar failure"
                )

    def _update_spinner(self) -> None:
        """Update spinner animation for running workers."""
        try:
            # Advance spinner frame
            self._spinner_frame += 1

            # Only update labels for running workers (efficient)
            has_running = False
            for worker_id, worker in self._crew_workers.items():
                if worker.get("status") == "running":
                    has_running = True
                    # Update the tree node label
                    if worker_id in self._crew_worker_nodes:
                        node = self._crew_worker_nodes[worker_id]
                        node.set_label(self._format_worker_label(worker_id))

            # Stop spinner if no workers are running (save resources)
            if not has_running and self._spinner_timer:
                self._spinner_timer.stop()
                self._spinner_timer = None
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to update crew stats: %s", e)
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to update crew stats: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about crew stats update failure"
                )

    def _add_crew_worker(self, worker_id: str, worker_type: str, task: str) -> None:
        """Add a worker to the sidebar tree."""
        self._crew_workers[worker_id] = {
            "worker_type": worker_type,
            "task": task,
            "status": "pending",
            "findings": 0,
        }

        try:
            label = self._format_worker_label(worker_id)
            if self._crew_orchestrator_node:
                node = self._crew_orchestrator_node.add(
                    label, data={"type": "worker", "id": worker_id}
                )
                self._crew_worker_nodes[worker_id] = node
                try:
                    self._crew_orchestrator_node.expand()
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Failed to expand crew orchestrator node: %s", e
                    )
                    try:
                        from .notifier import notify

                        notify("warning", f"TUI: failed to expand crew node: {e}")
                    except Exception:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about crew node expansion failure"
                        )
            self._update_crew_stats()
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to update spinner: %s", e)
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to update spinner: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about spinner update failure"
                )

    def _update_crew_worker(self, worker_id: str, **updates) -> None:
        """Update a worker's state."""
        if worker_id not in self._crew_workers:
            return

        self._crew_workers[worker_id].update(updates)

        # Restart spinner if a worker started running
        if updates.get("status") == "running" and not self._spinner_timer:
            self._spinner_timer = self.set_interval(0.15, self._update_spinner)

        try:
            if worker_id in self._crew_worker_nodes:
                label = self._format_worker_label(worker_id)
                self._crew_worker_nodes[worker_id].set_label(label)
            self._update_crew_stats()
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to add crew worker node: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to add crew worker node: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about add_crew_worker failure"
                )

    def _format_worker_label(self, worker_id: str) -> Text:
        """Format worker label for tree."""
        worker = self._crew_workers.get(worker_id, {})
        status = worker.get("status", "pending")
        wtype = worker.get("worker_type", "worker")
        findings = worker.get("findings", 0)

        # 4-state icons: working (braille), done (checkmark), warning (!), error (X)
        if status in ("running", "pending"):
            # Animated braille spinner for all in-progress states
            icon = self._spinner_frames[self._spinner_frame % len(self._spinner_frames)]
            color = "#d4d4d4"  # white
        elif status == "complete":
            icon = "✓"
            color = "#22c55e"  # green
        elif status == "warning":
            icon = "!"
            color = "#f59e0b"  # amber/orange
        else:  # error, cancelled, unknown
            icon = "✗"
            color = "#ef4444"  # red

        text = Text()
        text.append(f"{icon} ", style=color)
        text.append(wtype.upper(), style="bold")

        if status == "complete" and findings > 0:
            text.append(f" [{findings}]", style="#22c55e")  # green
        elif status in ("error", "cancelled"):
            # Don't append " !" here since we already have the X icon
            pass

        return text

    def _handle_worker_event(
        self, worker_id: str, event_type: str, data: Dict[str, Any]
    ) -> None:
        """Handle worker events from CrewAgent - updates tree sidebar only."""
        try:
            if event_type == "spawn":
                worker_type = data.get("worker_type", "unknown")
                task = data.get("task", "")
                self._add_crew_worker(worker_id, worker_type, task)
            elif event_type == "status":
                status = data.get("status", "running")
                self._update_crew_worker(worker_id, status=status)
            elif event_type == "tool":
                # Add tool as child node under the agent
                tool_name = data.get("tool", "unknown")
                self._add_tool_to_worker(worker_id, tool_name)
            elif event_type == "tokens":
                # Track token usage
                tokens = data.get("tokens", 0)
                self._crew_tokens_used += tokens
            elif event_type == "complete":
                findings_count = data.get("findings_count", 0)
                self._update_crew_worker(
                    worker_id, status="complete", findings=findings_count
                )
                self._crew_findings_count += findings_count
                self._update_crew_stats()
            elif event_type == "warning":
                # Worker hit max iterations but has results
                self._update_crew_worker(worker_id, status="warning")
                reason = data.get("reason", "Partial completion")
                worker = self._crew_workers.get(worker_id, {})
                wtype = worker.get("worker_type", "worker")
                self._add_system(f"[!] {wtype.upper()} stopped: {reason}")
                self._update_crew_stats()
            elif event_type == "failed":
                # Worker determined task infeasible
                self._update_crew_worker(worker_id, status="failed")
                reason = data.get("reason", "Task infeasible")
                worker = self._crew_workers.get(worker_id, {})
                wtype = worker.get("worker_type", "worker")
                self._add_system(f"[!] {wtype.upper()} failed: {reason}")
                self._update_crew_stats()
            elif event_type == "error":
                self._update_crew_worker(worker_id, status="error")
                worker = self._crew_workers.get(worker_id, {})
                wtype = worker.get("worker_type", "worker")
                error_msg = data.get("error", "Unknown error")
                # Only show errors in chat - they're important
                self._add_system(f"[!] {wtype.upper()} failed: {error_msg}")
        except Exception as e:
            self._add_system(f"[!] Worker event error: {e}")

    def _add_tool_to_worker(self, worker_id: str, tool_name: str) -> None:
        """Add a tool usage as child node under worker in tree."""
        try:
            node = self._crew_worker_nodes.get(worker_id)
            if node:
                node.add_leaf(f"  {tool_name}")
                node.expand()
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to update crew worker display: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed to update crew worker display: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about update_crew_worker failure"
                )

    @on(Tree.NodeSelected, "#workers-tree")
    def on_worker_tree_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection."""
        node = event.node
        if node.data:
            node_type = node.data.get("type")
            if node_type == "crew":
                self._viewing_worker_id = None
            elif node_type == "worker":
                self._viewing_worker_id = node.data.get("id")

    @work(thread=False)
    async def _run_crew_mode(self, target: str) -> None:
        """Run crew mode with sidebar."""
        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", "crew")

        try:
            from ..agents.base_agent import AgentMessage
            from ..agents.crew import CrewOrchestrator
            from ..config.settings import get_settings
            from ..llm import LLM, ModelConfig

            # Build prior context from assist/agent conversation history
            prior_context = self._build_prior_context()

            # Ensure model/runtime are available for static analysis
            assert self.model is not None
            assert self.runtime is not None

            # Honour the configured temperature + max_tokens (settings singleton, H15).
            llm = LLM(
                model=self.model,
                config=ModelConfig(
                    temperature=get_settings().temperature,
                    max_tokens=get_settings().max_tokens,
                ),
            )

            crew = CrewOrchestrator(
                llm=llm,
                tools=self.all_tools,
                runtime=self.runtime,
                on_worker_event=self._handle_worker_event,
                rag_engine=self.rag_engine,
                target=target,
                prior_context=prior_context,
            )
            self._current_crew = crew  # Track for cancellation

            self._add_system(f"@ Task: {target}")

            # Track crew results for memory
            crew_report = None

            async for update in crew.run(target):
                if self._should_stop:
                    await crew.cancel()
                    self._add_system("[!] Stopped by user")
                    break

                phase = update.get("phase", "")

                if phase == "starting":
                    self._set_status("thinking", "crew")

                elif phase == "tokens":
                    # Track orchestrator token usage
                    tokens = update.get("tokens", 0)
                    self._crew_tokens_used += tokens
                    self._update_crew_stats()

                elif phase == "thinking":
                    # Show the orchestrator's reasoning
                    content = update.get("content", "")
                    if content:
                        self._add_thinking(content)

                elif phase == "tool_call":
                    # Show orchestration tool calls
                    tool = update.get("tool", "")
                    args = update.get("args", {})
                    self._add_tool(tool, str(args))

                elif phase == "tool_result":
                    # Tool results are tracked via worker events
                    pass

                elif phase == "complete":
                    crew_report = update.get("report", "")
                    if crew_report:
                        self._add_assistant(crew_report)

                elif phase == "error":
                    error = update.get("error", "Unknown error")
                    self._add_system(f"[!] Crew error: {error}")

            # Add crew results to main agent's conversation history
            # so assist mode can reference what happened
            if self.agent and crew_report:
                # Add the crew task as a user message
                self.agent.conversation_history.append(
                    AgentMessage(
                        role="user",
                        content=f"[CREW MODE] Run parallel analysis on target: {target}",
                    )
                )
                # Add the crew report as assistant response
                self.agent.conversation_history.append(
                    AgentMessage(role="assistant", content=crew_report)
                )

            self._set_status("complete", "crew")
            self._add_system("+ Crew task complete.")

            # Stop timers
            if self._crew_stats_timer:
                self._crew_stats_timer.stop()
                self._crew_stats_timer = None
            if self._spinner_timer:
                self._spinner_timer.stop()
                self._spinner_timer = None

            # Clear crew reference
            self._current_crew = None

        except asyncio.CancelledError:
            # Cancel crew workers first
            if self._current_crew:
                await self._current_crew.cancel()
                self._current_crew = None
            self._add_system("[!] Cancelled")
            self._set_status("idle", "crew")
            # Stop timers on cancel
            if self._crew_stats_timer:
                self._crew_stats_timer.stop()
                self._crew_stats_timer = None
            if self._spinner_timer:
                self._spinner_timer.stop()
                self._spinner_timer = None

        except Exception as e:
            import traceback

            # Cancel crew workers on error too
            if self._current_crew:
                try:
                    await self._current_crew.cancel()
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Failed to add tool to worker node: %s", e
                    )
                    try:
                        from .notifier import notify

                        notify("warning", f"TUI: failed to add tool to worker: {e}")
                    except Exception:
                        logging.getLogger(__name__).exception(
                            "Failed to notify operator about add_tool_to_worker failure"
                        )
                self._current_crew = None
            self._add_system(f"[!] Crew error: {e}\n{traceback.format_exc()}")
            self._set_status("error")
            # Stop timers on error too
            if self._crew_stats_timer:
                self._crew_stats_timer.stop()
                self._crew_stats_timer = None
            if self._spinner_timer:
                self._spinner_timer.stop()
                self._spinner_timer = None
        finally:
            await self._save_current_conversation()
            self._is_running = False

    async def _cancel_crew(self) -> None:
        """Cancel crew orchestrator and all workers."""
        try:
            if self._current_crew:
                await self._current_crew.cancel()
                self._current_crew = None
                # Mark all running workers as cancelled in the UI
                for worker_id, worker in self._crew_workers.items():
                    if worker.get("status") in ("running", "pending"):
                        self._update_crew_worker(worker_id, status="cancelled")
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to cancel crew orchestrator cleanly: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: failed during crew cancellation: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about crew cancellation failure"
                )
