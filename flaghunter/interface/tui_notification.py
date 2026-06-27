"""Notifier-bus display callbacks mixed into FlagHunterTUI (债池五波·TUI 刀 23, god-class).

Extracted from tui.py. The two notifier-bus sinks: ``_show_notification`` renders a
toast/log line for a given level+message, and ``_notifier_callback`` is the callback
the agent notifier invokes (re-dispatched onto the Textual loop). They call stay-behind
helpers (``self._add_system`` / ``self.call_from_thread``) resolved at runtime through
the FlagHunterTUI instance MRO; stay-behind registration of ``_notifier_callback`` on the
notifier resolves the same way. Module-level deps only: ``asyncio`` / ``logging`` / ``Any``.
No decorators.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any


class NotificationMixin:
    """Notifier-bus display callbacks for FlagHunterTUI."""

    def _show_notification(self, level: str, message: Any) -> None:
        """Display a short operator-visible notification in the chat area."""
        try:
            if level.lower() == "flag_found":
                self._flag_banner = message
                self._add_system(f"🚩 FLAG FOUND: {message}")
                self._update_header()
                return
            if level.lower() == "tool_install_required":
                payload = message if isinstance(message, dict) else {"message": str(message)}
                self._pending_tool_install = payload
                self._add_system(self._format_tool_install_panel(payload))
                self._set_status("waiting", "agent" if self._mode == "agent" else self._mode)
                return
            # Prepend a concise system message so it is visible in the chat
            prefix = "[!]" if level.lower() in ("error", "critical") else "[!]"
            self._add_system(f"{prefix} {message}")
            # Set status bar to error briefly for emphasis
            if level.lower() in ("error", "critical"):
                self._set_status("error")
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to show notification in TUI: %s", e
            )

    def _notifier_callback(self, level: str, message: Any) -> None:
        """Callback wired to `flaghunter.interface.notifier`.

        This will be registered on mount so other modules can emit notifications.
        """
        try:
            try:
                asyncio.get_running_loop()
                # Already on the app's event loop (e.g. called from an asyncio task).
                # call_from_thread would raise here — call directly instead.
                self._show_notification(level, message)
                return
            except RuntimeError:
                pass
            # Called from a worker thread — use call_from_thread.
            if hasattr(self, "call_from_thread"):
                self.call_from_thread(self._show_notification, level, message)
            else:
                self._show_notification(level, message)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Exception in notifier callback handling: %s", e
            )
