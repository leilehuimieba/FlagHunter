from __future__ import annotations

from types import SimpleNamespace

import pytest

from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher, SolveResult
from pentestagent.agents.pa_agent.coordinator import CTFCoordinator


class _Runtime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])


class _FakeCoordinator:
    def __init__(self, result: SolveResult):
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def execute(
        self,
        dispatcher,
        *,
        target: str,
        goal: str,
        type: str | None = None,
        hint: str | None = None,
        submit_profile: dict[str, object] | None = None,
        challenge_context: dict[str, object] | None = None,
        run_id: str | None = None,
        ledger_root=None,
        checkpoint_root=None,
    ):
        self.calls.append(
            {
                "dispatcher": dispatcher,
                "target": target,
                "goal": goal,
                "type": type,
                "hint": hint,
                "submit_profile": submit_profile,
                "challenge_context": challenge_context,
                "run_id": run_id,
                "ledger_root": ledger_root,
                "checkpoint_root": checkpoint_root,
            }
        )
        return self.result


@pytest.mark.asyncio
async def test_dispatcher_run_delegates_to_coordinator_execute():
    dispatcher = CTFTaskDispatcher(runtime=_Runtime(), progress_callback=None)
    sentinel = SolveResult(success=False, reason="delegated-by-coordinator")
    fake = _FakeCoordinator(sentinel)
    dispatcher.coordinator = fake

    result = await dispatcher.run(
        target="127.0.0.1:3000",
        goal=" recover flag ",
        type="web",
        hint=" local",
        submit_profile={"platform": "ctf"},
        challenge_context={"artifactPaths": ["C:/tmp/app.zip"]},
        run_id="run-123",
    )

    assert result is sentinel
    assert len(fake.calls) == 1
    assert fake.calls[0]["dispatcher"] is dispatcher
    assert fake.calls[0]["target"] == "127.0.0.1:3000"
    assert fake.calls[0]["goal"] == " recover flag "
    assert fake.calls[0]["type"] == "web"
    assert fake.calls[0]["hint"] == " local"


@pytest.mark.asyncio
async def test_coordinator_execute_calls_dispatcher_run_without_redelegation():
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=True, flag="flag{ok}", reason="inner-run")
    captured: dict[str, object] = {}

    class _Dispatcher:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return sentinel

    result = await coordinator.execute(
        _Dispatcher(),
        target="127.0.0.1:3000",
        goal="goal",
        type="auto",
        hint="",
        submit_profile=None,
        challenge_context={"artifactPaths": []},
        run_id="run-abc",
        ledger_root=None,
        checkpoint_root=None,
    )

    assert result is sentinel
    assert captured["_delegate_to_coordinator"] is False
    assert captured["target"] == "http://127.0.0.1:3000"
    assert captured["goal"] == "goal"


@pytest.mark.asyncio
async def test_coordinator_normalizes_public_run_inputs_before_dispatch():
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=False, reason="normalized")
    captured: dict[str, object] = {}

    class _Dispatcher:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return sentinel

    result = await coordinator.execute(
        _Dispatcher(),
        target="127.0.0.1:3000/",
        goal="   ",
        type="",
        hint="  local hint  ",
        submit_profile=None,
        challenge_context={
            "challengePath": "   ",
            "artifactPaths": [" C:/tmp/app.zip ", "", "C:/tmp/app.zip"],
        },
        run_id="run-normalize",
        ledger_root=None,
        checkpoint_root=None,
    )

    assert result is sentinel
    assert captured["target"] == "http://127.0.0.1:3000"
    assert captured["goal"] == "拿到flag"
    assert captured["type"] == "auto"
    assert captured["hint"] == "local hint"
    assert captured["challenge_context"] == {
        "challengePath": None,
        "artifactPaths": ["C:/tmp/app.zip"],
    }
