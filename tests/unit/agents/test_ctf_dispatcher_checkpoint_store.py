from __future__ import annotations

from types import SimpleNamespace

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.agents.pa_agent.blackboard import project_blackboard
from flaghunter.agents.pa_agent.claim_views import preferred_flag_summary
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.ctf_state import (
    CTFState,
    ClaimKind,
    ClaimLevel,
    ClaimStatus,
    VerificationDecision,
    VerificationMethod,
)
from flaghunter.agents.pa_agent.strategy_memory import (
    ChallengeFingerprint,
    StrategyMemoryEntry,
    StrategyMemoryEntryMetadata,
    StrategyMemoryStore,
)
from flaghunter.harness.checkpoint_store import CheckpointStore
from flaghunter.harness.session_ledger import SessionLedger
from flaghunter.tools.notes import set_notes_file


class _CheckpointRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "checkpoint-home"}
        if action == "get_content":
            return {
                "content": "welcome flag{checkpoint_verified_ok}",
                "html": "<html><body>flag{checkpoint_verified_ok}</body></html>",
            }
        if action == "get_forms":
            return {"forms": []}
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _CheckpointSQLiSubmitRejectRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])

    async def browser_action(self, action: str, **kwargs):
        if action == "navigate":
            return {"url": "http://ctf.local/", "title": "checkpoint-submit-reject"}
        if action == "get_content":
            return {
                "content": "login portal",
                "html": """
                <html><body>
                  <form action="http://ctf.local/login" method="post">
                    <input name="username" />
                    <input name="password" />
                  </form>
                </body></html>
                """,
            }
        if action == "get_forms":
            return {
                "forms": [
                    {
                        "action": "http://ctf.local/login",
                        "method": "post",
                        "inputs": [
                            {"name": "username", "type": "text"},
                            {"name": "password", "type": "password"},
                        ],
                    }
                ]
            }
        return {"error": f"unexpected action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        method = str(kwargs.get("method") or "").upper()
        url = str(kwargs.get("url") or "")
        if action == "post" and url == "http://ctf.local/login":
            return {"status_code": 200, "body": "login ok"}
        if action == "request" and method == "POST" and url == "http://submit.local/flag":
            return {"status_code": 200, "body": "wrong flag"}
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


def _checkpoint_flag_claim(
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
        source_channel="checkpoint-test",
        confidence=0.7,
        metadata={"source": "checkpoint-test", "value": value},
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
            evidence_summary="runtime echoed flag",
            submitted_value=value,
            metadata={"path": "runtime"},
        )
    if verified:
        record = state.append_verification_record(
            claim.id,
            verifier_type="verifier",
            verifier_id="ctf_verifier",
            method=VerificationMethod.PLATFORM_SUBMIT,
            decision=VerificationDecision.VERIFIED,
            trace_id=f"verify:verified:{value}",
            passed=True,
            sufficient_for_upgrade=True,
            evidence_summary="platform accepted flag",
            submitted_value=value,
            metadata={"path": "platform"},
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
            evidence_summary="platform rejected flag",
            submitted_value=value,
            metadata={"path": "platform"},
        )
        state.retract_claim(
            claim.id,
            reason="platform rejected it",
            trace_id=record.trace_id,
            actor_id="ctf_verifier",
        )
    return claim


@pytest.mark.asyncio
async def test_dispatcher_writes_start_and_finish_checkpoints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_checkpoint.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(
        runtime=_CheckpointRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="web",
        hint="",
        run_id="run-checkpoint-dispatcher",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    store = CheckpointStore(tmp_path / "checkpoints")
    events = SessionLedger(tmp_path / "ledgers").read_events("run-checkpoint-dispatcher")
    checkpoints = store.list_checkpoints("run-checkpoint-dispatcher")
    latest = store.latest_checkpoint("run-checkpoint-dispatcher")

    assert result.success is True
    assert result.flag == "flag{checkpoint_verified_ok}"
    assert [item["label"] for item in checkpoints] == [
        "dispatcher_started",
        "task_finished",
    ]
    event_types = [event["event_type"] for event in events]
    assert "dispatcher_started" in event_types
    assert "checkpoint_written" in event_types
    assert "verification_decision" in event_types
    assert "artifact_registered" in event_types
    assert "task_finished" in event_types
    assert event_types.index("dispatcher_started") < event_types.index("checkpoint_written")
    assert event_types.index("checkpoint_written") < event_types.index("verification_decision")
    assert event_types.index("verification_decision") < event_types.index("artifact_registered")
    assert event_types.index("artifact_registered") < event_types.index("task_finished")
    assert event_types[-1] == "checkpoint_written"
    assert latest is not None
    assert latest["metadata"]["success"] is True
    assert latest["metadata"]["flag"] == "flag{checkpoint_verified_ok}"
    assert events[1]["payload"]["label"] == "dispatcher_started"
    artifact_event = next(event for event in events if event["event_type"] == "artifact_registered")
    assert artifact_event["payload"]["title"] == "ctf_flag"
    assert artifact_event["payload"]["producer"] == "verifier"
    assert artifact_event["payload"]["metadata"]["category"] == "flag_verified"
    assert artifact_event["payload"]["metadata"]["note_category"] == "artifact"
    assert events[-1]["payload"]["label"] == "task_finished"
    restored = CTFState.from_snapshot(latest["state"])
    assert restored.target == "http://ctf.local"
    assert restored.verified_flags[0].value == "flag{checkpoint_verified_ok}"


@pytest.mark.asyncio
async def test_dispatcher_persists_resume_ingress_into_start_event_and_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_checkpoint_resume.json")
    notes_module._notes.clear()

    dispatcher = CTFTaskDispatcher(
        runtime=_CheckpointRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )

    result = await dispatcher.run(
        target="http://ctf.local/",
        goal="拿到flag",
        type="web",
        hint="",
        challenge_context={
            "resumeContext": {
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "checkpointLabel": "task_failed",
                "stopReason": "wrong_flag_feedback",
                "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
            }
        },
        run_id="run-checkpoint-resume",
        ledger_root=tmp_path / "ledgers",
        checkpoint_root=tmp_path / "checkpoints",
    )

    store = CheckpointStore(tmp_path / "checkpoints")
    events = SessionLedger(tmp_path / "ledgers").read_events("run-checkpoint-resume")
    checkpoints = store.list_checkpoints("run-checkpoint-resume")
    started_checkpoint = checkpoints[0]

    assert result.success is True
    assert events[0]["event_type"] == "dispatcher_started"
    assert events[0]["payload"]["has_resume_context"] is True
    assert events[0]["payload"]["resume_run_id"] == "run-prev-1"
    assert events[0]["payload"]["resume_checkpoint_id"] == "checkpoint-prev-1"
    assert started_checkpoint["label"] == "dispatcher_started"
    assert started_checkpoint["metadata"]["has_resume_context"] is True
    assert started_checkpoint["metadata"]["resume_run_id"] == "run-prev-1"
    assert started_checkpoint["metadata"]["resume_checkpoint_id"] == "checkpoint-prev-1"
    assert events[1]["event_type"] == "checkpoint_written"
    assert events[1]["payload"]["metadata"]["has_resume_context"] is True
    assert events[1]["payload"]["metadata"]["resume_run_id"] == "run-prev-1"
    assert events[1]["payload"]["metadata"]["resume_checkpoint_id"] == "checkpoint-prev-1"


def test_restore_context_hydrates_state_from_resume_checkpoint(tmp_path) -> None:
    previous_state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    previous_state.add_observation(
        "ssti_engine_identified",
        "tornado",
        source="resume-checkpoint",
        metadata={"engine": "tornado"},
    )
    previous_state.add_flag(
        "flag{runtime_from_checkpoint}",
        level="runtime",
        evidence_source="runtime-http",
        rationale="carried from previous run",
    )
    previous_state.add_flag(
        "flag{rejected_from_checkpoint}",
        level="rejected",
        evidence_source="user-confirm",
        rationale="wrong flag from previous run",
    )

    store = CheckpointStore(tmp_path / "checkpoints")
    record = store.save_checkpoint(
        run_id="run-prev-1",
        label="task_failed",
        state_snapshot=previous_state.to_snapshot(),
        metadata={"reason": "wrong_flag_feedback"},
    )

    dispatcher = CTFTaskDispatcher(
        runtime=_CheckpointRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(target="http://ctf.local", goal="继续拿到flag")
    dispatcher._challenge_context = {
        "resumeContext": {
            "runId": "run-prev-1",
            "checkpointId": record["checkpoint_id"],
            "summary": "resume from prior checkpoint",
        }
    }
    dispatcher._setup_checkpoint_store(
        run_id="run-current-1",
        checkpoint_root=tmp_path / "checkpoints",
    )

    dispatcher._restore_context()

    assert dispatcher.state is not None
    assert dispatcher.state.goal == "继续拿到flag"
    assert dispatcher.state.target == "http://ctf.local"
    assert dispatcher.state.detected_type == "web"
    assert any(
        obs.kind == "ssti_engine_identified" and obs.value == "tornado"
        for obs in dispatcher.state.observations
    )
    assert dispatcher.state.has_flag("flag{runtime_from_checkpoint}", level="runtime")
    assert dispatcher.state.has_flag("flag{rejected_from_checkpoint}", level="rejected")


def test_checkpoint_round_trip_restores_canonical_verified_claim(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    claim = _checkpoint_flag_claim(state, "flag{checkpoint_canonical_verified}", verified=True)

    store = CheckpointStore(tmp_path / "checkpoints")
    record = store.save_checkpoint(
        run_id="run-canonical-verified",
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )
    latest = store.latest_checkpoint("run-canonical-verified")
    restored = CTFState.from_snapshot(latest["state"])
    restored_claim = restored.get_claim(claim.id)
    strongest = restored.strongest_claim(ClaimKind.FLAG_FOUND)
    summary = preferred_flag_summary(restored)
    board = project_blackboard(restored)

    assert latest["checkpoint_id"] == record["checkpoint_id"]
    assert restored_claim is not None
    assert restored_claim.id == claim.id
    assert restored_claim.level == ClaimLevel.VERIFIED
    assert restored_claim.status == ClaimStatus.ACTIVE
    assert strongest is not None
    assert strongest.id == claim.id
    assert summary["verifiedFlags"] == ["flag{checkpoint_canonical_verified}"]
    assert any(
        item["kind"] == "verified_flag"
        and item["value"] == "flag{checkpoint_canonical_verified}"
        for item in board["facts"]
    )


def test_checkpoint_round_trip_restores_runtime_supported_claim(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    claim = _checkpoint_flag_claim(
        state,
        "flag{checkpoint_canonical_runtime}",
        runtime_supported=True,
    )

    store = CheckpointStore(tmp_path / "checkpoints")
    store.save_checkpoint(
        run_id="run-canonical-runtime",
        label="runtime_pending",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )
    restored = CTFState.from_snapshot(
        store.latest_checkpoint("run-canonical-runtime")["state"]
    )
    restored_claim = restored.get_claim(claim.id)
    record_id = restored_claim.verification_record_ids[0]
    restored_record = restored.verification_records_by_id[record_id]
    summary = preferred_flag_summary(restored)
    board = project_blackboard(restored)

    assert restored_claim is not None
    assert restored_claim.level == ClaimLevel.CONJECTURE
    assert restored_record.decision == VerificationDecision.RUNTIME_SUPPORTED
    assert restored_record.method == VerificationMethod.RUNTIME_HTTP
    assert restored_record.passed is True
    assert restored_record.sufficient_for_upgrade is False
    assert summary["runtimeFlags"] == ["flag{checkpoint_canonical_runtime}"]
    assert any(
        item["kind"] == "runtime_flag"
        and item["value"] == "flag{checkpoint_canonical_runtime}"
        for item in board["facts"]
    )


def test_checkpoint_round_trip_restores_retracted_claim(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    claim = _checkpoint_flag_claim(
        state,
        "flag{checkpoint_canonical_retracted}",
        retracted=True,
    )

    store = CheckpointStore(tmp_path / "checkpoints")
    store.save_checkpoint(
        run_id="run-canonical-retracted",
        label="wrong_flag",
        state_snapshot=state.to_snapshot(),
        metadata={},
    )
    restored = CTFState.from_snapshot(
        store.latest_checkpoint("run-canonical-retracted")["state"]
    )
    restored_claim = restored.get_claim(claim.id)
    record_id = restored_claim.verification_record_ids[0]
    restored_record = restored.verification_records_by_id[record_id]
    summary = preferred_flag_summary(restored)
    board = project_blackboard(restored)

    assert restored_claim is not None
    assert restored_claim.level == ClaimLevel.RETRACTED
    assert restored_claim.status == ClaimStatus.RETRACTED
    assert restored_claim.retracted_at is not None
    assert restored_record.decision == VerificationDecision.REJECTED
    assert restored.find_claims_by_kind(ClaimKind.FLAG_FOUND) == []
    assert summary["retractedFlags"] == ["flag{checkpoint_canonical_retracted}"]
    assert summary["rejectedFlags"] == ["flag{checkpoint_canonical_retracted}"]
    assert any(
        item["kind"] == "refuted_flag"
        and item["value"] == "flag{checkpoint_canonical_retracted}"
        for item in board["facts"]
    )


def test_legacy_checkpoint_without_claim_store_still_restores(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.add_flag(
        "flag{legacy_checkpoint_verified}",
        level="verified",
        evidence_source="legacy-checkpoint",
        confidence=0.9,
    )
    snapshot = state.to_snapshot()
    for key in (
        "claims_by_id",
        "claim_index_by_kind",
        "verification_records_by_id",
        "verification_index_by_claim",
    ):
        snapshot.pop(key, None)

    store = CheckpointStore(tmp_path / "checkpoints")
    store.save_checkpoint(
        run_id="run-legacy-checkpoint",
        label="legacy",
        state_snapshot=snapshot,
        metadata={},
    )
    restored = CTFState.from_snapshot(
        store.latest_checkpoint("run-legacy-checkpoint")["state"]
    )
    summary = preferred_flag_summary(restored)
    board = project_blackboard(restored)

    assert restored.claims_by_id == {}
    assert restored.verification_records_by_id == {}
    assert restored.has_flag("flag{legacy_checkpoint_verified}", level="verified")
    assert summary["verifiedFlags"] == ["flag{legacy_checkpoint_verified}"]
    assert any(
        item["kind"] == "verified_flag"
        and item["value"] == "flag{legacy_checkpoint_verified}"
        for item in board["facts"]
    )


def test_restore_context_hydrates_canonical_claims_from_resume_checkpoint(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    previous_state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    claim = _checkpoint_flag_claim(
        previous_state,
        "flag{resume_canonical_verified}",
        verified=True,
    )

    store = CheckpointStore(tmp_path / "checkpoints")
    record = store.save_checkpoint(
        run_id="run-prev-canonical",
        label="task_finished",
        state_snapshot=previous_state.to_snapshot(),
        metadata={},
    )
    dispatcher = CTFTaskDispatcher(
        runtime=_CheckpointRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(target="http://ctf.local", goal="继续拿到flag")
    dispatcher._challenge_context = {
        "resumeContext": {
            "runId": "run-prev-canonical",
            "checkpointId": record["checkpoint_id"],
            "summary": "resume canonical checkpoint",
        }
    }
    dispatcher._setup_checkpoint_store(
        run_id="run-current-canonical",
        checkpoint_root=tmp_path / "checkpoints",
    )

    dispatcher._restore_context()

    assert dispatcher.state is not None
    restored_claim = dispatcher.state.get_claim(claim.id)
    summary = preferred_flag_summary(dispatcher.state)
    assert restored_claim is not None
    assert restored_claim.level == ClaimLevel.VERIFIED
    assert dispatcher.state.strongest_claim(ClaimKind.FLAG_FOUND).id == claim.id
    assert summary["verifiedFlags"] == ["flag{resume_canonical_verified}"]


@pytest.mark.asyncio
async def test_dispatcher_wrong_flag_feedback_writes_rejected_flags_into_final_checkpoint_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.ToolGuard.require",
        lambda self, tools: {},
    )
    set_notes_file(tmp_path / "notes_checkpoint_wrong_flag.json")
    notes_module._notes.clear()

    memory_store = StrategyMemoryStore(tmp_path / "strategy_memory_checkpoint_wrong_flag.json")
    await memory_store.save(
        StrategyMemoryEntry(
            id="mem_seed_checkpoint_wrong_flag",
            fingerprint=ChallengeFingerprint(tech_stack=["web"]),
            winning_hypothesis_kinds=["auth_form_sqli"],
            failed_hypothesis_kinds=["generic_web_recon"],
            solved=True,
            metadata=StrategyMemoryEntryMetadata(
                created_at=1e12,
                manual_status="active",
                applied_count=3,
                successful_applications=1,
                success_correlation=1.0,
            ),
        )
    )
    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.ctf_dispatcher.StrategyMemoryStore",
        lambda: memory_store,
    )

    dispatcher = CTFTaskDispatcher(runtime=_CheckpointRuntime(), progress_callback=None)
    dispatcher.state = CTFState(target="http://ctf.local", goal="拿到flag")
    dispatcher._setup_session_ledger(
        run_id="run-checkpoint-wrong-flag",
        ledger_root=tmp_path / "ledgers",
    )
    dispatcher._setup_checkpoint_store(
        run_id="run-checkpoint-wrong-flag",
        checkpoint_root=tmp_path / "checkpoints",
    )
    dispatcher._notes_log = []
    dispatcher._pending_wrong_flag_feedback = [
        {"flag": "flag{dispatcher_sqli_ok}", "rationale": "platform rejected"}
    ]
    dispatcher.state.add_flag(
        "flag{dispatcher_sqli_ok}",
        level="rejected",
        evidence_source="submit-endpoint",
        rationale="platform rejected",
        confidence=1.0,
    )

    result = await dispatcher._finalize_solve_result(
        SimpleNamespace(
            success=False,
            flag=None,
            reason="wrong flag feedback: flag{dispatcher_sqli_ok}",
            chain_used=[],
            notes=[],
            missing_tools=[],
        )
    )

    latest = CheckpointStore(tmp_path / "checkpoints").latest_checkpoint(
        "run-checkpoint-wrong-flag"
    )

    assert result.success is False
    assert latest is not None
    assert latest["label"] == "task_finished"
    assert latest["metadata"]["reason"].startswith("wrong flag feedback:")
    assert latest["metadata"]["rejected_flags"] == ["flag{dispatcher_sqli_ok}"]


def test_restored_checkpoint_state_can_change_followup_strategy_choice(tmp_path) -> None:
    previous_state = CTFState(
        target="http://ctf.local",
        goal="拿到flag",
        detected_type="web",
    )
    previous_state.add_observation(
        "ssti_engine_identified",
        "tornado",
        source="resume-checkpoint",
        metadata={"engine": "tornado"},
    )

    store = CheckpointStore(tmp_path / "checkpoints")
    record = store.save_checkpoint(
        run_id="run-prev-2",
        label="task_failed",
        state_snapshot=previous_state.to_snapshot(),
        metadata={"reason": "resume for engine exploit"},
    )

    dispatcher = CTFTaskDispatcher(
        runtime=_CheckpointRuntime(),
        progress_callback=None,
        verification_callback=lambda flag: "yes",
    )
    dispatcher.state = CTFState(target="http://ctf.local", goal="继续拿到flag")
    dispatcher._challenge_context = {
        "resumeContext": {
            "runId": "run-prev-2",
            "checkpointId": record["checkpoint_id"],
            "summary": "resume from engine checkpoint",
        }
    }
    dispatcher._setup_checkpoint_store(
        run_id="run-current-2",
        checkpoint_root=tmp_path / "checkpoints",
    )

    dispatcher._restore_context()

    strategy = dispatcher._select_primary_strategy(
        "web",
        target="http://ctf.local",
        page_features={
            "content": "",
            "html": "",
            "endpoints": ["/error?msg=test"],
            "raw_links": ["http://ctf.local/error?msg=test"],
            "forms": [],
        },
        hint=(
            "[control_decision]\n"
            "decisionKind=direct_execute\n"
            "nextAction=exploit_identified_engine\n"
            "driver=blackboard.identified_engine\n"
            "reason=identified engine present in blackboard"
        ),
    )

    assert strategy is not None
    assert strategy.kind == "ssti_exploit"
