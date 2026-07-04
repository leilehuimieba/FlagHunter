from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from flaghunter.agents.crew.swarm_bridge import run_ctf_dispatcher_worker
from flaghunter.agents.pa_agent.blackboard import project_blackboard
from flaghunter.agents.pa_agent.blackboard_adapter import make_record_fact
from flaghunter.agents.pa_agent.claim_views import preferred_flag_summary
from flaghunter.agents.pa_agent.coordinator import CTFCoordinator
from flaghunter.agents.pa_agent.ctf_crew_coordinator import (
    CTFCrewCoordinator,
    CrewWorkerSpec,
)
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher, SolveResult
from flaghunter.agents.pa_agent.ctf_state import (
    CTFState,
    ClaimKind,
    ClaimLevel,
    ClaimStatus,
    VerificationDecision,
    VerificationMethod,
)
from flaghunter.agents.pa_agent.hypothesis_engine import HypothesisEngine
from flaghunter.agents.pa_agent.recovery import RecoveryController
from flaghunter.agents.pa_agent.reasoning import ReasoningLayer
from flaghunter.agents.pa_agent.verifier import CTFVerifier
from flaghunter.interface import cli as interface_cli
from flaghunter.interface import web_server
from flaghunter.harness.checkpoint_store import CheckpointStore
from flaghunter.mcp.server import mcp_tools


class _Runtime:
    environment = SimpleNamespace(available_tools=[])


class _StrategyMemory:
    def build_fingerprint(self, state):
        return SimpleNamespace(id="p1-fingerprint")

    def build_entry(self, *, state, fingerprint, chain_used, solved):
        return SimpleNamespace(id="p1-entry")

    async def save(self, entry):
        return None


def _enable_claims_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")


def _flag_claim(
    state: CTFState,
    value: str,
    *,
    runtime_supported: bool = False,
    verified: bool = False,
    retracted: bool = False,
):
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content=value,
        producer_type="verifier",
        producer_id="ctf_verifier",
        primary_trace_id=f"trace:{value}",
        source_channel="p1-invariant-test",
        confidence=0.7,
    )
    if runtime_supported:
        state.append_verification_record(
            claim.id,
            verifier_type="verifier",
            verifier_id="ctf_verifier",
            method=VerificationMethod.RUNTIME_HTTP,
            decision=VerificationDecision.RUNTIME_SUPPORTED,
            trace_id=f"verify:runtime:{value}",
            passed=True,
            sufficient_for_upgrade=False,
            submitted_value=value,
        )
    if verified:
        record = state.append_verification_record(
            claim.id,
            verifier_type="verifier",
            verifier_id="ctf_verifier",
            method=VerificationMethod.LOCAL_CHALLENGE_AUTO_VERIFY,
            decision=VerificationDecision.VERIFIED,
            trace_id=f"verify:verified:{value}",
            passed=True,
            sufficient_for_upgrade=True,
            submitted_value=value,
        )
        state.upgrade_claim_to_verified(
            claim.id,
            verification_record_id=record.id,
            verifier_id="ctf_verifier",
        )
    if retracted:
        record = state.append_verification_record(
            claim.id,
            verifier_type="verifier",
            verifier_id="ctf_verifier",
            method=VerificationMethod.PLATFORM_SUBMIT,
            decision=VerificationDecision.REJECTED,
            trace_id=f"verify:rejected:{value}",
            passed=False,
            sufficient_for_upgrade=False,
            submitted_value=value,
        )
        state.retract_claim(
            claim.id,
            reason="platform rejected it",
            trace_id=record.trace_id,
            actor_id="ctf_verifier",
        )
    return claim


def _verified_record_for(state: CTFState, claim_id: str):
    claim = state.get_claim(claim_id)
    assert claim is not None
    for record_id in claim.verification_record_ids:
        record = state.verification_records_by_id[record_id]
        if record.decision == VerificationDecision.VERIFIED:
            return record
    raise AssertionError("verified record not found")


class _CoordinatorContractDispatcher:
    def __init__(self, state: CTFState, ingress_handoff: dict[str, object] | None = None):
        self._notes_log = []
        self.state = state
        self._ingress_handoff = dict(ingress_handoff or {})
        self.recorded_events: list[tuple[str, dict[str, object]]] = []
        self.finalized_results: list[SolveResult] = []

    def _record_session_event(self, event_type: str, payload: dict[str, object]):
        self.recorded_events.append((event_type, dict(payload)))

    def _write_checkpoint(self, label: str, payload: dict[str, object]):
        return None

    async def _finalize_solve_result(self, result: SolveResult):
        self.finalized_results.append(result)
        return result


def _verified_selector_hint(value: str) -> str:
    return (
        "[control_decision]\n"
        "decisionKind=direct_execute\n"
        "nextAction=verify_or_submit_flag\n"
        "driver=blackboard.verified_flag\n"
        f"verifiedFlag={value}"
    )


def _verified_selector_decision() -> dict[str, object]:
    return {
        "shouldRun": True,
        "decisionKind": "direct_execute",
        "reason": "verified flag already present in blackboard",
        "nextAction": "verify_or_submit_flag",
        "driver": "blackboard.verified_flag",
    }


def _legacy_verified_selector_snapshot(value: str) -> dict[str, object]:
    return {
        "observations": [],
        "artifacts": [],
        "runtime_flags": [],
        "verified_flags": [
            {
                "value": value,
                "level": "verified",
                "evidence_source": "prior-entry-selector",
                "rationale": "selector only; not canonical proof",
            }
        ],
    }


def _web_verified_selector_task(value: str, *, replay: bool = False) -> dict[str, object]:
    task = {
        "id": "web-p1-selector",
        "title": "web selector task",
        "target": "http://ctf.local",
        "goal": "get flag",
        "mode": "ctf",
        "modeSubtype": "web",
        "controlDecision": _verified_selector_decision(),
        "ctfStateSnapshot": _legacy_verified_selector_snapshot(value),
    }
    if replay:
        task.update(
            {
                "sourceRunId": "run-web-replay-selector",
                "resumeFromRunId": "run-web-replay-selector",
                "resumeFromCheckpointId": "checkpoint-web-replay-selector",
                "resumeSummary": "stop_reason=flag_verified",
                "sessionContext": {
                    "resumeContext": {
                        "runId": "run-web-replay-selector",
                        "checkpointId": "checkpoint-web-replay-selector",
                        "summary": "stop_reason=flag_verified",
                    }
                },
            }
        )
    return task


def _mcp_verified_selector_entry(value: str):
    return mcp_tools.TaskEntry(
        id="mcp-p1-selector",
        task="mcp selector task",
        status="pending",
        created_at="2026-07-03T00:00:00",
        agent=SimpleNamespace(runtime=None),
        target="http://ctf.local",
        mode="ctf",
        modeSubtype="web",
        controlDecision=_verified_selector_decision(),
        ctfStateSnapshot=_legacy_verified_selector_snapshot(value),
    )


def _cross_entry_verified_selector_cases(value: str):
    cli_hint = interface_cli._ctf_dispatcher_hint(
        control_decision=_verified_selector_decision(),
        blackboard_snapshot={
            "facts": [{"kind": "verified_flag", "value": value}],
            "pending_verifications": [],
        },
    )
    web_task = _web_verified_selector_task(value)
    replay_task = _web_verified_selector_task(value, replay=True)
    mcp_entry = _mcp_verified_selector_entry(value)
    return [
        ("cli_hint", cli_hint, None),
        (
            "ingress_handoff",
            "",
            {
                "decisionKind": "direct_execute",
                "nextAction": "verify_or_submit_flag",
                "driver": "blackboard.verified_flag",
                "verifiedFlag": value,
            },
        ),
        (
            "web_server_ingress",
            web_server._ctf_dispatcher_hint(web_task),
            web_server._build_ingress_handoff(web_task),
        ),
        (
            "web_replay_ingress",
            web_server._ctf_dispatcher_hint(replay_task),
            web_server._build_ingress_handoff(replay_task),
        ),
        (
            "mcp_ingress",
            mcp_tools._ctf_dispatcher_hint(mcp_entry),
            mcp_tools._build_ingress_handoff(mcp_entry),
        ),
    ]


def test_p1_create_claim_cannot_create_verified(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")

    with pytest.raises(ValueError, match="directly create verified"):
        state.create_claim(
            kind=ClaimKind.FLAG_FOUND,
            content="flag{direct_verified_blocked}",
            level=ClaimLevel.VERIFIED,
            producer_type="solver",
            producer_id="unit-test",
            primary_trace_id="trace-direct-verified",
        )

    assert state.claims_by_id == {}


def test_p1_record_fact_cannot_create_verified_claim(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    record_fact = make_record_fact(state)

    record_fact(
        '{"kind":"flag_found","content":"flag{record_fact_verified_blocked}",'
        '"level":"verified","confidence":1.0}'
    )

    assert state.claims_by_id == {}
    assert any(
        obs.kind == "model_fact"
        and "flag{record_fact_verified_blocked}" in obs.value
        for obs in state.observations
    )


def test_p1_restored_verified_claim_requires_sufficient_record(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content="flag{forged_after_resume}",
        producer_type="solver",
        producer_id="unit-test",
        primary_trace_id="trace-forged",
        confidence=1.0,
    )
    snapshot = state.to_snapshot()
    snapshot["claims_by_id"][claim.id]["level"] = "verified"
    snapshot["claims_by_id"][claim.id]["verification_record_ids"] = ["missing-record"]
    snapshot["verification_records_by_id"] = {}

    restored = CTFState.from_snapshot(snapshot)
    restored_claim = restored.get_claim(claim.id)
    summary = preferred_flag_summary(restored)

    assert restored_claim is not None
    assert restored_claim.level == ClaimLevel.CONJECTURE
    assert restored_claim.status == ClaimStatus.ACTIVE
    assert restored_claim.metadata["restore_integrity_warning"]
    assert summary["verifiedFlags"] == []
    assert restored.strongest_claim(ClaimKind.FLAG_FOUND).level != ClaimLevel.VERIFIED


def test_p1_bucket_fallback_mixed_canonical_and_legacy(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.add_flag(
        "flag{legacy_verified_when_canonical_verified_empty}",
        level="verified",
        evidence_source="legacy",
        confidence=0.9,
    )
    state.add_flag(
        "flag{legacy_runtime_when_canonical_runtime_empty}",
        level="runtime",
        evidence_source="legacy",
        confidence=0.8,
    )
    _flag_claim(state, "flag{canonical_candidate_only}")
    _flag_claim(state, "flag{canonical_retracted_only}", retracted=True)

    summary = preferred_flag_summary(state)
    board = project_blackboard(state)

    assert summary["verifiedFlags"] == [
        "flag{legacy_verified_when_canonical_verified_empty}"
    ]
    assert summary["runtimeFlags"] == [
        "flag{legacy_runtime_when_canonical_runtime_empty}"
    ]
    assert summary["candidateFlags"] == ["flag{canonical_candidate_only}"]
    assert summary["retractedFlags"] == ["flag{canonical_retracted_only}"]
    assert any(
        item["kind"] == "verified_flag"
        and item["value"] == "flag{legacy_verified_when_canonical_verified_empty}"
        for item in board["facts"]
    )
    assert any(
        item["kind"] == "candidate_flag"
        and item["description"] == "flag{canonical_candidate_only}"
        for item in board["intents"]
    )


@pytest.mark.asyncio
async def test_p1_verifier_double_write_end_to_end(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    verifier = CTFVerifier(runtime=None)

    candidate = await verifier.verify_flag(
        state,
        flag="flag{p1_candidate}",
        evidence_source="source-leak",
        rationale="found in source",
    )
    runtime = await verifier.verify_flag(
        state,
        flag="flag{p1_runtime}",
        evidence_source="http-response",
        rationale="echoed by target",
    )
    state.local_challenge_auto_verify = True
    verified = await verifier.verify_flag(
        state,
        flag="flag{p1_verified}",
        evidence_source="http-response",
        rationale="local challenge runtime flag",
    )
    rejected = verifier.reject_flag(
        state,
        flag="flag{p1_rejected}",
        evidence_source="platform-submit",
        rationale="platform rejected it",
    )

    assert [candidate.decision, runtime.decision, verified.decision, rejected.decision] == [
        "candidate",
        "runtime",
        "verified",
        "rejected",
    ]
    summary = preferred_flag_summary(state)
    board = project_blackboard(state)
    recovery = RecoveryController(HypothesisEngine()).finalize(
        state,
        used_chains=["web"],
        no_progress_count=0,
    )
    report = ReasoningLayer().generate_stop_report(
        state,
        reason="flag verified",
        missing_capabilities=[],
    )

    assert summary["verifiedFlags"] == ["flag{p1_verified}"]
    assert summary["runtimeFlags"] == ["flag{p1_runtime}"]
    assert summary["candidateFlags"] == ["flag{p1_candidate}"]
    assert summary["retractedFlags"] == ["flag{p1_rejected}"]
    verified_claim = state.strongest_claim(ClaimKind.FLAG_FOUND)
    assert verified_claim is not None
    assert verified_claim.content == "flag{p1_verified}"
    record = _verified_record_for(state, verified_claim.id)
    assert record.decision == VerificationDecision.VERIFIED
    assert record.passed is True
    assert record.sufficient_for_upgrade is True
    assert any(item["kind"] == "verified_flag" for item in board["facts"])
    assert recovery.should_stop is True
    assert recovery.action == "stop_generic"
    assert report.verified_flags == ["flag{p1_verified}"]
    assert report.runtime_flags == ["flag{p1_runtime}"]
    assert report.rejected_flags == ["flag{p1_rejected}"]


def test_p1_checkpoint_resume_preserves_verified_record_link(monkeypatch, tmp_path):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    claim = _flag_claim(state, "flag{checkpoint_p1_verified}", verified=True)
    record = _verified_record_for(state, claim.id)

    store = CheckpointStore(tmp_path / "checkpoints")
    store.save_checkpoint(
        run_id="run-p1-checkpoint",
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )

    restored = CTFState.from_snapshot(
        store.latest_checkpoint("run-p1-checkpoint")["state"]
    )
    restored_claim = restored.get_claim(claim.id)
    restored_record = restored.verification_records_by_id[record.id]

    assert restored_claim is not None
    assert restored_claim.level == ClaimLevel.VERIFIED
    assert restored_claim.verification_record_ids == [record.id]
    assert restored_record.claim_id == claim.id
    assert restored_record.decision == VerificationDecision.VERIFIED
    assert restored_record.passed is True
    assert restored_record.sufficient_for_upgrade is True
    assert preferred_flag_summary(restored)["verifiedFlags"] == [
        "flag{checkpoint_p1_verified}"
    ]


@pytest.mark.asyncio
async def test_p1_crew_summary_reads_canonical_verified_without_legacy_verified(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    _flag_claim(state, "flag{crew_p1_verified}", verified=True)

    async def _runner(spec: dict, shared_state: CTFState, cancel_event: asyncio.Event):
        return {
            "worker_id": spec["worker_id"],
            "observations": [],
            "candidate_flags": [],
            "verified_flag": None,
        }

    coordinator = CTFCrewCoordinator(
        state=state,
        verifier=CTFVerifier(runtime=None),
        worker_runner=_runner,
        timeout_seconds=1,
    )
    summary = await coordinator.run(
        [CrewWorkerSpec(worker_id="worker-1", worker_type="recon", task="noop")]
    )

    assert state.verified_flags == []
    assert summary.stop_reason == "flag_verified"
    assert summary.verified_flag == "flag{crew_p1_verified}"
    assert summary.to_dict()["flag_summary"]["verifiedFlags"] == [
        "flag{crew_p1_verified}"
    ]


@pytest.mark.asyncio
async def test_p1_swarm_state_diff_reads_canonical_runtime_and_retracted(monkeypatch):
    _enable_claims_v1(monkeypatch)

    class _Dispatcher:
        def __init__(self):
            self.state = CTFState(target="http://ctf.local", goal="get flag")
            _flag_claim(
                self.state,
                "flag{swarm_p1_runtime}",
                runtime_supported=True,
            )
            _flag_claim(self.state, "flag{swarm_p1_retracted}", retracted=True)

        async def run(self, *, target: str, goal: str, type: str, hint: str):
            return SimpleNamespace(success=False, flag=None, reason="worker done")

    result = await run_ctf_dispatcher_worker(
        _Dispatcher(),
        target="http://ctf.local",
        goal="get flag",
        chtype="web",
        hint="",
        worker_id="worker-p1",
        worker_type="exploit",
        cancel_event=None,
    )

    assert result["runtime_flags"] == ["flag{swarm_p1_runtime}"]
    assert result["state_diff"]["runtime_flags"] == ["flag{swarm_p1_runtime}"]
    assert result["state_diff"]["rejected_flags"] == ["flag{swarm_p1_retracted}"]
    assert result["state_diff"]["retracted_flags"] == ["flag{swarm_p1_retracted}"]


@pytest.mark.asyncio
async def test_p1_dispatcher_finalize_accepts_verifier_canonical_verified(monkeypatch):
    _enable_claims_v1(monkeypatch)
    dispatcher = CTFTaskDispatcher(runtime=_Runtime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="get flag")
    dispatcher.strategy_memory = _StrategyMemory()  # type: ignore[assignment]
    dispatcher.state.local_challenge_auto_verify = True
    verifier = CTFVerifier(runtime=None)

    verification = await verifier.verify_flag(
        dispatcher.state,
        flag="flag{dispatcher_p1_verified}",
        evidence_source="http-response",
        rationale="local challenge runtime flag",
    )
    result = await dispatcher._finalize_solve_result(
        SolveResult(success=False, reason="legacy path did not set success")
    )

    assert verification.decision == "verified"
    assert result.success is True
    assert result.flag == "flag{dispatcher_p1_verified}"
    assert result.reason == "canonical_verified_flag_claim"
    assert dispatcher.state.strongest_claim(ClaimKind.FLAG_FOUND).level == ClaimLevel.VERIFIED


@pytest.mark.asyncio
async def test_p1_coordinator_verified_selector_hint_alone_cannot_succeed(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    dispatcher = _CoordinatorContractDispatcher(state)

    result = await CTFCoordinator()._apply_verified_flag_contract(
        dispatcher,
        hint=_verified_selector_hint("flag{hint_only_not_verified}"),
    )

    assert result is None
    assert dispatcher.finalized_results == []
    assert state.verified_flags == []
    assert state.find_claims_by_kind(ClaimKind.FLAG_FOUND, include_inactive=True) == []
    assert all(
        event_type != "verification_decision"
        for event_type, _ in dispatcher.recorded_events
    )


@pytest.mark.asyncio
async def test_p1_coordinator_verified_selector_reads_existing_canonical_claim(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    _flag_claim(state, "flag{already_verified_by_verifier}", verified=True)
    dispatcher = _CoordinatorContractDispatcher(state)

    result = await CTFCoordinator()._apply_verified_flag_contract(
        dispatcher,
        hint=_verified_selector_hint("flag{already_verified_by_verifier}"),
    )

    assert result is not None
    assert result.success is True
    assert result.flag == "flag{already_verified_by_verifier}"
    assert result.reason == "canonical_verified_flag_claim"
    assert dispatcher.finalized_results == [result]
    assert state.verified_flags == []
    assert all(
        event_type != "verification_decision"
        for event_type, _ in dispatcher.recorded_events
    )


@pytest.mark.asyncio
async def test_p1_coordinator_verified_selector_cannot_forge_mismatched_claim(
    monkeypatch,
):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")
    _flag_claim(state, "flag{different_verified_by_verifier}", verified=True)
    dispatcher = _CoordinatorContractDispatcher(state)

    result = await CTFCoordinator()._apply_verified_flag_contract(
        dispatcher,
        hint=_verified_selector_hint("flag{forged_by_control_contract}"),
    )

    assert result is None
    assert dispatcher.finalized_results == []
    assert state.verified_flags == []
    assert preferred_flag_summary(state)["verifiedFlags"] == [
        "flag{different_verified_by_verifier}"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entry_name", "hint", "handoff"),
    _cross_entry_verified_selector_cases("flag{cross_entry_selector_only}"),
)
async def test_p1_cross_entry_verified_selector_only_cannot_succeed_without_claim(
    monkeypatch,
    entry_name: str,
    hint: str,
    handoff: dict[str, object] | None,
):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal=f"get flag via {entry_name}")
    dispatcher = _CoordinatorContractDispatcher(state, ingress_handoff=handoff)

    result = await CTFCoordinator()._apply_verified_flag_contract(
        dispatcher,
        hint=hint,
    )

    assert "verifiedFlag=flag{cross_entry_selector_only}" in hint or (
        handoff is not None and handoff.get("verifiedFlag") == "flag{cross_entry_selector_only}"
    )
    assert result is None
    assert dispatcher.finalized_results == []
    assert state.verified_flags == []
    assert state.find_claims_by_kind(ClaimKind.FLAG_FOUND, include_inactive=True) == []
    assert all(
        event_type != "verification_decision"
        for event_type, _ in dispatcher.recorded_events
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entry_name", "hint", "handoff"),
    _cross_entry_verified_selector_cases("flag{cross_entry_canonical_verified}"),
)
async def test_p1_cross_entry_verified_selector_only_reads_existing_canonical_claim(
    monkeypatch,
    entry_name: str,
    hint: str,
    handoff: dict[str, object] | None,
):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal=f"get flag via {entry_name}")
    _flag_claim(state, "flag{cross_entry_canonical_verified}", verified=True)
    dispatcher = _CoordinatorContractDispatcher(state, ingress_handoff=handoff)

    result = await CTFCoordinator()._apply_verified_flag_contract(
        dispatcher,
        hint=hint,
    )

    assert "verifiedFlag=flag{cross_entry_canonical_verified}" in hint or (
        handoff is not None and handoff.get("verifiedFlag") == "flag{cross_entry_canonical_verified}"
    )
    assert result is not None
    assert result.success is True
    assert result.flag == "flag{cross_entry_canonical_verified}"
    assert result.reason == "canonical_verified_flag_claim"
    assert dispatcher.finalized_results == [result]
    assert state.verified_flags == []
    assert len(state.find_claims_by_kind(ClaimKind.FLAG_FOUND, include_inactive=True)) == 1
    assert all(
        event_type != "verification_decision"
        for event_type, _ in dispatcher.recorded_events
    )
