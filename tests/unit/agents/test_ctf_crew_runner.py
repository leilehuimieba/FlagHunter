"""D4: headless CTF crew runner — shared by CLI/web (and TUI delegates its
stop-reason mapping here). Covers the pure stop-reason normalization and the
assembly/mapping of run_ctf_crew_solve via lightweight fakes (no real runtime)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent import ctf_crew_runner
from flaghunter.agents.pa_agent.ctf_crew_runner import (
    derive_crew_stop_reason,
    run_ctf_crew_solve,
)


def _summary(**kwargs):
    base = dict(stop_reason="", worker_results={}, verified_flag=None, started_workers=[])
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_derive_crew_stop_reason_passthrough_and_mapping():
    # explicit terminal reasons pass through
    assert derive_crew_stop_reason(_summary(stop_reason="flag_verified")) == "flag_verified"
    assert derive_crew_stop_reason(_summary(stop_reason="crew_timeout")) == "crew_timeout"
    assert (
        derive_crew_stop_reason(_summary(stop_reason="worker_error:boom"))
        == "worker_error:boom"
    )
    # wrong-flag feedback wins over generic
    assert (
        derive_crew_stop_reason(
            _summary(worker_results={"w1": {"reason": "got Wrong Flag Feedback again"}})
        )
        == "wrong_flag_feedback"
    )
    # already-solved detection
    assert (
        derive_crew_stop_reason(
            _summary(worker_results={"w1": {"reason": "challenge already solved"}})
        )
        == "challenge_already_solved"
    )
    # missing tools → capability ceiling
    assert (
        derive_crew_stop_reason(
            _summary(worker_results={"w1": {"reason": "x", "missing_tools": ["nmap"]}})
        )
        == "capability_ceiling"
    )
    # workers_completed with nothing else → exhausted
    assert (
        derive_crew_stop_reason(_summary(stop_reason="workers_completed"))
        == "all_hypotheses_exhausted"
    )
    # fallback when nothing matches
    assert derive_crew_stop_reason(_summary()) == "workers_completed"


class _CapRegistry:
    async def full_check(self):
        return None

    def to_dict(self):
        return {"tools": []}


class _FakeDispatcher:
    """Minimal stand-in for CTFTaskDispatcher used by the crew runner."""

    instances: list["_FakeDispatcher"] = []

    def __init__(self, *, runtime=None, progress_callback=None, llm=None, profile="ctf"):
        from flaghunter.knowledge.profile import Profile, get_profile

        self.runtime = runtime
        self.progress_callback = progress_callback
        self.llm = llm
        # Mirror the real dispatcher: resolve a profile name to a Profile object.
        self.profile = profile if isinstance(profile, Profile) else get_profile(profile)
        self.state = None
        self.verifier = SimpleNamespace(name="verifier")
        self.capability_registry = _CapRegistry()
        self.reasoning_layer = SimpleNamespace(
            generate_stop_report=lambda *a, **k: None
        )
        self.hypothesis_engine = SimpleNamespace(generate=lambda state: None)
        self._challenge_context = None
        self.align_result = None
        _FakeDispatcher.instances.append(self)

    def _apply_submit_profile(self, profile):
        self.applied_profile = dict(profile or {})

    async def _snapshot_platform_context(self, target):
        return None

    async def _phase_recon(self, target):
        return {"html": "<html>login</html>", "content": "login portal"}

    def _align_platform_challenge(self, target, page_features):
        return self.align_result

    def _build_already_solved_reason(self):
        return "already solved on platform"


class _FakeSpec:
    def __init__(self, worker_id, worker_type, task):
        self.worker_id = worker_id
        self.worker_type = worker_type
        self.task = task


class _FakeCoordinator:
    last: "_FakeCoordinator | None" = None

    def __init__(self, *, state, verifier, worker_runner, progress_callback=None):
        self.state = state
        self.verifier = verifier
        self.worker_runner = worker_runner
        self.progress_callback = progress_callback
        _FakeCoordinator.last = self

    def build_worker_specs(self, *, target, page_features=None):
        return [_FakeSpec("recon-1", "recon", "recon the surface")]

    async def run_with_shadow_graph(self, *, target, page_features=None):
        return _summary(
            stop_reason="flag_verified",
            verified_flag="flag{crew_ok}",
            started_workers=["recon-1"],
            worker_results={"recon-1": {"reason": "solved", "missing_tools": []}},
        )


@pytest.fixture(autouse=True)
def _patch_crew_deps(monkeypatch):
    _FakeDispatcher.instances = []
    _FakeCoordinator.last = None
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.CTFTaskDispatcher", _FakeDispatcher
    )
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_crew_coordinator.CTFCrewCoordinator",
        _FakeCoordinator,
    )
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_planner.detect_type",
        lambda blob, target: "web",
    )


@pytest.mark.asyncio
async def test_run_ctf_crew_solve_happy_path_maps_summary_to_solve_result():
    events: list[tuple[str, str]] = []
    progress: list[str] = []

    solve_result, dispatcher = await run_ctf_crew_solve(
        runtime=SimpleNamespace(),
        llm=SimpleNamespace(),
        target="http://ctf.local",
        goal="flag",
        chtype="auto",
        hint="go",
        progress_callback=progress.append,
        worker_event=lambda wid, evt, data: events.append((wid, evt)),
    )

    assert solve_result.success is True
    assert solve_result.flag == "flag{crew_ok}"
    assert solve_result.chain_used == ["recon-1"]
    assert solve_result.reason == "flag_verified"
    # returns the planning dispatcher (exposes .state for downstream plumbing)
    assert dispatcher is _FakeDispatcher.instances[0]
    assert dispatcher.state.detected_type == "web"
    # coordinator wired against the planning dispatcher's shared state + verifier
    assert _FakeCoordinator.last.state is dispatcher.state
    assert _FakeCoordinator.last.verifier is dispatcher.verifier
    # spawn events surfaced for the planned worker
    assert ("recon-1", "spawn") in events


@pytest.mark.asyncio
async def test_run_ctf_crew_solve_short_circuits_on_already_solved():
    # First constructed dispatcher reports an already-solved alignment.
    captured = {}

    real_init = _FakeDispatcher.__init__

    def _init(self, **kwargs):
        real_init(self, **kwargs)
        self.align_result = {"already_solved": True, "challenge_id": "c1"}
        captured["d"] = self

    _FakeDispatcher.__init__ = _init
    try:
        solve_result, dispatcher = await run_ctf_crew_solve(
            runtime=SimpleNamespace(),
            llm=SimpleNamespace(),
            target="http://ctf.local",
            goal="flag",
        )
    finally:
        _FakeDispatcher.__init__ = real_init

    assert solve_result.success is False
    assert solve_result.flag is None
    assert solve_result.reason == "already solved on platform"
    # short-circuit: never built a coordinator
    assert _FakeCoordinator.last is None
    assert dispatcher.state.stop_reason == "challenge_already_solved"
