from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from pentestagent.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher, SolveResult
from pentestagent.agents.pa_agent.coordinator import CTFCoordinator
from pentestagent.agents.pa_agent.ctf_state import Hypothesis
from pentestagent.agents.pa_agent.recovery import RecoveryDecision


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
        self.rejected_flags_loaded = False
        self.platform_snapshot_targets: list[str] = []
        self.capability_registry = SimpleNamespace(
            full_check=self._capability_full_check,
            to_dict=lambda: {"http_request_basic": "available"},
        )
        self.capability_full_check_calls = 0

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

    def _load_rejected_flags(self):
        self.rejected_flags_loaded = True

    async def _snapshot_platform_context(self, target: str):
        self.platform_snapshot_targets.append(target)

    async def _capability_full_check(self):
        self.capability_full_check_calls += 1

    async def _phase_recon(self, target: str):
        return {
            "html": "<html></html>",
            "content": "portal",
            "forms": [],
            "endpoints": ["/login"],
            "recon_missing_tools": [],
        }

    def _ingest_local_challenge_artifacts(self, target: str):
        return None

    def _ingest_registered_local_source_hints(self):
        return None

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
            "resumeContext": {
                "runId": " run-prev-1 ",
                "checkpointId": " checkpoint-prev-1 ",
                "checkpointLabel": " task_failed ",
                "stopReason": " wrong_flag_feedback ",
                "summary": " run_id=run-prev-1; stop_reason=wrong_flag_feedback ",
                "verifiedFlags": ["", " flag{dup} ", "flag{dup}"],
                "runtimeFlags": [" candidate{1} ", ""],
            },
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
        "resumeContext": {
            "runId": "run-prev-1",
            "checkpointId": "checkpoint-prev-1",
            "checkpointLabel": "task_failed",
            "stopReason": "wrong_flag_feedback",
            "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
            "verifiedFlags": ["flag{dup}"],
            "runtimeFlags": ["candidate{1}"],
        },
    }


@pytest.mark.asyncio
async def test_coordinator_derives_target_from_challenge_path_compose_when_target_missing(
    tmp_path: Path,
):
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=False, reason="derived-target")
    dispatcher = _BootstrapCapableDispatcher(sentinel)

    challenge_dir = tmp_path / "easy_login"
    challenge_dir.mkdir()
    (challenge_dir / "docker-compose.yml").write_text(
        'services:\n  app:\n    image: easy-login\n    ports:\n      - "3000:3000"\n',
        encoding="utf-8",
    )

    result = await coordinator.execute(
        dispatcher,
        target="",
        goal="goal",
        type="web",
        hint="",
        submit_profile=None,
        challenge_context={
            "challengePath": str(challenge_dir),
            "artifactPaths": [],
        },
        run_id="run-derived-target-path",
        ledger_root=None,
        checkpoint_root=None,
    )

    assert result is sentinel
    assert dispatcher._captured["target"] == "http://127.0.0.1:3000"
    assert dispatcher._captured["challenge_context"]["challengePath"] == str(challenge_dir)


@pytest.mark.asyncio
async def test_coordinator_derives_target_from_local_archive_when_target_missing(
    tmp_path: Path,
):
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=False, reason="derived-target-archive")
    dispatcher = _BootstrapCapableDispatcher(sentinel)

    archive_src = tmp_path / "archive_src" / "easy_login_zip"
    archive_src.mkdir(parents=True)
    (archive_src / "docker-compose.yml").write_text(
        'services:\n  app:\n    image: easy-login\n    ports:\n      - "8080:80"\n',
        encoding="utf-8",
    )
    archive_path = tmp_path / "easy_login.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(
            archive_src / "docker-compose.yml",
            arcname="easy_login_zip/docker-compose.yml",
        )

    result = await coordinator.execute(
        dispatcher,
        target="",
        goal="goal",
        type="web",
        hint="",
        submit_profile=None,
        challenge_context={
            "artifactPaths": [str(archive_path)],
        },
        run_id="run-derived-target-archive",
        ledger_root=None,
        checkpoint_root=None,
    )

    assert result is sentinel
    assert dispatcher._captured["target"] == "http://127.0.0.1:8080"
    assert dispatcher._captured["challenge_context"]["artifactPaths"] == [str(archive_path)]


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
            self.rejected_flags_loaded = False
            self.platform_snapshot_targets: list[str] = []
            self.capability_full_check_calls = 0
            self.capability_registry = SimpleNamespace(
                full_check=self._capability_full_check,
                to_dict=lambda: {"http_request_basic": "available"},
            )

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

        def _load_rejected_flags(self):
            self.rejected_flags_loaded = True

        async def _snapshot_platform_context(self, target: str):
            self.platform_snapshot_targets.append(target)

        async def _phase_recon(self, target: str):
            return {
                "html": "<html></html>",
                "content": "portal",
                "forms": [],
                "endpoints": ["/login"],
                "recon_missing_tools": [],
            }

        def _ingest_local_challenge_artifacts(self, target: str):
            return None

        async def _capability_full_check(self):
            self.capability_full_check_calls += 1

        async def _phase_recon(self, target: str):
            return {
                "html": "<html></html>",
                "content": "portal",
                "forms": [],
                "endpoints": ["/login"],
                "recon_missing_tools": [],
            }

        def _ingest_local_challenge_artifacts(self, target: str):
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
            captured["rejected_flags_loaded"] = self.rejected_flags_loaded
            captured["platform_snapshot_targets"] = list(self.platform_snapshot_targets)
            captured["capability_full_check_calls"] = self.capability_full_check_calls
            captured["state_capabilities"] = dict(getattr(self.state, "capabilities", {}) or {})
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
    assert captured["rejected_flags_loaded"] is True
    assert captured["platform_snapshot_targets"] == ["http://127.0.0.1:3000"]
    assert captured["capability_full_check_calls"] == 1
    assert captured["state_capabilities"] == {"http_request_basic": "available"}


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
            self.rejected_flags_loaded = False
            self.platform_snapshot_targets: list[str] = []
            self.capability_full_check_calls = 0
            self.capability_registry = SimpleNamespace(
                full_check=self._capability_full_check,
                to_dict=lambda: {"http_request_basic": "available"},
            )

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

        def _load_rejected_flags(self):
            self.rejected_flags_loaded = True

        async def _snapshot_platform_context(self, target: str):
            self.platform_snapshot_targets.append(target)

        async def _capability_full_check(self):
            self.capability_full_check_calls += 1

        async def _phase_recon(self, target: str):
            return {
                "html": "<html></html>",
                "content": "portal",
                "forms": [],
                "endpoints": ["/login"],
                "recon_missing_tools": [],
            }

        def _ingest_local_challenge_artifacts(self, target: str):
            return None

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


@pytest.mark.asyncio
async def test_coordinator_records_resume_ingress_in_run_start_contract(tmp_path: Path):
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=False, reason="run-start-resume")
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
            self.rejected_flags_loaded = False
            self.platform_snapshot_targets: list[str] = []
            self.capability_full_check_calls = 0
            self.capability_registry = SimpleNamespace(
                full_check=self._capability_full_check,
                to_dict=lambda: {"http_request_basic": "available"},
            )

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

        def _load_rejected_flags(self):
            self.rejected_flags_loaded = True

        async def _snapshot_platform_context(self, target: str):
            self.platform_snapshot_targets.append(target)

        async def _capability_full_check(self):
            self.capability_full_check_calls += 1

        async def _phase_recon(self, target: str):
            return {
                "html": "<html></html>",
                "content": "portal",
                "forms": [],
                "endpoints": ["/login"],
                "recon_missing_tools": [],
            }

        def _ingest_local_challenge_artifacts(self, target: str):
            return None

        async def run(self, **kwargs):
            captured.update(kwargs)
            captured["local_challenge_auto_verify"] = getattr(
                self.state, "local_challenge_auto_verify", None
            )
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
        challenge_context={
            "challengePath": str(challenge_dir),
            "artifactPaths": [],
            "resumeContext": {
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "checkpointLabel": "task_failed",
                "stopReason": "wrong_flag_feedback",
                "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
            },
        },
        run_id="run-start-resume",
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
                "has_resume_context": True,
                "resume_run_id": "run-prev-1",
                "resume_checkpoint_id": "checkpoint-prev-1",
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
                "has_resume_context": True,
                "resume_run_id": "run-prev-1",
                "resume_checkpoint_id": "checkpoint-prev-1",
            },
        )
    ]


@pytest.mark.asyncio
async def test_coordinator_applies_pre_recon_contract_before_inner_run(tmp_path: Path):
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=False, reason="pre-recon-ready")
    captured: dict[str, object] = {}

    class _CapabilityRegistry:
        def __init__(self):
            self.full_check_calls = 0

        async def full_check(self):
            self.full_check_calls += 1

        def to_dict(self):
            return {"http_request_basic": "available"}

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
            self.capability_registry = _CapabilityRegistry()
            self.rejected_flags_loaded = False
            self.platform_snapshot_targets: list[str] = []

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
            return None

        def _write_checkpoint(self, label: str, payload: dict[str, object]):
            return None

        def _load_rejected_flags(self):
            self.rejected_flags_loaded = True

        async def _snapshot_platform_context(self, target: str):
            self.platform_snapshot_targets.append(target)

        async def _phase_recon(self, target: str):
            return {
                "html": "<html></html>",
                "content": "portal",
                "forms": [],
                "endpoints": ["/login"],
                "recon_missing_tools": [],
            }

        def _ingest_local_challenge_artifacts(self, target: str):
            return None

        async def run(self, **kwargs):
            captured.update(kwargs)
            captured["rejected_flags_loaded"] = self.rejected_flags_loaded
            captured["platform_snapshot_targets"] = list(self.platform_snapshot_targets)
            captured["capability_full_check_calls"] = self.capability_registry.full_check_calls
            captured["state_capabilities"] = dict(getattr(self.state, "capabilities", {}) or {})
            return sentinel

    dispatcher = _Dispatcher()

    result = await coordinator.execute(
        dispatcher,
        target="127.0.0.1:3000",
        goal="goal",
        type="web",
        hint="",
        submit_profile=None,
        challenge_context={"artifactPaths": []},
        run_id="run-prerecon",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    assert result is sentinel
    assert captured["_pre_recon_ready"] is True
    assert captured["rejected_flags_loaded"] is True
    assert captured["platform_snapshot_targets"] == ["http://127.0.0.1:3000"]
    assert captured["capability_full_check_calls"] == 1
    assert captured["state_capabilities"] == {"http_request_basic": "available"}


@pytest.mark.asyncio
async def test_coordinator_applies_recon_contract_before_inner_run(tmp_path: Path):
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=False, reason="recon-ready")
    captured: dict[str, object] = {}
    page_features = {
        "html": "<html></html>",
        "content": "portal",
        "forms": [],
        "endpoints": ["/login"],
        "recon_missing_tools": [],
    }

    class _CapabilityRegistry:
        async def full_check(self):
            return None

        def to_dict(self):
            return {}

    class _ToolGuard:
        def suggest_install(self, name: str) -> str:
            return f"install {name}"

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
            self.capability_registry = _CapabilityRegistry()
            self.tool_guard = _ToolGuard()
            self.phase_recon_targets: list[str] = []
            self.ingested_targets: list[str] = []

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
            return None

        def _write_checkpoint(self, label: str, payload: dict[str, object]):
            return None

        def _load_rejected_flags(self):
            return None

        async def _snapshot_platform_context(self, target: str):
            return None

        async def _phase_recon(self, target: str):
            self.phase_recon_targets.append(target)
            return dict(page_features)

        def _ingest_local_challenge_artifacts(self, target: str):
            self.ingested_targets.append(target)

        async def run(self, **kwargs):
            captured.update(kwargs)
            captured["phase_recon_targets"] = list(self.phase_recon_targets)
            captured["ingested_targets"] = list(self.ingested_targets)
            return sentinel

    dispatcher = _Dispatcher()

    result = await coordinator.execute(
        dispatcher,
        target="127.0.0.1:3000",
        goal="goal",
        type="web",
        hint="",
        submit_profile=None,
        challenge_context={"artifactPaths": []},
        run_id="run-recon",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    assert result is sentinel
    assert captured["_recon_ready"] is True
    assert captured["_page_features"] == page_features
    assert captured["phase_recon_targets"] == ["http://127.0.0.1:3000"]
    assert captured["ingested_targets"] == ["http://127.0.0.1:3000"]


@pytest.mark.asyncio
async def test_coordinator_returns_missing_recon_result_before_inner_run(tmp_path: Path):
    coordinator = CTFCoordinator()
    finalized: list[SolveResult] = []

    class _CapabilityRegistry:
        async def full_check(self):
            return None

        def to_dict(self):
            return {}

    class _ToolGuard:
        def suggest_install(self, name: str) -> str:
            return f"install {name}"

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
            self.capability_registry = _CapabilityRegistry()
            self.tool_guard = _ToolGuard()
            self.stored_missing_tools = None
            self.run_called = False

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
            return None

        def _write_checkpoint(self, label: str, payload: dict[str, object]):
            return None

        def _load_rejected_flags(self):
            return None

        async def _snapshot_platform_context(self, target: str):
            return None

        async def _phase_recon(self, target: str):
            return {
                "html": "",
                "content": "",
                "forms": [],
                "endpoints": [],
                "recon_missing_tools": ["browser", "http_request"],
            }

        def _ingest_local_challenge_artifacts(self, target: str):
            return None

        async def _store_missing_tools(self, missing, install_commands):
            self.stored_missing_tools = (list(missing), dict(install_commands))
            self._notes_log.append(f"missing:{','.join(missing)}")

        async def _finalize_solve_result(self, result: SolveResult):
            finalized.append(result)
            return result

        async def run(self, **kwargs):
            self.run_called = True
            return SolveResult(success=True, reason="should-not-run")

    dispatcher = _Dispatcher()

    result = await coordinator.execute(
        dispatcher,
        target="127.0.0.1:3000",
        goal="goal",
        type="web",
        hint="",
        submit_profile=None,
        challenge_context={"artifactPaths": []},
        run_id="run-recon-missing",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    assert dispatcher.run_called is False
    assert result.success is False
    assert result.missing_tools == ["browser", "http_request"]
    assert result.notes == ["missing:browser,http_request"]
    assert "侦察依赖缺失" in result.reason
    assert dispatcher.stored_missing_tools == (
        ["browser", "http_request"],
        {"browser": "install browser", "http_request": "install http_request"},
    )
    assert finalized and finalized[0] is result


@pytest.mark.asyncio
async def test_coordinator_applies_post_recon_contract_before_inner_run(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.detect_type",
        lambda content, target: "misc",
    )
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=False, reason="post-recon-ready")
    captured: dict[str, object] = {}
    page_features = {
        "html": "<html><title>Archive</title></html>",
        "content": "download the archive",
        "forms": [],
        "endpoints": ["/download"],
        "recon_missing_tools": [],
    }

    class _CapabilityRegistry:
        async def full_check(self):
            return None

        def to_dict(self):
            return {}

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
            self.capability_registry = _CapabilityRegistry()

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
            return None

        def _write_checkpoint(self, label: str, payload: dict[str, object]):
            return None

        def _load_rejected_flags(self):
            return None

        async def _snapshot_platform_context(self, target: str):
            return None

        async def _phase_recon(self, target: str):
            return dict(page_features)

        def _ingest_local_challenge_artifacts(self, target: str):
            return None

        def _align_platform_challenge(self, target: str, features: dict[str, object]):
            return None

        def _extract_flag(self, text: str):
            return None

        def _emit(self, message: str):
            return None

        async def run(self, **kwargs):
            captured.update(kwargs)
            return sentinel

    dispatcher = _Dispatcher()

    result = await coordinator.execute(
        dispatcher,
        target="127.0.0.1:3000",
        goal="goal",
        type="auto",
        hint="",
        submit_profile=None,
        challenge_context={"artifactPaths": []},
        run_id="run-post-recon",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    assert result is sentinel
    assert captured["_post_recon_ready"] is True
    assert captured["_page_features"] == page_features
    assert captured["_detected_type"] == "misc"
    assert dispatcher.state is not None
    assert dispatcher.state.detected_type == "misc"


@pytest.mark.asyncio
async def test_coordinator_stops_when_platform_alignment_marks_already_solved(tmp_path: Path):
    coordinator = CTFCoordinator()

    class _CapabilityRegistry:
        async def full_check(self):
            return None

        def to_dict(self):
            return {}

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
            self.capability_registry = _CapabilityRegistry()
            self.run_called = False
            self.finalized_results: list[SolveResult] = []

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
            return None

        def _write_checkpoint(self, label: str, payload: dict[str, object]):
            return None

        def _load_rejected_flags(self):
            return None

        async def _snapshot_platform_context(self, target: str):
            return None

        async def _phase_recon(self, target: str):
            return {
                "html": "<html></html>",
                "content": "portal",
                "forms": [],
                "endpoints": ["/challenge/42"],
                "recon_missing_tools": [],
            }

        def _ingest_local_challenge_artifacts(self, target: str):
            return None

        def _align_platform_challenge(self, target: str, features: dict[str, object]):
            return {
                "challenge_id": "42",
                "challenge_name": "EasySQL",
                "platform_type": "ctfd",
                "already_solved": True,
            }

        def _build_already_solved_reason(self) -> str:
            return "already solved on platform"

        def _extract_flag(self, text: str):
            return None

        def _emit(self, message: str):
            return None

        async def _finalize_solve_result(self, result: SolveResult):
            self.finalized_results.append(result)
            return result

        async def run(self, **kwargs):
            self.run_called = True
            return SolveResult(success=False, reason="should-not-run")

    dispatcher = _Dispatcher()

    result = await coordinator.execute(
        dispatcher,
        target="127.0.0.1:3000",
        goal="goal",
        type="web",
        hint="",
        submit_profile=None,
        challenge_context={"artifactPaths": []},
        run_id="run-already-solved",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    assert dispatcher.run_called is False
    assert dispatcher.finalized_results
    assert result.reason == "already solved on platform"
    assert dispatcher.state is not None
    assert dispatcher.state.submit_challenge_id == "42"
    assert any(
        isinstance(item, dict)
        and item.get("type") == "platform_challenge_alignment"
        and item.get("already_solved") is True
        and item.get("challenge_id") == "42"
        for item in dispatcher.state.meta_reasonings
    )


@pytest.mark.asyncio
async def test_coordinator_returns_verified_direct_flag_before_inner_run(tmp_path: Path):
    coordinator = CTFCoordinator()
    observed: list[tuple[str, str, str, str]] = []

    class _CapabilityRegistry:
        async def full_check(self):
            return None

        def to_dict(self):
            return {}

    class _Dispatcher:
        def __init__(self):
            self._notes_log = ["note-a"]
            self._challenge_context = None
            self._ledger_run_id = None
            self._current_fingerprint = None
            self._memory_match_ids = []
            self._pending_wrong_flag_feedback = []
            self._exhausted_visit_url_targets = set()
            self.reasoning_layer = SimpleNamespace(degradation_events=[])
            self.state = None
            self.capability_registry = _CapabilityRegistry()
            self.run_called = False
            self.finalized_results: list[SolveResult] = []

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
            return None

        def _write_checkpoint(self, label: str, payload: dict[str, object]):
            return None

        def _load_rejected_flags(self):
            return None

        async def _snapshot_platform_context(self, target: str):
            return None

        async def _phase_recon(self, target: str):
            self._notes_log.append("note-a")
            return {
                "html": "<html></html>",
                "content": "welcome flag{win}",
                "forms": [],
                "endpoints": ["/"],
                "recon_missing_tools": [],
            }

        def _ingest_local_challenge_artifacts(self, target: str):
            return None

        def _align_platform_challenge(self, target: str, features: dict[str, object]):
            return None

        def _extract_flag(self, text: str):
            return "flag{win}"

        async def _observe_flag(
            self,
            flag: str,
            target: str,
            *,
            evidence_source: str,
            rationale: str,
        ):
            observed.append((flag, target, evidence_source, rationale))
            return SimpleNamespace(decision="verified")

        def _emit(self, message: str):
            return None

        async def _finalize_solve_result(self, result: SolveResult):
            self.finalized_results.append(result)
            return result

        async def run(self, **kwargs):
            self.run_called = True
            return SolveResult(success=False, reason="should-not-run")

    dispatcher = _Dispatcher()

    result = await coordinator.execute(
        dispatcher,
        target="127.0.0.1:3000",
        goal="goal",
        type="web",
        hint="",
        submit_profile=None,
        challenge_context={"artifactPaths": []},
        run_id="run-direct-flag",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    assert dispatcher.run_called is False
    assert dispatcher.finalized_results
    assert result.success is True
    assert result.flag == "flag{win}"
    assert result.chain_used == ["recon"]
    assert result.reason == "首页直接命中旗帜"
    assert result.notes == ["note-a"]
    assert observed == [
        (
            "flag{win}",
            "http://127.0.0.1:3000",
            "browser-rendered-page",
            "首页直接命中旗帜",
        )
    ]
    assert dispatcher.state is not None
    assert dispatcher.state.stop_reason == "首页直接命中旗帜"


@pytest.mark.asyncio
async def test_coordinator_verifies_runtime_signal_before_recon_when_hint_requests_it(
    tmp_path: Path,
):
    coordinator = CTFCoordinator()
    observed: list[tuple[str, str, str, str]] = []

    class _CapabilityRegistry:
        async def full_check(self):
            return None

        def to_dict(self):
            return {}

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
            self.capability_registry = _CapabilityRegistry()
            self.run_called = False
            self.phase_recon_called = False
            self.finalized_results: list[SolveResult] = []

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
            return None

        def _write_checkpoint(self, label: str, payload: dict[str, object]):
            return None

        def _load_rejected_flags(self):
            return None

        async def _snapshot_platform_context(self, target: str):
            return None

        async def _phase_recon(self, target: str):
            self.phase_recon_called = True
            return {
                "html": "<html></html>",
                "content": "portal",
                "forms": [],
                "endpoints": ["/"],
                "recon_missing_tools": [],
            }

        def _ingest_local_challenge_artifacts(self, target: str):
            return None

        async def _observe_flag(
            self,
            flag: str,
            target: str,
            *,
            evidence_source: str,
            rationale: str,
        ):
            self._notes_log.append("runtime-note")
            observed.append((flag, target, evidence_source, rationale))
            return SimpleNamespace(decision="verified", flag=flag)

        def _emit(self, message: str):
            return None

        async def _finalize_solve_result(self, result: SolveResult):
            self.finalized_results.append(result)
            return result

        async def run(self, **kwargs):
            self.run_called = True
            return SolveResult(success=False, reason="should-not-run")

    dispatcher = _Dispatcher()

    result = await coordinator.execute(
        dispatcher,
        target="127.0.0.1:3000",
        goal="goal",
        type="web",
        hint=(
            "[control_decision]\n"
            "decisionKind=direct_execute\n"
            "nextAction=verify_runtime_signal\n"
            "driver=blackboard.runtime_flag\n"
            "runtimeFlag=flag{dispatcher_runtime}"
        ),
        submit_profile=None,
        challenge_context={"artifactPaths": []},
        run_id="run-runtime-verify",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    assert dispatcher.run_called is False
    assert dispatcher.phase_recon_called is False
    assert dispatcher.finalized_results
    assert result.success is True
    assert result.flag == "flag{dispatcher_runtime}"
    assert result.chain_used == ["runtime_signal"]
    assert result.reason == "runtime 信号优先验证命中旗帜"
    assert result.notes == ["runtime-note"]
    assert observed == [
        (
            "flag{dispatcher_runtime}",
            "http://127.0.0.1:3000",
            "runtime-blackboard-signal",
            "blackboard runtime flag requested verification",
        )
    ]
    assert dispatcher.state is not None
    assert dispatcher.state.stop_reason == "runtime 信号优先验证命中旗帜"


@pytest.mark.asyncio
async def test_coordinator_returns_verified_flag_from_hint_before_recon(
    tmp_path: Path,
):
    coordinator = CTFCoordinator()

    class _CapabilityRegistry:
        async def full_check(self):
            return None

        def to_dict(self):
            return {}

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
            self.capability_registry = _CapabilityRegistry()
            self.run_called = False
            self.phase_recon_called = False
            self.finalized_results: list[SolveResult] = []

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
            return None

        def _write_checkpoint(self, label: str, payload: dict[str, object]):
            return None

        def _load_rejected_flags(self):
            return None

        async def _snapshot_platform_context(self, target: str):
            return None

        async def _phase_recon(self, target: str):
            self.phase_recon_called = True
            return {
                "html": "<html></html>",
                "content": "portal",
                "forms": [],
                "endpoints": ["/"],
                "recon_missing_tools": [],
            }

        def _ingest_local_challenge_artifacts(self, target: str):
            return None

        def _emit(self, message: str):
            return None

        async def _finalize_solve_result(self, result: SolveResult):
            self.finalized_results.append(result)
            return result

        async def run(self, **kwargs):
            self.run_called = True
            return SolveResult(success=False, reason="should-not-run")

    dispatcher = _Dispatcher()

    result = await coordinator.execute(
        dispatcher,
        target="127.0.0.1:3000",
        goal="goal",
        type="web",
        hint=(
            "[control_decision]\n"
            "decisionKind=direct_execute\n"
            "nextAction=verify_or_submit_flag\n"
            "driver=blackboard.verified_flag\n"
            "verifiedFlag=flag{verified_from_blackboard}"
        ),
        submit_profile=None,
        challenge_context={"artifactPaths": []},
        run_id="run-verified-flag",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    assert dispatcher.run_called is False
    assert dispatcher.phase_recon_called is False
    assert dispatcher.finalized_results
    assert result.success is True
    assert result.flag == "flag{verified_from_blackboard}"
    assert result.chain_used == ["verified_flag"]
    assert result.reason == "blackboard 已有 verified flag"
    assert result.notes == []
    assert dispatcher.state is not None
    assert dispatcher.state.stop_reason == "blackboard 已有 verified flag"


@pytest.mark.asyncio
async def test_coordinator_applies_strategy_memory_contract_before_inner_run(
    tmp_path: Path,
):
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=False, reason="strategy-memory-ready")
    captured: dict[str, object] = {}
    query_usage_calls: list[list[str]] = []

    class _CapabilityRegistry:
        async def full_check(self):
            return None

        def to_dict(self):
            return {}

    class _Entry:
        def __init__(self):
            self.id = "mem-1"
            self.atomic_facts = ["auth:form_login"]
            self.winning_hypothesis_kinds = ["auth_form_sqli"]
            self.failed_hypothesis_kinds = ["generic_web_recon"]

    class _StrategyMemory:
        def build_fingerprint(self, state, *, page_features, target):
            return {"target": target, "detected_type": state.detected_type}

        async def query(self, fingerprint):
            return [(_Entry(), 0.8123)]

        async def record_query_usage(self, entry_ids: list[str]):
            query_usage_calls.append(list(entry_ids))

        def compute_hypothesis_adjustments(self, memory_matches):
            return {"auth_form_sqli": 0.35}

        def build_atomic_facts(self, *, state, fingerprint):
            return ["detected:sqli", "auth:form_login"]

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
            self.capability_registry = _CapabilityRegistry()
            self.strategy_memory = _StrategyMemory()

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
            return None

        def _write_checkpoint(self, label: str, payload: dict[str, object]):
            return None

        def _load_rejected_flags(self):
            return None

        async def _snapshot_platform_context(self, target: str):
            return None

        async def _phase_recon(self, target: str):
            return {
                "html": "<html></html>",
                "content": "login portal",
                "forms": [],
                "endpoints": ["/login"],
                "recon_missing_tools": [],
            }

        def _ingest_local_challenge_artifacts(self, target: str):
            return None

        def _align_platform_challenge(self, target: str, features: dict[str, object]):
            return None

        def _extract_flag(self, text: str):
            return None

        def _emit(self, message: str):
            return None

        async def run(self, **kwargs):
            captured.update(kwargs)
            captured["current_fingerprint"] = self._current_fingerprint
            captured["memory_match_ids"] = list(self._memory_match_ids)
            captured["hypothesis_memory_adjustments"] = dict(
                getattr(self.state, "hypothesis_memory_adjustments", {}) or {}
            )
            captured["meta_reasonings"] = list(getattr(self.state, "meta_reasonings", []) or [])
            return sentinel

    dispatcher = _Dispatcher()

    result = await coordinator.execute(
        dispatcher,
        target="127.0.0.1:3000",
        goal="goal",
        type="sqli",
        hint="",
        submit_profile=None,
        challenge_context={"artifactPaths": []},
        run_id="run-strategy-memory",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    assert result is sentinel
    assert captured["_strategy_memory_ready"] is True
    assert captured["current_fingerprint"] == {
        "target": "http://127.0.0.1:3000",
        "detected_type": "sqli",
    }
    assert captured["memory_match_ids"] == ["mem-1"]
    assert captured["hypothesis_memory_adjustments"] == {"auth_form_sqli": 0.35}
    assert query_usage_calls == [["mem-1"]]
    assert any(
        isinstance(item, dict)
        and item.get("type") == "strategy_memory_audit"
        and item.get("matched_entries") == [
            {
                "id": "mem-1",
                "similarity": 0.8123,
                "atomic_facts": ["auth:form_login"],
                "winning_hypothesis_kinds": ["auth_form_sqli"],
                "failed_hypothesis_kinds": ["generic_web_recon"],
            }
        ]
        and item.get("adjustments") == {"auth_form_sqli": 0.35}
        for item in captured["meta_reasonings"]
    )


@pytest.mark.asyncio
async def test_coordinator_applies_hypothesis_contract_before_inner_run(tmp_path: Path):
    coordinator = CTFCoordinator()
    sentinel = SolveResult(success=False, reason="hypothesis-ready")
    captured: dict[str, object] = {}

    class _CapabilityRegistry:
        async def full_check(self):
            return None

        def to_dict(self):
            return {}

    class _StrategyMemory:
        def build_fingerprint(self, state, *, page_features, target):
            return {"target": target}

        async def query(self, fingerprint):
            return []

        async def record_query_usage(self, entry_ids: list[str]):
            return None

        def compute_hypothesis_adjustments(self, memory_matches):
            return {}

        def build_atomic_facts(self, *, state, fingerprint):
            return []

    class _HypothesisEngine:
        def generate(self, state):
            state.hypotheses = [
                Hypothesis(
                    id="hyp-1",
                    kind="auth_form_sqli",
                    description="try auth form sqli",
                    confidence=0.78,
                ),
                Hypothesis(
                    id="hyp-2",
                    kind="generic_web_recon",
                    description="continue web recon",
                    confidence=0.52,
                ),
            ]
            return list(state.hypotheses)

        def choose_chain_order(self, state):
            return ["sqli", "web", "web"]

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
            self.capability_registry = _CapabilityRegistry()
            self.strategy_memory = _StrategyMemory()
            self.hypothesis_engine = _HypothesisEngine()

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
            return None

        def _write_checkpoint(self, label: str, payload: dict[str, object]):
            return None

        def _load_rejected_flags(self):
            return None

        async def _snapshot_platform_context(self, target: str):
            return None

        async def _phase_recon(self, target: str):
            return {
                "html": "<html></html>",
                "content": "login portal",
                "forms": [],
                "endpoints": ["/login"],
                "recon_missing_tools": [],
            }

        def _ingest_local_challenge_artifacts(self, target: str):
            return None

        def _align_platform_challenge(self, target: str, features: dict[str, object]):
            return None

        def _extract_flag(self, text: str):
            return None

        def _emit(self, message: str):
            return None

        async def run(self, **kwargs):
            captured.update(kwargs)
            captured["hypotheses"] = [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "confidence": item.confidence,
                }
                for item in getattr(self.state, "hypotheses", [])
            ]
            return sentinel

    dispatcher = _Dispatcher()

    result = await coordinator.execute(
        dispatcher,
        target="127.0.0.1:3000",
        goal="goal",
        type="sqli",
        hint="",
        submit_profile=None,
        challenge_context={"artifactPaths": []},
        run_id="run-hypothesis",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    assert result is sentinel
    assert captured["_hypotheses_ready"] is True
    assert captured["_chain_order"] == ["sqli", "web"]
    assert captured["hypotheses"] == [
        {"id": "hyp-1", "kind": "auth_form_sqli", "confidence": 0.78},
        {"id": "hyp-2", "kind": "generic_web_recon", "confidence": 0.52},
    ]


def test_coordinator_prepares_chain_iteration_contract():
    coordinator = CTFCoordinator()
    hypothesis = Hypothesis(
        id="hyp-1",
        kind="auth_form_sqli",
        description="try auth form sqli",
        confidence=0.82,
    )
    planned_calls: list[dict[str, object]] = []

    class _CapabilityRegistry:
        def best_available(self, primitive: str):
            return {"primitive": primitive, "provider": "sqlmap"}

    class _ReasoningLayer:
        def plan_chain_execution(
            self,
            state,
            *,
            chain_name,
            hypothesis,
            strategy,
            capability_primitive,
            capability_choice,
            alternatives,
        ):
            planned_calls.append(
                {
                    "chain_name": chain_name,
                    "hypothesis_id": hypothesis.id if hypothesis is not None else None,
                    "strategy": strategy,
                    "capability_primitive": capability_primitive,
                    "capability_choice": capability_choice,
                    "alternatives": list(alternatives),
                }
            )
            return SimpleNamespace(
                id="exp-1",
                hypothesis_id=hypothesis.id if hypothesis is not None else None,
                inputs={"chain": chain_name},
                expected_signal="flag or progress",
            )

    class _Dispatcher:
        def __init__(self):
            self.state = SimpleNamespace(hypotheses=[hypothesis])
            self.capability_registry = _CapabilityRegistry()
            self.reasoning_layer = _ReasoningLayer()

        def _select_hypothesis_for_chain(self, chain_name: str):
            return hypothesis

        def _select_primary_strategy(self, chain_name: str, *, target: str, page_features, hint: str):
            return {"kind": "auth_form_sqli", "chain": chain_name, "target": target}

        def _primary_capability_for_chain(self, chain_name: str):
            return "sql_injection_test"

    dispatcher = _Dispatcher()

    contract = coordinator._prepare_chain_iteration_contract(
        dispatcher,
        chain_name="sqli",
        target="http://ctf.local",
        page_features={"forms": [{"action": "/login"}]},
        hint="",
        chain_order=["sqli", "web", "xss"],
    )

    assert contract["active_hypothesis"] is hypothesis
    assert contract["strategy"] == {
        "kind": "auth_form_sqli",
        "chain": "sqli",
        "target": "http://ctf.local",
    }
    assert contract["capability_primitive"] == "sql_injection_test"
    assert contract["capability_choice"] == {
        "primitive": "sql_injection_test",
        "provider": "sqlmap",
    }
    assert getattr(contract["experiment"], "id", "") == "exp-1"
    assert planned_calls == [
        {
            "chain_name": "sqli",
            "hypothesis_id": "hyp-1",
            "strategy": {
                "kind": "auth_form_sqli",
                "chain": "sqli",
                "target": "http://ctf.local",
            },
            "capability_primitive": "sql_injection_test",
            "capability_choice": {
                "primitive": "sql_injection_test",
                "provider": "sqlmap",
            },
            "alternatives": ["web", "xss"],
        }
    ]


@pytest.mark.asyncio
async def test_coordinator_applies_missing_tools_recovery_contract_switch_chain():
    coordinator = CTFCoordinator()
    recorded: list[tuple[str, str]] = []
    emitted: list[str] = []
    stored: list[tuple[list[str], dict[str, str]]] = []

    class _ToolGuard:
        def suggest_install(self, name: str) -> str:
            return f"install {name}"

    class _RecoveryController:
        def on_missing_tools(self, state, *, current_chain: str, missing_tools: list[str], used_chains: list[str]):
            return RecoveryDecision(
                action="switch_chain",
                should_stop=False,
                reason="switch to web after missing sqlmap",
                next_chain_order=["web", "xss"],
                missing_tools=list(missing_tools),
            )

    class _Dispatcher:
        def __init__(self):
            self.tool_guard = _ToolGuard()
            self.recovery_controller = _RecoveryController()
            self.state = SimpleNamespace(stop_reason=None)

        async def _store_missing_tools(self, missing_names, install_commands):
            stored.append((list(missing_names), dict(install_commands)))

        def _record_recovery_decision(self, decision, *, chain_name: str):
            recorded.append((chain_name, decision.reason))

        def _emit(self, message: str):
            emitted.append(message)

    dispatcher = _Dispatcher()
    result = SolveResult(success=False)

    contract = await coordinator._apply_missing_tools_recovery_contract(
        dispatcher,
        chain_name="sqli",
        chain_index=0,
        chain_order=["sqli"],
        missing_names=["sqlmap"],
        result=result,
        target="http://ctf.local",
        active_hypothesis=None,
        experiment=None,
    )

    assert contract["continue_loop"] is True
    assert contract["next_chain_index"] == 1
    assert contract["chain_order"] == ["sqli", "web", "xss"]
    assert contract["final_result"] is None
    assert stored == [(["sqlmap"], {"sqlmap": "install sqlmap"})]
    assert recorded == [("sqli", "switch to web after missing sqlmap")]
    assert emitted == ["[CTF recovery] switch to web after missing sqlmap"]


def test_coordinator_applies_progress_evaluation_contract_with_effective_progress():
    coordinator = CTFCoordinator()
    feedback_calls: list[dict[str, object]] = []
    interpretations: list[dict[str, object]] = []
    evaluations: list[dict[str, object]] = []

    hypothesis = Hypothesis(
        id="hyp-1",
        kind="auth_form_sqli",
        description="try auth form sqli",
        confidence=0.82,
    )

    class _State:
        def __init__(self):
            self.progress_markers: list[str] = []
            self.no_progress_markers: list[str] = []

        def mark_progress(self, marker: str):
            self.progress_markers.append(marker)

        def mark_no_progress(self, marker: str):
            self.no_progress_markers.append(marker)

    class _HypothesisEngine:
        def record_experiment_feedback(self, state, **kwargs):
            feedback_calls.append(dict(kwargs))

    class _ReasoningLayer:
        def record_interpretation(self, state, **kwargs):
            interpretations.append(dict(kwargs))

        def evaluate_experiment_result(self, state, **kwargs):
            evaluations.append(dict(kwargs))

    class _Dispatcher:
        def __init__(self):
            self.state = _State()
            self.hypothesis_engine = _HypothesisEngine()
            self.reasoning_layer = _ReasoningLayer()

        def _derive_progress_delta(self, before_state, *, chain_outcome):
            return "strong"

        def _emit(self, message: str):
            return None

    dispatcher = _Dispatcher()
    outcome = SimpleNamespace(progress=True, reason="login bypass worked")
    experiment = SimpleNamespace(
        id="exp-1",
        inputs={"chain": "sqli"},
        expected_signal="flag or progress",
    )

    contract = coordinator._apply_progress_evaluation_contract(
        dispatcher,
        chain_name="sqli",
        before_state={"runtime": 0},
        outcome=outcome,
        no_progress_rounds=2,
        active_hypothesis=hypothesis,
        experiment=experiment,
    )

    assert contract["progress_delta"] == "strong"
    assert contract["effective_progress"] is True
    assert contract["no_progress_rounds"] == 0
    assert dispatcher.state.progress_markers == ["login bypass worked"]
    assert dispatcher.state.no_progress_markers == []
    assert feedback_calls == [
        {
            "hypothesis_id": "hyp-1",
            "progress_delta": "strong",
            "observed_signal": "login bypass worked",
            "experiment_id": "exp-1",
            "inputs": {"chain": "sqli"},
            "expected_signal": "flag or progress",
        }
    ]
    assert interpretations == [
        {
            "observation_ids": ["exp-1"],
            "content": "链路 sqli 取得进展：login bypass worked",
            "hypothesis_ids": ["hyp-1"],
            "confidence": 0.72,
        }
    ]
    assert evaluations == [
        {
            "experiment_id": "exp-1",
            "progress_delta": "strong",
            "observed_signal": "login bypass worked",
        }
    ]


@pytest.mark.asyncio
async def test_coordinator_applies_after_chain_recovery_contract_stop(tmp_path: Path):
    coordinator = CTFCoordinator()
    recorded: list[tuple[str, str]] = []
    emitted: list[str] = []
    retrospectives: list[tuple[str, str, str]] = []

    class _RecoveryController:
        def after_chain(self, state, *, current_chain: str, active_hypothesis, outcome_progress: bool, no_progress_count: int, used_chains: list[str]):
            return RecoveryDecision(
                action="stop_candidate_only",
                should_stop=True,
                reason="candidate only without runtime proof",
            )

    class _Dispatcher:
        def __init__(self):
            self.recovery_controller = _RecoveryController()
            self.state = SimpleNamespace(stop_reason=None)
            self._notes_log = ["note-a"]

        def _record_recovery_decision(self, decision, *, chain_name: str):
            recorded.append((chain_name, decision.reason))

        def _emit(self, message: str):
            emitted.append(message)

        async def _store_retrospective(self, reason: str, target: str, chain_name: str):
            retrospectives.append((reason, target, chain_name))

        async def _finalize_solve_result(self, result: SolveResult):
            return result

    dispatcher = _Dispatcher()
    result = SolveResult(success=False)

    contract = await coordinator._apply_after_chain_recovery_contract(
        dispatcher,
        chain_name="web",
        chain_index=0,
        chain_order=["web", "xss"],
        result=result,
        target="http://ctf.local",
        active_hypothesis=None,
        effective_progress=False,
        no_progress_rounds=1,
    )

    assert contract["continue_loop"] is False
    assert contract["chain_order"] == ["web", "xss"]
    assert contract["next_chain_index"] == 0
    assert contract["final_result"] is result
    assert result.reason == "candidate only without runtime proof"
    assert result.notes == ["note-a"]
    assert dispatcher.state.stop_reason == "candidate only without runtime proof"
    assert recorded == [("web", "candidate only without runtime proof")]
    assert emitted == ["[CTF recovery] candidate only without runtime proof"]
    assert retrospectives == [
        ("candidate only without runtime proof", "http://ctf.local", "web")
    ]


@pytest.mark.asyncio
async def test_coordinator_applies_wrong_flag_early_stop_contract():
    coordinator = CTFCoordinator()
    retrospectives: list[tuple[str, str, str]] = []

    class _Dispatcher:
        def __init__(self):
            self._pending_wrong_flag_feedback = [{"flag": "flag{wrong}"}]
            self._notes_log = ["note-a"]
            self.state = SimpleNamespace(stop_reason=None)

        async def _store_retrospective(self, reason: str, target: str, chain_name: str):
            retrospectives.append((reason, target, chain_name))

        async def _finalize_solve_result(self, result: SolveResult):
            return result

    dispatcher = _Dispatcher()
    result = SolveResult(success=False)
    outcome = SimpleNamespace(flag=None)

    finalized = await coordinator._apply_wrong_flag_early_stop_contract(
        dispatcher,
        result=result,
        outcome=outcome,
        target="http://ctf.local",
        chain_name="web",
    )

    assert finalized is result
    assert result.reason == "wrong flag feedback: flag{wrong}"
    assert result.notes == ["note-a"]
    assert dispatcher.state.stop_reason == "wrong flag feedback: flag{wrong}"
    assert retrospectives == [
        ("wrong flag feedback: flag{wrong}", "http://ctf.local", "web")
    ]


@pytest.mark.asyncio
async def test_coordinator_applies_terminal_success_contract():
    coordinator = CTFCoordinator()
    feedback_calls: list[dict[str, object]] = []
    interpretations: list[dict[str, object]] = []
    evaluations: list[dict[str, object]] = []

    hypothesis = Hypothesis(
        id="hyp-1",
        kind="auth_form_sqli",
        description="try auth form sqli",
        confidence=0.82,
    )

    class _State:
        def __init__(self):
            self.stop_reason = None
            self.progress_markers: list[str] = []

        def mark_progress(self, marker: str):
            self.progress_markers.append(marker)

    class _HypothesisEngine:
        def record_experiment_feedback(self, state, **kwargs):
            feedback_calls.append(dict(kwargs))

    class _ReasoningLayer:
        def record_interpretation(self, state, **kwargs):
            interpretations.append(dict(kwargs))

        def evaluate_experiment_result(self, state, **kwargs):
            evaluations.append(dict(kwargs))

    class _Dispatcher:
        def __init__(self):
            self.state = _State()
            self._notes_log = ["note-a"]
            self.hypothesis_engine = _HypothesisEngine()
            self.reasoning_layer = _ReasoningLayer()

        async def _finalize_solve_result(self, result: SolveResult):
            return result

    dispatcher = _Dispatcher()
    result = SolveResult(success=False)
    experiment = SimpleNamespace(
        id="exp-1",
        inputs={"chain": "sqli"},
        expected_signal="flag or progress",
    )
    outcome = SimpleNamespace(flag="flag{ok}", reason="sqli verified")

    finalized = await coordinator._apply_terminal_success_contract(
        dispatcher,
        result=result,
        outcome=outcome,
        chain_name="sqli",
        active_hypothesis=hypothesis,
        experiment=experiment,
    )

    assert finalized is result
    assert result.success is True
    assert result.flag == "flag{ok}"
    assert result.reason == "sqli verified"
    assert result.notes == ["note-a"]
    assert dispatcher.state.stop_reason == "sqli verified"
    assert dispatcher.state.progress_markers == ["sqli verified"]
    assert feedback_calls == [
        {
            "hypothesis_id": "hyp-1",
            "progress_delta": "terminal",
            "observed_signal": "sqli verified",
            "experiment_id": "exp-1",
            "inputs": {"chain": "sqli"},
            "expected_signal": "flag or progress",
        }
    ]
    assert interpretations == [
        {
            "observation_ids": ["exp-1"],
            "content": "链路 sqli 命中终局信号：sqli verified",
            "hypothesis_ids": ["hyp-1"],
            "confidence": 0.9,
        }
    ]
    assert evaluations == [
        {
            "experiment_id": "exp-1",
            "progress_delta": "terminal",
            "observed_signal": "sqli verified",
        }
    ]


@pytest.mark.asyncio
async def test_coordinator_applies_final_recovery_contract():
    coordinator = CTFCoordinator()
    recorded: list[tuple[str, str]] = []
    emitted: list[str] = []
    retrospectives: list[tuple[str, str, str]] = []

    class _RecoveryController:
        def finalize(self, state, *, used_chains: list[str], no_progress_count: int):
            return RecoveryDecision(
                action="stop_exhausted",
                should_stop=True,
                reason="all chains exhausted",
            )

    class _Dispatcher:
        def __init__(self):
            self.recovery_controller = _RecoveryController()
            self.state = SimpleNamespace(stop_reason=None)
            self._notes_log = ["note-a"]

        def _record_recovery_decision(self, decision, *, chain_name: str):
            recorded.append((chain_name, decision.reason))

        def _emit(self, message: str):
            emitted.append(message)

        async def _store_retrospective(self, reason: str, target: str, chain_name: str):
            retrospectives.append((reason, target, chain_name))

        async def _finalize_solve_result(self, result: SolveResult):
            return result

    dispatcher = _Dispatcher()
    result = SolveResult(success=False)
    result.chain_used = ["sqli", "web"]

    finalized = await coordinator._apply_final_recovery_contract(
        dispatcher,
        result=result,
        target="http://ctf.local",
        detected_type="sqli",
        no_progress_rounds=3,
    )

    assert finalized is result
    assert result.reason == "all chains exhausted"
    assert result.notes == ["note-a"]
    assert dispatcher.state.stop_reason == "all chains exhausted"
    assert recorded == [("sqli", "all chains exhausted")]
    assert emitted == ["[CTF recovery] all chains exhausted"]
    assert retrospectives == [
        ("all chains exhausted", "http://ctf.local", "sqli")
    ]
