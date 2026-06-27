"""Textual action bindings + command-history nav mixed into FlagHunterTUI (债池五波·TUI 刀 25, god-class).

Extracted from tui.py. The Textual ``action_*`` binding handlers — quit, stop-agent
(+ its ``_reconnect_mcp_after_cancel`` helper), show-help, focus-next — plus the
input command-history navigation (``_suggestions_visible`` / ``action_history_up`` /
``action_history_down``). Textual resolves ``action_<name>`` by name through the
FlagHunterTUI instance MRO at keypress time, so the BINDINGS table stays behind in the
main class and still dispatches here. Module-level deps: ``asyncio`` / ``logging`` /
``Static`` / ``HelpScreen`` (tui_screens, 刀4) / ``CommandSuggestions`` (tui_core_widgets,
刀6); notify is lazy inside the bodies. No decorators.
"""

from __future__ import annotations

import asyncio
import logging

from textual.widgets import Static

from .tui_core_widgets import CommandSuggestions
from .tui_screens import HelpScreen


class ActionsMixin:
    """Textual action bindings + command-history nav for FlagHunterTUI."""

    def action_quit_app(self) -> None:
        # Stop any running tasks first
        if self._is_running:
            self._should_stop = True
            if (
                self._current_worker
                and not getattr(self._current_worker, "done", lambda: False)()
            ):
                cancel = getattr(self._current_worker, "cancel", None)
                if cancel:
                    cancel()
            if self._current_crew:
                # Schedule cancel but don't wait - we're exiting
                asyncio.create_task(self._cancel_crew())
        self.exit()

    def action_stop_agent(self) -> None:
        # Hide suggestions on Escape without stopping the agent
        try:
            suggestions = self.query_one("#cmd-suggestions", CommandSuggestions)
            if suggestions.display:
                suggestions.hide()
                self.query_one("#tab-hint", Static).display = False
                self._get_chat_input().styles.width = "1fr"
                return
        except Exception:
            pass
        if self._is_running:
            self._should_stop = True
            self._add_system("[!] Stopping...")

            # Cancel the running worker to interrupt blocking awaits
            if (
                self._current_worker
                and not getattr(self._current_worker, "done", lambda: False)()
            ):
                cancel = getattr(self._current_worker, "cancel", None)
                if cancel:
                    cancel()

            # Cancel crew orchestrator if running
            if self._current_crew:
                asyncio.create_task(self._cancel_crew())

            # Clean up agent state to prevent stale tool responses
            if self.agent:
                self.agent.cleanup_after_cancel()

            # Reconnect MCP servers (they may be in a bad state after cancellation)
            if self.mcp_manager:
                asyncio.create_task(self._reconnect_mcp_after_cancel())

    async def _reconnect_mcp_after_cancel(self) -> None:
        """Reconnect MCP servers after cancellation to restore clean state."""
        await asyncio.sleep(0.5)  # Brief delay for cancellation to propagate
        try:
            if self.mcp_manager:
                await self.mcp_manager.reconnect_all()
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to reconnect MCP servers after cancel: %s", e
            )
            try:
                from .notifier import notify

                notify(
                    "warning", f"TUI: failed to reconnect MCP servers after cancel: {e}"
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about MCP reconnect failure"
                )

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_focus_next(self) -> None:
        """Complete suggestion with Tab, or fall back to normal focus cycling."""
        if self._suggestions_visible():
            try:
                suggestions = self.query_one("#cmd-suggestions", CommandSuggestions)
                new_value = suggestions.get_tab_completion()
                if new_value is not None:
                    self._set_chat_input_text(new_value)
                    # Refresh suggestions for the new value
                    suggestions.update_suggestions(new_value)
                    return
            except Exception:
                pass
        super().action_focus_next()

    # ----- History navigation -----

    def _suggestions_visible(self) -> bool:
        try:
            return self.query_one("#cmd-suggestions", CommandSuggestions).display
        except Exception:
            return False

    def action_history_up(self) -> None:
        """Navigate suggestions up, or recall previous input into the chat field."""
        if self._suggestions_visible():
            try:
                self.query_one("#cmd-suggestions", CommandSuggestions).select_previous()
            except Exception:
                pass
            return

        try:
            inp = self._get_chat_input()
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to query chat input for history up: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: history navigation failed: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about history_up failure"
                )
            return

        if not self._cmd_history:
            return

        # Move back but not below zero
        if self._history_index > 0:
            self._history_index -= 1

        inp.text = self._cmd_history[self._history_index]
        self._set_chat_input_text(inp.text)

    def action_history_down(self) -> None:
        """Navigate suggestions down, or recall next input (or clear when at end)."""
        if self._suggestions_visible():
            try:
                self.query_one("#cmd-suggestions", CommandSuggestions).select_next()
            except Exception:
                pass
            return

        try:
            inp = self._get_chat_input()
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to query chat input for history down: %s", e
            )
            try:
                from .notifier import notify

                notify("warning", f"TUI: history navigation failed: {e}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to notify operator about history_down failure"
                )
            return

        if not self._cmd_history:
            return

        if self._history_index < len(self._cmd_history) - 1:
            self._history_index += 1
            inp.text = self._cmd_history[self._history_index]
            self._set_chat_input_text(inp.text)
        else:
            # Past the end: clear input and set index to end
            self._history_index = len(self._cmd_history)
            self._clear_chat_input()
