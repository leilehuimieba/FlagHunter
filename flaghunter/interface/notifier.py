"""Simple notifier bridge for UI notifications.

Modules can call `notify(level, message)` to emit operator-visible
notifications. A UI (TUI) may register a callback via `register_callback()`
to receive notifications and display them. If no callback is registered,
notifications are logged.

A second channel — `spawn_terminal` / `register_spawn_terminal_callback` —
lets agent code request that the TUI open an EmbeddedTerminal widget for a
child agent's PTY output.

A third channel — `despawn_terminal` / `register_despawn_terminal_callback` —
lets agent code request that the TUI remove a previously opened terminal.
"""

import logging
from typing import Any, Callable, Optional

from ..session.event_bus import EventBus

# The general-notification channel rides on the shared neutral EventBus
# (architecture invariant I3 — single event-source implementation). The
# notify(level, message) / register_callback API is preserved; internally the
# message is published as a "notify" event and the UI callback is a subscriber.
# The spawn/despawn/wake-up channels below are targeted control hooks with
# return-value semantics (not broadcasts), so they stay as plain callbacks.
_notify_bus = EventBus()
_callback: Optional[Callable[[str, Any], None]] = None
_callback_unsub: Optional[Callable[[], None]] = None
_spawn_terminal_cb: Optional[Callable[[int, str], None]] = None
_despawn_terminal_cb: Optional[Callable[[str], None]] = None
_agent_wake_up_cb: Optional[Callable[[], None]] = None


def get_notify_bus() -> EventBus:
    """Return the neutral event bus carrying notify() events (observers/tests)."""
    return _notify_bus


def register_callback(cb: Optional[Callable[[str, Any], None]]) -> None:
    """Register (or clear) the notification callback by (un)subscribing it on
    the neutral bus. Single-subscriber semantics preserved.

    Callback receives (level, message).
    """
    global _callback, _callback_unsub
    if _callback_unsub is not None:
        _callback_unsub()
        _callback_unsub = None
    _callback = cb
    if cb is not None:
        def _adapter(event) -> None:
            try:
                cb(event.data["level"], event.data["message"])
            except Exception:
                logging.getLogger(__name__).exception("Notifier callback failed")

        _callback_unsub = _notify_bus.subscribe(_adapter)


def notify(level: str, message: Any) -> None:
    """Emit a notification. If a UI callback is subscribed, publish to the bus;
    otherwise log."""
    if _notify_bus.subscriber_count > 0:
        _notify_bus.emit("notify", {"level": level, "message": message}, source="notifier")
        return

    # Fallback to logging
    log = logging.getLogger("flaghunter.notifier")
    display_message = message if isinstance(message, str) else repr(message)
    if level.lower() in ("error", "critical"):
        log.error(display_message)
    elif level.lower() in ("warn", "warning"):
        log.warning(display_message)
    else:
        log.info(display_message)


def register_spawn_terminal_callback(cb: Callable[[int, str], None]) -> None:
    """Register a callback so the TUI can create an EmbeddedTerminal widget.

    Callback receives (master_fd, label).
    """
    global _spawn_terminal_cb
    _spawn_terminal_cb = cb


def spawn_terminal(master_fd: int, label: str) -> bool:
    """Ask the TUI to open an EmbeddedTerminal for *master_fd*.

    Returns True if the TUI accepted the request, False if no TUI is active
    (caller should fall back to opening a new terminal window).
    """
    global _spawn_terminal_cb
    if _spawn_terminal_cb:
        try:
            _spawn_terminal_cb(master_fd, label)
            return True
        except Exception:
            logging.getLogger(__name__).exception("spawn_terminal callback failed")
    return False


def register_despawn_terminal_callback(cb: Callable[[str], None]) -> None:
    """Register a callback so the TUI can remove a CollapsibleTerminal widget.

    Callback receives (label,).
    """
    global _despawn_terminal_cb
    _despawn_terminal_cb = cb


def despawn_terminal(label: str) -> None:
    """Ask the TUI to close and remove the terminal identified by *label*."""
    global _despawn_terminal_cb
    if _despawn_terminal_cb:
        try:
            _despawn_terminal_cb(label)
        except Exception:
            logging.getLogger(__name__).exception("despawn_terminal callback failed")


def register_agent_wake_up_callback(cb: Callable[[], None]) -> None:
    """Register a callback that the TUI uses to restart the agent loop.

    Called when a child-agent push notification arrives while the parent
    agent is idle.  The TUI callback should invoke agent.wake_up() and
    route its output to the chat panel.
    """
    global _agent_wake_up_cb
    _agent_wake_up_cb = cb


def agent_wake_up() -> None:
    """Signal the TUI to resume the parent agent loop (idle → thinking).

    If no TUI callback is registered (headless mode), this is a no-op;
    the injected conversation_history message will be processed the next
    time the agent is invoked manually.
    """
    global _agent_wake_up_cb
    if _agent_wake_up_cb:
        try:
            _agent_wake_up_cb()
        except Exception:
            logging.getLogger(__name__).exception("agent_wake_up callback failed")
