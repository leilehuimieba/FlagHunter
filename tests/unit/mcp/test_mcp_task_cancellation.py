"""A-04 — cancel_task really interrupts a running MCP task (F-02).

Before A-04, ``cancel_task`` only flipped ``entry.status``; a background task
suspended on a long ``await`` (the CTF dispatcher) kept running to completion.
These tests drive a task whose worker is parked on a long ``await`` that the
cooperative status poll can never reach, and prove that cancel_task now cancels
the stored asyncio handle so the task ends promptly as ``cancelled`` — and that
the cancellation registry scope is opened while running and dropped after.
"""

from __future__ import annotations

import asyncio

import pytest

from flaghunter.mcp.server import mcp_tools
from flaghunter.domain.cancellation import get_cancellation_registry


class _ParkedAgent:
    """Agent whose run_mcp parks on a long await before ever yielding.

    This models the CTF dispatcher's long await: the driver loop's cooperative
    ``entry.status == 'cancelled'`` poll (which only runs between yields) can
    never fire, so only real asyncio cancellation can stop it.
    """

    def __init__(self) -> None:
        self.cleaned_up = False
        self.runtime = None

    async def run_mcp(self, _task):
        await asyncio.sleep(100)  # never completes within the test
        yield  # pragma: no cover - unreachable once cancelled

    def cleanup_after_cancel(self) -> None:
        self.cleaned_up = True


def _make_entry(agent) -> mcp_tools.TaskEntry:
    return mcp_tools.TaskEntry(
        id="cxl-test-1",
        task="park forever",
        status="pending",
        created_at="2026-07-31T00:00:00",
        agent=agent,
        mode="agent",
    )


@pytest.mark.asyncio
async def test_cancel_task_interrupts_a_parked_await():
    agent = _ParkedAgent()
    entry = _make_entry(agent)
    mcp_tools._tasks[entry.id] = entry

    # Schedule exactly as run_task_async does: store the driving handle.
    handle = asyncio.create_task(mcp_tools._drive_task(entry))
    mcp_tools._task_handles[entry.id] = handle
    try:
        # Let the task reach the parked await and register its scope.
        await asyncio.sleep(0.02)
        assert entry.status == "running"
        assert entry.id in get_cancellation_registry()

        result = await mcp_tools.cancel_task({"task_id": entry.id})
        assert "cancelled" in result.lower()

        # The parked await must unwind promptly — no 100s wait.
        await asyncio.wait_for(handle, timeout=1.0)
        assert entry.status == "cancelled"
        assert agent.cleaned_up is True
        # Scope + handle cleaned up once terminal.
        assert entry.id not in mcp_tools._task_handles
        assert get_cancellation_registry().get(entry.id) is None
    finally:
        mcp_tools._tasks.pop(entry.id, None)
        mcp_tools._task_handles.pop(entry.id, None)
        get_cancellation_registry().close(entry.id)


@pytest.mark.asyncio
async def test_cancel_task_latches_registry_token():
    agent = _ParkedAgent()
    entry = _make_entry(agent)
    mcp_tools._tasks[entry.id] = entry
    handle = asyncio.create_task(mcp_tools._drive_task(entry))
    mcp_tools._task_handles[entry.id] = handle
    try:
        await asyncio.sleep(0.02)
        scope = get_cancellation_registry().get(entry.id)
        assert scope is not None and not scope.cancelled

        await mcp_tools.cancel_task({"task_id": entry.id})
        # The token carries the reason even before the finally-close runs.
        assert scope.cancelled
        assert scope.token.reason == "user_cancel"
        await asyncio.wait_for(handle, timeout=1.0)
    finally:
        mcp_tools._tasks.pop(entry.id, None)
        mcp_tools._task_handles.pop(entry.id, None)
        get_cancellation_registry().close(entry.id)


@pytest.mark.asyncio
async def test_cancel_task_on_unknown_id_is_reported():
    result = await mcp_tools.cancel_task({"task_id": "does-not-exist"})
    assert "no task" in result.lower()


@pytest.mark.asyncio
async def test_cancel_task_on_terminal_task_is_noop():
    agent = _ParkedAgent()
    entry = _make_entry(agent)
    entry.status = "done"
    mcp_tools._tasks[entry.id] = entry
    try:
        result = await mcp_tools.cancel_task({"task_id": entry.id})
        assert "already" in result.lower()
        assert entry.status == "done"
    finally:
        mcp_tools._tasks.pop(entry.id, None)
