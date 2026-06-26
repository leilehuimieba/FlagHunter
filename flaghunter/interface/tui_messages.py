"""Textual Message subclasses for FlagHunterTUI (debt ledger 第五波·TUI 刀1).

Extracted from tui.py. These are thin cross-task UI-event messages posted via
``post_message`` / handled via ``@on(...)`` inside FlagHunterTUI. Each only
inherits textual ``Message`` and stores its payload in ``__init__`` — zero
dependency on any other tui widget/screen or on FlagHunterTUI itself — so they
are trivially self-contained. tui.py re-imports them so the stay-behind
producers/handlers inside FlagHunterTUI resolve unchanged.
"""

from __future__ import annotations

from textual.message import Message


class MCPTaskEvent(Message):
    """Posted by on_mcp_event() so Textual handles the UI update safely."""

    def __init__(self, event: str, data: dict) -> None:
        super().__init__()
        self.event = event
        self.data = data


class SpawnTerminalMessage(Message):
    """Posted when a child agent requests an EmbeddedTerminal widget."""

    def __init__(self, master_fd: int, label: str) -> None:
        super().__init__()
        self.master_fd = master_fd
        self.label = label


class DespawnTerminalMessage(Message):
    """Posted when a child agent has been despawned and its terminal should be removed."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label


class ChildAgentWakeUpMessage(Message):
    """Posted (thread-safely) when a child async task completes and the parent
    agent is idle.  Triggers _run_wake_up_mode() through Textual's message loop
    so we never call @work methods from an arbitrary async context."""
