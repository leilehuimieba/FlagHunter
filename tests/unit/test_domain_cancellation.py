"""A-02 — propagatable cancellation scopes + registry.

The headline acceptance is "取消后动作数为 0": once a token is cancelled, a
cooperative worker performs zero further actions. These guards also pin
idempotent one-way cancellation, subtree propagation, inherited cancellation
for late-born children, and registry cancel-by-id semantics.
"""

from __future__ import annotations

import threading

import pytest

from flaghunter.domain import cancellation as cx
from flaghunter.domain.cancellation import (
    CancellationRegistry,
    CancellationScope,
    CancellationToken,
    TaskCancelled,
)


def test_token_is_one_way_and_idempotent():
    tok = CancellationToken()
    assert tok.cancelled is False
    assert tok.cancel("stop") is True   # first call latches
    assert tok.cancel("again") is False  # subsequent calls are no-ops
    assert tok.cancelled is True
    assert tok.reason == "stop"


def test_raise_if_cancelled():
    tok = CancellationToken()
    tok.raise_if_cancelled()  # no-op while live
    tok.cancel("boom")
    with pytest.raises(TaskCancelled) as exc:
        tok.raise_if_cancelled()
    assert exc.value.reason == "boom"


def test_zero_actions_after_cancel():
    # The acceptance: a cooperative worker does no work once cancelled.
    tok = CancellationToken()
    actions = 0

    def worker():
        nonlocal actions
        for _ in range(1000):
            tok.raise_if_cancelled()  # checked at each action boundary
            actions += 1

    tok.cancel()  # cancel BEFORE the loop starts
    with pytest.raises(TaskCancelled):
        worker()
    assert actions == 0


def test_wait_wakes_immediately_on_cancel():
    tok = CancellationToken()

    def canceller():
        tok.cancel("wake")

    threading.Timer(0.02, canceller).start()
    # Would block up to 5s, but must return True (cancelled) well before that.
    assert tok.wait(timeout=5.0) is True
    assert tok.cancelled is True


def test_scope_propagates_to_children():
    root = CancellationScope(task_id="root")
    child_a = root.child("a")
    child_b = root.child("b")
    grandchild = child_a.child("a1")

    root.cancel("parent-stop")

    assert root.cancelled
    assert child_a.cancelled
    assert child_b.cancelled
    assert grandchild.cancelled
    assert grandchild.token.reason == "parent-stop"


def test_late_born_child_inherits_cancellation():
    root = CancellationScope(task_id="root")
    root.cancel("early")
    # A child created AFTER the parent was cancelled starts cancelled.
    late = root.child("late")
    assert late.cancelled
    with pytest.raises(TaskCancelled):
        late.raise_if_cancelled()


def test_child_cancel_does_not_leak_upward():
    root = CancellationScope(task_id="root")
    child = root.child("c")
    child.cancel("child-only")
    assert child.cancelled
    assert not root.cancelled


def test_registry_cancel_by_id():
    reg = CancellationRegistry()
    scope = reg.open("task-1")
    assert reg.get("task-1") is scope
    assert reg.active_ids() == ["task-1"]

    assert reg.cancel("task-1", "ui-stop") is True
    assert scope.cancelled
    assert scope.token.reason == "ui-stop"
    assert reg.active_ids() == []


def test_registry_cancel_unknown_id_is_false():
    reg = CancellationRegistry()
    assert reg.cancel("nope") is False


def test_registry_open_is_idempotent_and_close_drops():
    reg = CancellationRegistry()
    s1 = reg.open("t")
    s2 = reg.open("t")
    assert s1 is s2
    assert len(reg) == 1
    reg.close("t")
    assert reg.get("t") is None
    assert len(reg) == 0


def test_default_registry_is_process_singleton():
    assert cx.get_cancellation_registry() is cx.get_cancellation_registry()
