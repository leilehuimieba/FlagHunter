"""Tests for the notifier bridge (lives in session/, shimmed from interface/).

The general-notification channel (notify/register_callback) rides on the
neutral EventBus (invariant I3); the spawn/despawn/wake-up control hooks stay
as plain callbacks with return-value semantics. The module was moved to
flaghunter.session.notifier (H8) so non-interface layers can import it without
a reverse dependency; interface.notifier is now a compat shim (see the shim
re-export test below).
"""

import pytest

from flaghunter.session import notifier
from flaghunter.session.event_bus import EventBus


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    notifier.register_callback(None)
    monkeypatch.setattr(notifier, "_spawn_terminal_cb", None)
    monkeypatch.setattr(notifier, "_despawn_terminal_cb", None)
    monkeypatch.setattr(notifier, "_agent_wake_up_cb", None)
    yield
    notifier.register_callback(None)


def test_notify_bus_is_neutral_event_bus():
    assert isinstance(notifier.get_notify_bus(), EventBus)


def test_notify_delivers_to_registered_callback():
    seen = []
    notifier.register_callback(lambda level, message: seen.append((level, message)))

    notifier.notify("info", "hello")
    notifier.notify("error", "boom")

    assert seen == [("info", "hello"), ("error", "boom")]


def test_clearing_callback_falls_back_to_logging(caplog):
    notifier.register_callback(None)
    with caplog.at_level("INFO", logger="flaghunter.notifier"):
        notifier.notify("info", "fallback-msg")
    assert "fallback-msg" in caplog.text


def test_replacing_callback_unsubscribes_previous():
    a, b = [], []
    notifier.register_callback(lambda l, m: a.append(m))
    notifier.register_callback(lambda l, m: b.append(m))

    notifier.notify("info", "x")

    assert a == []
    assert b == ["x"]


def test_faulty_callback_does_not_break_notify():
    def boom(level, message):
        raise RuntimeError("callback blew up")

    notifier.register_callback(boom)
    # Must not raise — adapter logs the exception, bus isolates it.
    notifier.notify("info", "x")


def test_spawn_terminal_returns_false_without_tui():
    assert notifier.spawn_terminal(3, "child-1") is False


def test_spawn_terminal_returns_true_with_callback():
    calls = []
    notifier.register_spawn_terminal_callback(lambda fd, label: calls.append((fd, label)))
    assert notifier.spawn_terminal(7, "child-2") is True
    assert calls == [(7, "child-2")]


def test_interface_shim_reexports_same_singletons():
    """interface.notifier is a backwards-compat shim over session.notifier —
    the re-exported names must be the SAME objects so UI subscribers and agent
    emitters share one notify bus (H8)."""
    from flaghunter.interface import notifier as shim

    assert shim.notify is notifier.notify
    assert shim.get_notify_bus() is notifier.get_notify_bus()
    assert shim.spawn_terminal is notifier.spawn_terminal
    assert shim.register_callback is notifier.register_callback
