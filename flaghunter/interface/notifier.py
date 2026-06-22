"""Compatibility shim — the notifier now lives in ``flaghunter.session.notifier``.

Kept so existing ``from flaghunter.interface.notifier import ...`` and TUI-local
``from .notifier import ...`` call sites keep working unchanged. Non-interface
layers (agents/tools/runtime/knowledge/workspaces) should import from
``flaghunter.session.notifier`` directly to avoid a reverse dependency on the
entry-point layer. All names below resolve to the SAME module-level singletons
(one shared notify bus / callbacks), so mixing the two import paths is safe.
See H8.
"""

from ..session.notifier import (  # noqa: F401
    agent_wake_up,
    despawn_terminal,
    get_notify_bus,
    notify,
    register_agent_wake_up_callback,
    register_callback,
    register_despawn_terminal_callback,
    register_spawn_terminal_callback,
    spawn_terminal,
)

__all__ = [
    "notify",
    "register_callback",
    "get_notify_bus",
    "spawn_terminal",
    "register_spawn_terminal_callback",
    "despawn_terminal",
    "register_despawn_terminal_callback",
    "agent_wake_up",
    "register_agent_wake_up_callback",
]
