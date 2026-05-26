from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pentestagent.agents.crew.swarm_bridge import (
    build_ctf_dispatcher_worker_runner,
    run_ctf_dispatcher_worker,
)
from pentestagent.agents.pa_agent.ctf_state import CTFState


class _FakeDispatcher:
    def __init__(self, *, success: bool, flag: str | None = None):
        self._success = success
        self._flag = flag
        self.calls: list[dict[str, str]] = []
        self.state = CTFState(target="http://ctf.local", goal="拿到flag")
        self.state.add_observation(
            "worker_observation",
            "scan /backup",
            source="dispatcher",
            metadata={"path": "/backup"},
        )
        self.state.add_flag(
            "flag{candidate_from_dispatcher}",
            level="candidate",
            evidence_source="source-leak",
            rationale="found in source",
            requires_followup=True,
        )
        if flag:
            self.state.add_flag(
                flag,
                level="verified",
                evidence_source="dispatcher",
                rationale="final result",
                confidence=1.0,
            )

    async def run(self, *, target: str, goal: str, type: str, hint: str):
        self.calls.append(
            {"target": target, "goal": goal, "type": type, "hint": hint}
        )
        return SimpleNamespace(
            success=self._success,
            flag=self._flag,
            reason="dispatcher-finished",
        )


@pytest.mark.asyncio
async def test_run_ctf_dispatcher_worker_returns_state_diff():
    dispatcher = _FakeDispatcher(success=False, flag=None)

    result = await run_ctf_dispatcher_worker(
        dispatcher,
        target="http://ctf.local",
        goal="拿到flag",
        chtype="web",
        hint="",
        worker_id="worker-1",
        worker_type="recon",
        cancel_event=None,
    )

    assert result["worker_id"] == "worker-1"
    assert result["worker_type"] == "recon"
    assert result["verified_flag"] is None
    assert result["candidate_flags"] == ["flag{candidate_from_dispatcher}"]
    assert result["runtime_flags"] == []
    assert result["state_diff"]["observations"][0]["kind"] == "worker_observation"
    assert dispatcher.calls[0]["type"] == "web"


@pytest.mark.asyncio
async def test_build_ctf_dispatcher_worker_runner_wraps_factory():
    created: list[_FakeDispatcher] = []

    def _factory():
        dispatcher = _FakeDispatcher(success=True, flag="flag{crew_bridge_ok}")
        created.append(dispatcher)
        return dispatcher

    runner = build_ctf_dispatcher_worker_runner(
        _factory,
        target="http://ctf.local",
        goal="拿到flag",
        chtype="sqli",
        hint="from-crew",
    )

    result = await runner(
        {"worker_id": "worker-2", "worker_type": "exploit"},
        shared_state=CTFState(target="http://ctf.local", goal="拿到flag"),
        cancel_event=asyncio.Event(),
    )

    assert len(created) == 1
    assert result["success"] is True
    assert result["verified_flag"] == "flag{crew_bridge_ok}"
    assert result["runtime_flags"] == []
    assert result["state_diff"]["verified_flags"] == ["flag{crew_bridge_ok}"]
    assert created[0].calls[0]["hint"] == "from-crew"
