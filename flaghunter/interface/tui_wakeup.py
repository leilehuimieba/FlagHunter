"""Child-agent wake-up handling mixed into FlagHunterTUI (债池五波·TUI 刀 24, god-class).

Extracted from tui.py. The child-agent wake-up feature: ``_on_agent_wake_up_callback``
(invoked off-thread by a child agent) posts a ``ChildAgentWakeUpMessage``,
``on_child_agent_wake_up_message`` is Textual's name-convention handler that schedules the
``@work`` ``_run_wake_up_mode`` resume loop on the main loop. They call stay-behind helpers
(``self._add_system`` / ``self._set_status`` / ``self.agent``) resolved at runtime through
the FlagHunterTUI instance MRO. Module-level deps: ``asyncio`` / ``logging`` / ``work`` /
``ChildAgentWakeUpMessage`` (tui_messages, 刀1) / ``ToolMessage`` (tui_message_widgets, 刀3,
only in a local annotation).
"""

from __future__ import annotations

import asyncio
import logging

from textual import work

from .tui_message_widgets import ToolMessage
from .tui_messages import ChildAgentWakeUpMessage


class WakeUpMixin:
    """Child-agent wake-up callback + resume loop for FlagHunterTUI."""

    def _on_agent_wake_up_callback(self) -> None:
        """Triggered by notifier.agent_wake_up() — may come from any async context."""
        try:
            try:
                asyncio.get_running_loop()
                # Already on the app's event loop — post_message directly.
                self.post_message(ChildAgentWakeUpMessage())
                return
            except RuntimeError:
                pass
            # Called from a worker thread — use call_from_thread.
            if hasattr(self, "call_from_thread"):
                try:
                    self.call_from_thread(self.post_message, ChildAgentWakeUpMessage())
                    return
                except Exception:
                    pass
            self.post_message(ChildAgentWakeUpMessage())
        except Exception as e:
            logging.getLogger(__name__).exception(
                "_on_agent_wake_up_callback failed: %s", e
            )

    def on_child_agent_wake_up_message(self, _event: ChildAgentWakeUpMessage) -> None:
        """Received on Textual's main loop — safe to start a @work method here."""
        if not self._is_running and self.agent:
            self._current_worker = self._run_wake_up_mode()

    @work(thread=False)
    async def _run_wake_up_mode(self) -> None:
        """Resume processing a pending child-agent notification in the active mode.

        The notification has already been injected into conversation_history by
        the watcher.  Dispatches display logic per mode so the behaviour is
        identical to the regular runner (_run_assist / _run_interact /
        _run_agent_mode) — avoiding subtle differences in state checks or
        status updates that would break result display.
        """
        if not self.agent:
            return

        mode = self._mode
        self._is_running = True
        self._should_stop = False
        self._set_status("thinking", mode)
        tool_messages_mapping: dict[str, ToolMessage] = {}

        try:
            tool_messages_mapping: dict[str, ToolMessage] = {}
            await self._display_responses(
                self.agent.wake_up(mode),
                tool_messages_mapping,
                is_agent=(mode == "agent"),
            )
            self._set_status("idle", mode)

        except asyncio.CancelledError:
            self._add_system("[!] Cancelled")
            self._set_status("idle", mode)
        except Exception as e:
            self._add_system(f"[!] Error: {e}")
            self._set_status("error")
        finally:
            self._is_running = False
