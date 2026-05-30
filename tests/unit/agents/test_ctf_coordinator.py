from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher, SolveResult
from pentestagent.agents.pa_agent.coordinator import CTFCoordinator


class _Runtime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])


class _BootstrapCapableDispatcher:
    def __init__(self, result: SolveResult):
        self._result = result
        self._notes_log = []
        self._challenge_context = None
        self._ledger_run_id = None
        self._current_fingerprint = None
        self._memory_match_ids: list[str] = []
        self._pending_wrong_flag_feedback: list[str] = []
        self._exhausted_visit_url_targets: set[str] = set()
        self.reasoning_layer = SimpleNamespace(degradation_events=[])
        self.state = None
        self.applied_submit_profile = None
        self.recorded_events: list[tuple[str, dict[str, object]]] = []
        self.written_checkpoints: list[tuple[str, dict[str, object]]] = []

    def _setup_session_ledger(self, *, run_id=None, ledger_root=None):
        self._ledger_run_id = run_id

    def _setup_artifact_registry(self, *, run_id=None, registry_root=None):
        self._artifact_registry_args = (run_id, registry_root)

    def _setup_checkpoint_store(self, *, run_id=None, checkpoint_root=None):
        self._checkpoint_store_args = (run_id, checkpoint_root)

    def _apply_submit_profile(self, submit_profile):
        self.applied_submit_profile = submit_profile

    async def _start_failover_monitor_if_available(self):
        return None

    def _record_session_event(self, event_type: str, payload: dict[str, object]):
        self.recorded_events.append((event_type, dict(payload)))

    def _write_checkpoint(self, label: str, payload: dict[str, object]):
        self.written_checkpoints.append((label, dict(payload)))

    async def run(self, **kwargs):
        self._captured = dict(kwargs)
        return self._result


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
    dispatcher = _BootstrapCapableDispatcher(sentinel)

    result = await coordinator.execute(
        dispatcher,
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
    assert dispatcher._captured["_delegate_to_coordinator"] is False
    assert dispatcher._captured["target"] == "http://127.0.0.1:3000"
    assert dispatcher._captured["goal"] == "goal"


@pytest.mark.asyncio
async def test_coordinator_normalizes_public_run_inputs_before_dispatch():
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=False, reason="normalized")
    dispatcher = _BootstrapCapableDispatcher(sentinel)

    result = await coordinator.execute(
        dispatcher,
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
    assert dispatcher._captured["target"] == "http://127.0.0.1:3000"
    assert dispatcher._captured["goal"] == "拿到flag"
    assert dispatcher._captured["type"] == "auto"
    assert dispatcher._captured["hint"] == "local hint"
    assert dispatcher._captured["challenge_context"] == {
        "challengePath": None,
        "artifactPaths": ["C:/tmp/app.zip"],
    }


@pytest.mark.asyncio
async def test_coordinator_bootstraps_dispatcher_before_inner_run(tmp_path: Path):
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=False, reason="bootstrapped")
    captured: dict[str, object] = {}

    class _Dispatcher:
        def __init__(self):
            self._notes_log = ["stale"]
            self._challenge_context = None
            self._ledger_run_id = None
            self._current_fingerprint = "stale"
            self._memory_match_ids = ["stale"]
            self._pending_wrong_flag_feedback = ["stale"]
            self._exhausted_visit_url_targets = {"stale"}
            self.reasoning_layer = SimpleNamespace(degradation_events=["stale"])
            self.state = None
            self.artifact_setup_calls: list[tuple[str | None, object]] = []
            self.checkpoint_setup_calls: list[tuple[str | None, object]] = []
            self.applied_submit_profile = None
            self.monitor_started = False

        def _setup_session_ledger(self, *, run_id=None, ledger_root=None):
            self._ledger_run_id = run_id or "generated-run-id"
            self.ledger_root = ledger_root

        def _setup_artifact_registry(self, *, run_id=None, registry_root=None):
            self.artifact_setup_calls.append((run_id, registry_root))

        def _setup_checkpoint_store(self, *, run_id=None, checkpoint_root=None):
            self.checkpoint_setup_calls.append((run_id, checkpoint_root))

        def _apply_submit_profile(self, submit_profile):
            self.applied_submit_profile = submit_profile

        async def _start_failover_monitor_if_available(self):
            self.monitor_started = True

        def _record_session_event(self, event_type: str, payload: dict[str, object]):
            return None

        def _write_checkpoint(self, label: str, payload: dict[str, object]):
            return None

        async def run(self, **kwargs):
            captured.update(kwargs)
            captured["notes_log"] = list(self._notes_log)
            captured["challenge_context"] = dict(self._challenge_context or {})
            captured["ledger_run_id"] = self._ledger_run_id
            captured["state_target"] = getattr(self.state, "target", None)
            captured["state_goal"] = getattr(self.state, "goal", None)
            captured["current_fingerprint"] = self._current_fingerprint
            captured["memory_match_ids"] = list(self._memory_match_ids)
            captured["pending_wrong_flag_feedback"] = list(self._pending_wrong_flag_feedback)
            captured["exhausted_visit_url_targets"] = set(self._exhausted_visit_url_targets)
            captured["degradation_events"] = list(self.reasoning_layer.degradation_events)
            captured["artifact_setup_calls"] = list(self.artifact_setup_calls)
            captured["checkpoint_setup_calls"] = list(self.checkpoint_setup_calls)
            captured["applied_submit_profile"] = self.applied_submit_profile
            captured["monitor_started"] = self.monitor_started
            return sentinel

    dispatcher = _Dispatcher()

    result = await coordinator.execute(
        dispatcher,
        target="127.0.0.1:3000/",
        goal=" goal ",
        type="",
        hint=" hint ",
        submit_profile={"platform": "ctf"},
        challenge_context={"artifactPaths": [" C:/tmp/app.zip ", "", "C:/tmp/app.zip"]},
        run_id="run-bootstrap",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    assert result is sentinel
    assert captured["_delegate_to_coordinator"] is False
    assert captured["_bootstrap_ready"] is True
    assert captured["_requested_type"] == "auto"
    assert captured["target"] == "http://127.0.0.1:3000"
    assert captured["goal"] == "goal"
    assert captured["hint"] == "hint"
    assert captured["notes_log"] == []
    assert captured["challenge_context"] == {
        "challengePath": None,
        "artifactPaths": ["C:/tmp/app.zip"],
    }
    assert captured["ledger_run_id"] == "run-bootstrap"
    assert captured["state_target"] == "http://127.0.0.1:3000"
    assert captured["state_goal"] == "goal"
    assert captured["current_fingerprint"] is None
    assert captured["memory_match_ids"] == []
    assert captured["pending_wrong_flag_feedback"] == []
    assert captured["exhausted_visit_url_targets"] == set()
    assert captured["degradation_events"] == []
    assert captured["artifact_setup_calls"] == [("run-bootstrap", None)]
    assert captured["checkpoint_setup_calls"] == [("run-bootstrap", tmp_path / "checkpoints")]
    assert captured["applied_submit_profile"] == {"platform": "ctf"}
    assert captured["monitor_started"] is True


@pytest.mark.asyncio
async def test_coordinator_applies_run_start_contract_before_inner_run(tmp_path: Path):
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=False, reason="run-started")
    challenge_dir = tmp_path / "challenge"
    challenge_dir.mkdir()
    captured: dict[str, object] = {}

    class _Dispatcher:
        def __init__(self):
            self._notes_log = []
            self._challenge_context = None
            self._ledger_run_id = None
            self._current_fingerprint = None
            self._memory_match_ids = []
            self._pending_wrong_flag_feedback = []
            self._exhausted_visit_url_targets = set()
            self.reasoning_layer = SimpleNamespace(degradation_events=[])
            self.state = None
            self.recorded_events: list[tuple[str, dict[str, object]]] = []
            self.written_checkpoints: list[tuple[str, dict[str, object]]] = []

        def _setup_session_ledger(self, *, run_id=None, ledger_root=None):
            self._ledger_run_id = run_id

        def _setup_artifact_registry(self, *, run_id=None, registry_root=None):
            return None

        def _setup_checkpoint_store(self, *, run_id=None, checkpoint_root=None):
            return None

        def _apply_submit_profile(self, submit_profile):
            return None

        async def _start_failover_monitor_if_available(self):
            return None

        def _record_session_event(self, event_type: str, payload: dict[str, object]):
            self.recorded_events.append((event_type, dict(payload)))

        def _write_checkpoint(self, label: str, payload: dict[str, object]):
            self.written_checkpoints.append((label, dict(payload)))

        async def run(self, **kwargs):
            captured.update(kwargs)
            captured["local_challenge_auto_verify"] = getattr(self.state, "local_challenge_auto_verify", None)
            captured["recorded_events"] = list(self.recorded_events)
            captured["written_checkpoints"] = list(self.written_checkpoints)
            return sentinel

    dispatcher = _Dispatcher()

    result = await coordinator.execute(
        dispatcher,
        target="127.0.0.1:3000",
        goal="goal",
        type="web",
        hint="",
        submit_profile=None,
        challenge_context={"challengePath": str(challenge_dir), "artifactPaths": []},
        run_id="run-start",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    assert result is sentinel
    assert captured["_run_started"] is True
    assert captured["local_challenge_auto_verify"] is True
    assert captured["recorded_events"] == [
        (
            "dispatcher_started",
            {
                "target": "http://127.0.0.1:3000",
                "goal": "goal",
                "requested_type": "web",
                "local_challenge_auto_verify": True,
                "has_challenge_context": True,
            },
        )
    ]
    assert captured["written_checkpoints"] == [
        (
            "dispatcher_started",
            {
                "target": "http://127.0.0.1:3000",
                "goal": "goal",
                "requested_type": "web",
            },
        )
    ]
