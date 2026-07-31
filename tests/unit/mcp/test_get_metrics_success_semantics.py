"""F-05 / A-06 — MCP ``get_metrics`` success must be proof-backed, not ``done``.

A finished agent loop (``status == "done"``) is not a solve. ``get_metrics``
must count a *verified solve* only when the dispatcher reported a proof-backed
``SolveResult.success`` (recorded on ``TaskEntry.verifiedSuccess``), and must
not surface a "success_rate = done/total" number that inflates success.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from flaghunter.mcp.server import mcp_tools


def _entry(entry_id: str, status: str, verified: bool | None) -> mcp_tools.TaskEntry:
    return mcp_tools.TaskEntry(
        id=entry_id,
        task="solve challenge",
        status=status,
        created_at="2026-07-31T00:00:00+00:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        mode="ctf",
        verifiedSuccess=verified,
    )


@pytest.fixture(autouse=True)
def _clean_tasks():
    saved = dict(mcp_tools._tasks)
    mcp_tools._tasks.clear()
    try:
        yield
    finally:
        mcp_tools._tasks.clear()
        mcp_tools._tasks.update(saved)


@pytest.mark.asyncio
async def test_done_without_proof_is_not_a_verified_solve():
    # Two CTF tasks finished the loop; only one produced a verified proof.
    mcp_tools._tasks["a"] = _entry("a", "done", verified=True)
    mcp_tools._tasks["b"] = _entry("b", "done", verified=False)

    out = await mcp_tools.get_metrics({})

    assert "completed:          2" in out  # both loops finished
    assert "solve_tasks:        2" in out
    assert "verified_solves:    1" in out
    assert "verified_solve_rate:50.0%" in out
    # The misleading done/total "success_rate" line must be gone.
    assert "success_rate:" not in out


@pytest.mark.asyncio
async def test_non_solve_tasks_do_not_count_as_solve_tasks():
    # A generic (non-CTF) task that finished carries verifiedSuccess=None and
    # must not be treated as a solve task at all.
    mcp_tools._tasks["a"] = mcp_tools.TaskEntry(
        id="a",
        task="enumerate",
        status="done",
        created_at="2026-07-31T00:00:00+00:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        verifiedSuccess=None,
    )
    mcp_tools._tasks["b"] = _entry("b", "done", verified=True)

    out = await mcp_tools.get_metrics({})

    assert "completed:          2" in out
    assert "solve_tasks:        1" in out
    assert "verified_solves:    1" in out
    assert "verified_solve_rate:100.0%" in out


@pytest.mark.asyncio
async def test_no_solve_tasks_reports_na():
    mcp_tools._tasks["a"] = mcp_tools.TaskEntry(
        id="a",
        task="enumerate",
        status="done",
        created_at="2026-07-31T00:00:00+00:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        verifiedSuccess=None,
    )

    out = await mcp_tools.get_metrics({})

    assert "solve_tasks:        0" in out
    assert "verified_solve_rate:n/a" in out
