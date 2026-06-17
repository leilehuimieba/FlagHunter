from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from flaghunter.interface.tui import FlagHunterTUI


@pytest.mark.asyncio
async def test_handle_retro_command_lists_unresolved(monkeypatch):
    messages: list[str] = []
    tui = FlagHunterTUI()
    tui._add_system = messages.append  # type: ignore[method-assign]

    monkeypatch.setattr(
        "flaghunter.knowledge.retrospective.get_unresolved_entries",
        lambda: [
            {
                "id": 1,
                "category": "plan_inefficient",
                "timestamp": "2026-05-23T10:00:00",
                "description": "three failures",
                "suggestion": "re-detect type",
            }
        ],
    )

    await tui._handle_retro_command("/retro")

    assert messages
    assert "[CTF Retrospective] 1 unresolved items" in messages[0]
    assert "re-detect type" in messages[0]


@pytest.mark.asyncio
async def test_handle_retro_command_resolve(monkeypatch):
    messages: list[str] = []
    tui = FlagHunterTUI()
    tui._add_system = messages.append  # type: ignore[method-assign]
    marker = MagicMock()

    monkeypatch.setattr(
        "flaghunter.knowledge.retrospective.mark_resolved",
        marker,
    )

    await tui._handle_retro_command("/retro resolve 3")

    marker.assert_called_once_with(3)
    assert "resolved" in messages[0].lower()
