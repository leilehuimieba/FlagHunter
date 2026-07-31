"""A-03 — stopping a web task really interrupts its coroutine (F-01).

Before A-03, the /stop handler flipped ``status`` to "stopped" and persisted;
the daemon thread kept running the agent loop / CTF dispatcher. These tests
prove the managed task runner now cancels the task's coroutine across the
thread boundary, so a coroutine parked on a long await unwinds promptly and the
cancellation-registry token is latched with the stop reason.
"""

from __future__ import annotations

import asyncio
import threading
import time

from flaghunter.interface import web_server
from flaghunter.domain.cancellation import get_cancellation_registry


def _run_parked_task(task_id: str, started: threading.Event, ended: threading.Event):
    """Mimic _run_agent_task's managed runner around a coroutine that parks.

    Uses the exact register/cancel/close seam _run_agent_task uses so the test
    exercises the real cross-thread cancellation path, not a reimplementation.
    """

    async def _park():
        started.set()
        await asyncio.sleep(30)  # long await the cooperative poll can't reach

    loop = asyncio.new_event_loop()
    get_cancellation_registry().open(task_id)
    handle = loop.create_task(_park())
    web_server._register_task_runner(task_id, loop, handle)
    outcome = {"cancelled": False}
    try:
        loop.run_until_complete(handle)
    except asyncio.CancelledError:
        outcome["cancelled"] = True
    finally:
        web_server._unregister_task_runner(task_id)
        loop.close()
        get_cancellation_registry().close(task_id)
        ended.set()
    return outcome


def test_cancel_web_task_interrupts_across_threads():
    task_id = "web-cxl-1"
    started = threading.Event()
    ended = threading.Event()
    outcome: dict = {}

    def target():
        outcome.update(_run_parked_task(task_id, started, ended))

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    try:
        assert started.wait(timeout=2.0), "task never started"
        # Give the loop a beat to actually enter the parked await.
        time.sleep(0.05)

        t0 = time.monotonic()
        signalled = web_server._cancel_web_task(task_id, "user_stop")
        assert signalled is True

        assert ended.wait(timeout=2.0), "parked await was not interrupted"
        elapsed = time.monotonic() - t0
        assert elapsed < 5.0  # nowhere near the 30s the await would have taken
        assert outcome.get("cancelled") is True
    finally:
        worker.join(timeout=2.0)
        get_cancellation_registry().close(task_id)
        web_server._unregister_task_runner(task_id)


def test_cancel_web_task_latches_registry_token():
    task_id = "web-cxl-2"
    started = threading.Event()
    ended = threading.Event()

    def target():
        _run_parked_task(task_id, started, ended)

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    try:
        assert started.wait(timeout=2.0)
        time.sleep(0.05)
        # Grab the scope while the task is live and confirm the reason latches.
        scope = get_cancellation_registry().get(task_id)
        assert scope is not None and not scope.cancelled

        web_server._cancel_web_task(task_id, "user_stop")
        assert scope.cancelled
        assert scope.token.reason == "user_stop"
        assert ended.wait(timeout=2.0)
    finally:
        worker.join(timeout=2.0)
        get_cancellation_registry().close(task_id)
        web_server._unregister_task_runner(task_id)


def test_cancel_web_task_with_no_runner_is_false():
    # Nothing registered → latches the token but reports nothing to interrupt.
    assert web_server._cancel_web_task("never-ran", "user_stop") is False
    get_cancellation_registry().close("never-ran")
