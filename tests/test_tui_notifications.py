import pytest

from pentestagent.interface import notifier
from pentestagent.interface.tui import PentestAgentTUI
from pentestagent.workspaces.manager import WorkspaceManager


def test_tui_set_target_persist_failure_emits_notification(monkeypatch, tmp_path):
    captured = []

    def cb(level, message):
        captured.append((level, message))

    notifier.register_callback(cb)

    # Make set_last_target raise
    def bad_set_last(self, name, value):
        raise RuntimeError("disk error")

    monkeypatch.setattr(WorkspaceManager, "set_last_target", bad_set_last)

    tui = PentestAgentTUI()
    # Call the internal method to set target
    tui._set_target("/target 10.0.0.1")

    assert len(captured) >= 1
    assert any("Failed to persist last target" in m for _, m in captured)


def test_tui_apply_target_display_failure_emits_notification(monkeypatch):
    captured = []

    def cb(level, message):
        captured.append((level, message))

    notifier.register_callback(cb)

    tui = PentestAgentTUI()

    # Make _apply_target_display raise
    def bad_apply(self, target):
        raise RuntimeError("ui update failed")

    monkeypatch.setattr(PentestAgentTUI, "_apply_target_display", bad_apply)

    tui._set_target("/target 1.2.3.4")

    assert len(captured) >= 1
    assert any("Failed to update target display" in m or "Failed to update target" in m for _, m in captured)
