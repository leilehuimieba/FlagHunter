"""Retry / copy / retrospective commands mixed into FlagHunterTUI (债池五波·TUI 刀 20, god-class).

Extracted from tui.py. The /retry, /copy and /retro slash-command handlers:
``_find_retryable_plan_step`` finds the last failed plan step, ``_handle_retry_command``
+ the ``@work`` ``_run_retry_plan_step`` re-run it, ``_handle_copy_command`` copies the
last message to the clipboard, and ``_handle_retro_command`` renders the retrospective
ledger. They call stay-behind helpers (``self._add_system`` / ``self.agent``) resolved at
runtime through the FlagHunterTUI instance MRO; the stay-behind ``_handle_command``
dispatches them. Module-level deps: ``asyncio`` / ``Any`` / ``Optional`` / ``work``;
finish.StepStatus / subprocess / sys / tempfile / pathlib / retrospective backends are
lazy inside the bodies.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from textual import work


class RetryCommandMixin:
    """/retry /copy /retro command handlers for FlagHunterTUI."""

    def _find_retryable_plan_step(self) -> Optional[Any]:
        """Find the most recent FAIL or IN_PROGRESS plan step."""
        runtime = self.runtime or getattr(self.agent, "runtime", None)
        plan = getattr(runtime, "plan", None) if runtime else None
        if not plan or not getattr(plan, "steps", None):
            return None

        try:
            from ..tools.finish import StepStatus

            retryable = {
                StepStatus.FAIL,
                StepStatus.IN_PROGRESS,
                "fail",
                "in_progress",
            }
            for step in reversed(plan.steps):
                if getattr(step, "status", None) in retryable:
                    return step
        except Exception:
            return None
        return None

    async def _handle_retry_command(self) -> None:
        """Re-run the most recent failed/in-progress step without resetting the plan."""
        if not self.agent:
            self._add_system("[!] Agent not ready")
            return
        if self._is_running:
            self._add_system("[!] Agent is already running.")
            return

        step = self._find_retryable_plan_step()
        if not step:
            self._add_system("[!] No FAIL or IN_PROGRESS plan step available for /retry.")
            return

        try:
            from ..tools.finish import StepStatus

            step.status = StepStatus.PENDING
            step.result = None
        except Exception as exc:
            self._add_system(f"[!] Failed to reset retry step: {exc}")
            return

        tool_context = ""
        if self._pending_tool_install and self._pending_tool_install.get("tool"):
            tool_context = (
                f" Missing tool context: {self._pending_tool_install['tool']} "
                f"({self._pending_tool_install.get('install_hint', 'install manually')})."
            )

        self._add_system(
            f"[retry] Re-queued Step {step.id}: {step.description}"
        )
        self._pending_tool_install = None
        self._current_worker = self._run_retry_plan_step(
            step.id,
            str(step.description),
            tool_context,
        )

    @work(thread=False)
    async def _run_retry_plan_step(
        self, step_id: int, step_description: str, tool_context: str = ""
    ) -> None:
        """Continue the existing plan from a retried step."""
        if not self.agent:
            self._add_system("[!] Agent not ready")
            return

        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", "agent")

        retry_prompt = (
            f"Retry the current plan from Step {step_id}: {step_description}."
            f"{tool_context} Re-execute this step and continue the existing plan."
            " Do not reset the task or create a brand-new unrelated plan unless the"
            " current plan is no longer feasible."
        )

        try:
            tool_messages_mapping: dict[str, ToolMessage] = {}
            await self._display_responses(
                self.agent.continue_conversation(retry_prompt),
                tool_messages_mapping,
                is_agent=True,
            )
            self._set_status("complete", "agent")
            self._add_system("+ Retry complete. Back to assist mode.")
            await asyncio.sleep(1)
            self._set_status("idle", "assist")
        except asyncio.CancelledError:
            self._add_system("[!] Retry cancelled")
            self._set_status("idle", "assist")
        except Exception as e:
            self._add_system(f"[!] Retry error: {e}")
            self._set_status("error")
        finally:
            await self._save_current_conversation()
            self._is_running = False

    async def _handle_copy_command(self, cmd: str) -> None:
        """Copy the last N agent/system messages to the clipboard.

        Usage: /copy [n]   (default n=5)
        On Windows uses clip.exe; on Linux/macOS tries xclip/pbcopy.
        """
        import subprocess as _sp

        parts = cmd.strip().split()
        try:
            n = int(parts[1]) if len(parts) > 1 else 5
        except (IndexError, ValueError):
            n = 5

        # Collect text from the most recent N message widgets
        snippets: list[str] = []
        for w in self._chat_widgets[-n * 2 :]:  # overshoot, then trim
            if hasattr(w, "_copy_content"):
                snippets.append(w._copy_content)
            elif hasattr(w, "message_content"):
                snippets.append(w.message_content)
            if len(snippets) >= n:
                break

        if not snippets:
            self._add_system("[copy] No messages to copy.")
            return

        text = "\n\n---\n\n".join(snippets)

        try:
            import sys as _sys
            if _sys.platform == "win32":
                _sp.run(["clip"], input=text.encode("utf-16"), check=True)
            elif _sys.platform == "darwin":
                _sp.run(["pbcopy"], input=text.encode(), check=True)
            else:
                _sp.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
            self._add_system(f"[copy] {len(snippets)} message(s) copied to clipboard.")
        except Exception as e:
            # Fallback: write to a temp file
            import tempfile, pathlib
            tf = pathlib.Path(tempfile.gettempdir()) / "flaghunter_copy.txt"
            tf.write_text(text, encoding="utf-8")
            self._add_system(f"[copy] clipboard unavailable ({e}); saved to {tf}")

    async def _handle_retro_command(self, cmd: str) -> None:
        """Show unresolved retrospective items or resolve an item by id."""
        parts = cmd.strip().split()

        try:
            from ..knowledge.retrospective import (
                get_unresolved_entries,
                mark_resolved,
            )
        except Exception as exc:
            self._add_system(f"[retro] unavailable: {exc}")
            return

        if len(parts) >= 3 and parts[1].lower() == "resolve":
            try:
                entry_id = int(parts[2])
            except Exception:
                self._add_system("[retro] Usage: /retro resolve <id>")
                return

            try:
                mark_resolved(entry_id)
                self._add_system(f"[retro] Marked entry #{entry_id} as resolved.")
            except Exception as exc:
                self._add_system(f"[retro] resolve failed: {exc}")
            return

        unresolved = get_unresolved_entries()
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"[CTF Retrospective] {len(unresolved)} unresolved items",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        for entry in unresolved:
            ts = str(entry.get("timestamp", ""))
            date_str = ts[:10] if len(ts) >= 10 else ts
            lines.append(
                f"#{entry.get('id')} [{entry.get('category', 'other')}] {date_str}"
            )
            lines.append(f"   {entry.get('description', '')}")
            suggestion = str(entry.get("suggestion", "") or "").strip()
            if suggestion:
                lines.append(f"   Suggestion: {suggestion}")
            lines.append("")

        if not unresolved:
            lines.append("No unresolved retrospective items.")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self._add_system("\n".join(lines))
