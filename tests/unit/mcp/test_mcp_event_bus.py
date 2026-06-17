"""MCP server events flow through the neutral EventBus (invariant I3).

The TUI's MCP observation hook is now a subscriber on the shared bus rather
than a bespoke single callback, but the set_ui_hook / _emit public behavior is
preserved.
"""

import pytest

from pentestagent.mcp.server import mcp_tools as m
from pentestagent.session.event_bus import EventBus


@pytest.fixture(autouse=True)
def _reset_hook():
    m.set_ui_hook(None)
    yield
    m.set_ui_hook(None)


def test_module_bus_is_neutral_event_bus():
    assert isinstance(m.get_event_bus(), EventBus)


def test_emit_delivers_to_registered_hook():
    seen = []
    m.set_ui_hook(lambda event, data: seen.append((event, data)))

    m._emit("task_start", {"task_id": "t1"})
    m._emit("tool_call", {"task_id": "t1", "name": "nmap"})

    assert seen == [
        ("task_start", {"task_id": "t1"}),
        ("tool_call", {"task_id": "t1", "name": "nmap"}),
    ]


def test_clearing_hook_stops_delivery():
    seen = []
    m.set_ui_hook(lambda event, data: seen.append(event))
    m._emit("first", {})
    m.set_ui_hook(None)
    m._emit("second", {})

    assert seen == ["first"]


def test_replacing_hook_unsubscribes_previous():
    a, b = [], []
    m.set_ui_hook(lambda e, d: a.append(e))
    m.set_ui_hook(lambda e, d: b.append(e))  # replaces the first

    m._emit("evt", {})

    assert a == []  # old hook unsubscribed
    assert b == ["evt"]


def test_faulty_hook_does_not_break_emit():
    def boom(event, data):
        raise RuntimeError("hook blew up")

    m.set_ui_hook(boom)
    # Must not raise — neutral bus isolates subscriber errors.
    m._emit("evt", {"x": 1})
