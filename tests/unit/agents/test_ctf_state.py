from __future__ import annotations

import asyncio
import ast
import inspect
import json

import pytest

from flaghunter.agents.pa_agent.claim_views import preferred_flag_summary
from flaghunter.agents.pa_agent.ctf_state import (
    CTFState,
    ClaimKind,
    ClaimLevel,
    ClaimStatus,
    FlagProof,
    LLMStepLog,
    VerificationDecision,
    VerificationMethod,
)
from flaghunter.agents.pa_agent.task_dag_plan import (
    TaskDAGNode,
    TaskDAGPlan,
    TaskDAGStatus,
    build_task_dag_plan_readback,
)
import flaghunter.agents.pa_agent.ctf_state as ctf_state_module


def _enable_claims_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")


def _single_return_call_name(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    statements = [
        statement for statement in node.body if not isinstance(statement, ast.Expr)
    ]
    assert len(statements) == 1
    statement = statements[0]
    assert isinstance(statement, ast.Return)
    assert isinstance(statement.value, ast.Call)
    if isinstance(statement.value.func, ast.Name):
        return statement.value.func.id
    if isinstance(statement.value.func, ast.Attribute):
        return statement.value.func.attr
    return ""


def test_ctf_state_exploration_agenda_defaults_to_empty():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    assert state.schema_version == "1.7"
    assert state.exploration_agenda == []
    assert state.entry_kind == "url"  # CTF default


def test_ctf_state_add_exploration_item_deduplicates_by_url_or_path():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    first = state.add_exploration_item(
        "/hints.txt",
        discovery_source="response_body",
        hint_strength=2,
        added_at=10.0,
    )
    second = state.add_exploration_item(
        "/hints.txt",
        discovery_source="link_href",
        hint_strength=1,
        added_at=20.0,
    )

    assert first is second
    assert len(state.exploration_agenda) == 1
    assert state.exploration_agenda[0].url_or_path == "/hints.txt"
    assert state.exploration_agenda[0].hint_strength == 1
    assert state.exploration_agenda[0].added_at == 10.0


def test_ctf_state_enter_phase_defaults_and_transitions():
    from flaghunter.agents.pa_agent.ctf_state import Phase

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    assert state.current_phase == Phase.INIT
    assert state.phase_history == []

    state.enter_phase(Phase.SETUP)
    state.enter_phase(Phase.RECON)
    # same-phase re-entry is idempotent (no duplicate history entry)
    state.enter_phase(Phase.RECON)
    state.enter_phase(Phase.EXPLOIT)

    assert state.current_phase == Phase.EXPLOIT
    assert state.phase_history == [Phase.SETUP, Phase.RECON, Phase.EXPLOIT]


def test_ctf_state_enter_phase_blank_falls_back_to_init():
    from flaghunter.agents.pa_agent.ctf_state import Phase

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.enter_phase(Phase.RECON)
    assert state.enter_phase("   ") == Phase.INIT
    assert state.current_phase == Phase.INIT


def test_ctf_state_phase_survives_snapshot_round_trip():
    from flaghunter.agents.pa_agent.ctf_state import Phase

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.enter_phase(Phase.SETUP)
    state.enter_phase(Phase.RECON)

    restored = CTFState.from_snapshot(state.to_snapshot())
    assert restored.current_phase == Phase.RECON
    assert restored.phase_history == [Phase.SETUP, Phase.RECON]


def test_ctf_state_from_old_snapshot_without_phase_keys_uses_defaults():
    from flaghunter.agents.pa_agent.ctf_state import Phase

    # A pre-1.4 snapshot has no current_phase / phase_history keys.
    restored = CTFState.from_snapshot(
        {"target": "http://ctf.local", "goal": "g", "schema_version": "1.3"}
    )
    assert restored.current_phase == Phase.INIT
    assert restored.phase_history == []
    assert restored.phase_round_counts == {}


def test_ctf_state_record_phase_round_tallies_per_phase():
    from flaghunter.agents.pa_agent.ctf_state import Phase

    state = CTFState(target="http://ctf.local", goal="g")
    assert state.rounds_in_phase(Phase.EXPLOIT) == 0

    # explicit phase argument
    assert state.record_phase_round(Phase.EXPLOIT) == 1
    assert state.record_phase_round(Phase.EXPLOIT) == 2
    assert state.rounds_in_phase(Phase.EXPLOIT) == 2

    # a different phase tallies independently
    assert state.record_phase_round(Phase.RECON) == 1
    assert state.rounds_in_phase(Phase.RECON) == 1
    assert state.rounds_in_phase(Phase.EXPLOIT) == 2


def test_ctf_state_record_phase_round_defaults_to_current_phase():
    from flaghunter.agents.pa_agent.ctf_state import Phase

    state = CTFState(target="http://ctf.local", goal="g")
    state.enter_phase(Phase.EXPLOIT)
    assert state.record_phase_round() == 1
    assert state.rounds_in_phase(Phase.EXPLOIT) == 1


def test_ctf_state_phase_round_counts_survive_snapshot_round_trip():
    from flaghunter.agents.pa_agent.ctf_state import Phase

    state = CTFState(target="http://ctf.local", goal="g")
    state.enter_phase(Phase.EXPLOIT)
    state.record_phase_round()
    state.record_phase_round()

    restored = CTFState.from_snapshot(state.to_snapshot())
    assert restored.rounds_in_phase(Phase.EXPLOIT) == 2


def test_ctf_state_effective_phase_budget_falls_back_to_module_default():
    from flaghunter.agents.pa_agent.ctf_state import Phase
    from flaghunter.knowledge.kill_chain import phase_round_budget

    state = CTFState(target="http://ctf.local", goal="g")
    # No profile override → kill_chain module default (P4); CTF is byte-identical.
    assert state.effective_phase_budget(Phase.EXPLOIT) == phase_round_budget(Phase.EXPLOIT)
    # Unbudgeted phase stays None.
    assert state.effective_phase_budget(Phase.RECON) is None


def test_ctf_state_effective_phase_budget_honours_profile_override():
    from flaghunter.agents.pa_agent.ctf_state import Phase

    state = CTFState(target="http://ctf.local", goal="g")
    state.phase_round_budget_overrides = {Phase.EXPLOIT: 12}  # code_audit-style override
    assert state.effective_phase_budget(Phase.EXPLOIT) == 12


def test_ctf_state_budget_overrides_survive_snapshot_round_trip():
    from flaghunter.agents.pa_agent.ctf_state import Phase

    state = CTFState(target="http://ctf.local", goal="g")
    state.phase_round_budget_overrides = {Phase.EXPLOIT: 12}

    restored = CTFState.from_snapshot(state.to_snapshot())
    assert restored.effective_phase_budget(Phase.EXPLOIT) == 12


def test_ctf_state_snapshot_methods_delegate_to_snapshot_seam() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    state.add_observation(
        "derived_target",
        "http://127.0.0.1:3000",
        source="unit",
        metadata={"safe": "visible"},
    )

    exported = ctf_state_module._export_state_snapshot(state)
    restored = ctf_state_module._restore_state_snapshot(exported)

    assert state.to_snapshot() == exported
    assert CTFState.from_snapshot(exported).to_snapshot() == restored.to_snapshot()
    assert restored.observations[0].kind == "derived_target"

    source = inspect.getsource(ctf_state_module.CTFState)
    tree = ast.parse(source)
    methods = {
        node.name: node
        for node in tree.body[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert _single_return_call_name(methods["to_snapshot"]) == "_export_state_snapshot"
    assert _single_return_call_name(methods["from_snapshot"]) == "_restore_state_snapshot"


def test_ctf_state_apply_profile_projects_entry_kind_and_budgets():
    from flaghunter.agents.pa_agent.ctf_state import Phase
    from flaghunter.knowledge.profile import CODE_AUDIT, CTF

    state = CTFState(target="http://ctf.local", goal="g")
    state.apply_profile(CODE_AUDIT)
    assert state.entry_kind == "source"
    assert state.effective_phase_budget(Phase.EXPLOIT) == 12

    # Re-applying the CTF profile resets to url + the module default budget.
    state.apply_profile(CTF)
    assert state.entry_kind == "url"
    assert state.phase_round_budget_overrides == {}


def test_ctf_state_apply_profile_none_is_a_noop():
    state = CTFState(target="http://ctf.local", goal="g")
    state.apply_profile(None)
    assert state.entry_kind == "url"
    assert state.phase_round_budget_overrides == {}


def test_ctf_state_gets_unexplored_priority_items_only():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.add_exploration_item(
        "/file?filename=/etc/passwd&filehash=deadbeef",
        discovery_source="response_body",
        hint_strength=1,
        added_at=30.0,
    )
    state.add_exploration_item(
        "/welcome.txt",
        discovery_source="link_href",
        hint_strength=2,
        added_at=20.0,
    )
    state.add_exploration_item(
        "/robots.txt",
        discovery_source="recon_header",
        hint_strength=3,
        added_at=10.0,
    )
    state.add_exploration_item(
        "/flag.txt",
        discovery_source="response_body",
        hint_strength=1,
        explored=True,
        added_at=40.0,
    )

    items = state.get_unexplored_priority_items(max_hint_strength=2)

    assert [item.url_or_path for item in items] == [
        "/file?filename=/etc/passwd&filehash=deadbeef",
        "/welcome.txt",
    ]


def test_ctf_state_tracks_flag_levels_independently():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    state.add_flag(
        "Syc{candidate_only}",
        level="candidate",
        evidence_source="source-leak",
        rationale="found in backup archive",
        requires_followup=True,
    )
    state.add_flag(
        "flag{runtime_ok}",
        level="runtime",
        evidence_source="http-response",
        rationale="echoed by target",
    )
    state.add_flag(
        "flag{bad_one}",
        level="rejected",
        evidence_source="user-feedback",
        rationale="user marked as wrong",
        confidence=1.0,
    )

    assert [record.value for record in state.candidate_flags] == ["Syc{candidate_only}"]
    assert [record.value for record in state.runtime_flags] == ["flag{runtime_ok}"]
    assert state.is_rejected_flag("flag{bad_one}") is True
    assert state.is_rejected_flag("flag{runtime_ok}") is False


def test_ctf_state_deduplicates_artifacts_and_merges_metadata():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    state.add_artifact(
        "ctf_backup_candidate",
        location="http://ctf.local/www.zip",
        source="notes",
        metadata={"category": "artifact"},
    )
    state.add_artifact(
        "ctf_backup_candidate",
        location="http://ctf.local/www.zip",
        source="notes",
        metadata={"content": "found backup/source candidate"},
    )

    assert len(state.artifacts) == 1
    assert state.artifacts[0].metadata["category"] == "artifact"
    assert state.artifacts[0].metadata["content"] == "found backup/source candidate"


def test_ctf_state_progress_counters_reset_on_progress():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    assert state.mark_no_progress("xss") == 1
    assert state.mark_no_progress("xss") == 2

    state.mark_progress("backup")

    assert state.no_progress_count == 0
    assert state.last_progress_marker == "backup"


def test_ctf_state_flag_level_is_monotonic():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    state.add_flag(
        "flag{same_one}",
        level="candidate",
        evidence_source="source-leak",
    )
    state.add_flag(
        "flag{same_one}",
        level="runtime",
        evidence_source="http-response",
    )
    state.add_flag(
        "flag{same_one}",
        level="candidate",
        evidence_source="source-leak",
    )

    assert state.candidate_flags == []
    assert [record.value for record in state.runtime_flags] == ["flag{same_one}"]


def test_ctf_state_preserves_flag_proof_on_level_upgrade():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    candidate_proof = FlagProof(
        proof_type="source_code_leak",
        evidence_source="source-leak",
        evidence_url="http://ctf.local/www.zip",
        evidence_snippet="flag{same_one}",
        replayable=True,
        submit_confidence=0.0,
        source_trust="source_only",
        strategy_kind="backup_source_leak",
        timestamp="2026-05-24T00:00:00+00:00",
    )
    runtime_proof = FlagProof(
        proof_type="runtime_http",
        evidence_source="http-response",
        evidence_url="http://ctf.local/check.php",
        evidence_snippet="Login Success! flag{same_one}",
        replayable=True,
        submit_confidence=0.85,
        source_trust="runtime",
        strategy_kind="auth_form_sqli",
        hypothesis_id="auth_form_sqli",
        timestamp="2026-05-24T00:00:01+00:00",
    )

    state.add_flag(
        "flag{same_one}",
        level="candidate",
        evidence_source="source-leak",
        proof=candidate_proof,
    )
    state.add_flag(
        "flag{same_one}",
        level="runtime",
        evidence_source="http-response",
        proof=runtime_proof,
    )

    assert state.candidate_flags == []
    assert len(state.runtime_flags) == 1
    assert state.runtime_flags[0].proof is runtime_proof


def test_ctf_state_llm_exploration_budget_guard():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    assert state.is_llm_exploration_allowed(max_steps=2) is True

    state.llm_exploration_steps = 2

    assert state.is_llm_exploration_allowed(max_steps=2) is False


def test_ctf_state_llm_exploration_ceiling_relaxed_and_env_overridable(monkeypatch):
    # §3.2: the DEFAULT budget (no explicit max_steps) is a relaxed ceiling — well
    # above the old hardcoded 8 that starved out-of-repertoire exploration — and is
    # an env-overridable boundary, not a behavioural cage.
    from flaghunter.agents.pa_agent.ctf_state import _llm_exploration_ceiling

    state = CTFState(target="http://ctf.local", goal="拿到flag")
    assert _llm_exploration_ceiling() >= 24
    state.llm_exploration_steps = 8
    assert state.is_llm_exploration_allowed() is True  # 8 no longer exhausts it

    monkeypatch.setenv("FLAGHUNTER_LLM_EXPLORATION_CEILING", "40")
    assert _llm_exploration_ceiling() == 40
    state.llm_exploration_steps = 39
    assert state.is_llm_exploration_allowed() is True
    state.llm_exploration_steps = 40
    assert state.is_llm_exploration_allowed() is False


def test_ctf_state_records_llm_step_and_weak_decision():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    state.record_llm_step(
        LLMStepLog(
            step=1,
            action_type="http_request",
            rationale="probe admin panel",
            payload_summary='{"url":"http://ctf.local/admin"}',
            response_summary="status=200; body=admin panel",
            verifier_decision="none",
            expected_signal_met=True,
            timestamp=1.0,
        )
    )
    state.record_weak_decision("missing fallback for shell action")

    assert state.llm_exploration_steps == 1
    assert len(state.llm_exploration_log) == 1
    assert state.llm_exploration_log[0].action_type == "http_request"
    assert state.weak_decision_log == ["missing fallback for shell action"]


def test_ctf_state_can_create_canonical_claim(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content=" flag{maybe} ",
        producer_type="solver",
        producer_id="unit-test",
        primary_trace_id="trace-1",
        confidence=0.4,
    )

    assert claim.kind == ClaimKind.FLAG_FOUND
    assert claim.content == "flag{maybe}"
    assert claim.normalized_content == "flag{maybe}"
    assert claim.level == ClaimLevel.CONJECTURE
    assert claim.status == ClaimStatus.ACTIVE
    assert state.get_claim(claim.id) is claim
    assert state.find_claims_by_kind(ClaimKind.FLAG_FOUND) == [claim]
    assert state.active_claims() == [claim]


def test_ctf_state_create_claim_delegates_to_claim_store_seam(monkeypatch) -> None:
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="get flag")

    claim = ctf_state_module._create_claim(
        state,
        kind=ClaimKind.FLAG_FOUND,
        content=" flag{seam} ",
        producer_type="solver",
        producer_id="unit-test",
        primary_trace_id="trace-claim-seam",
        confidence=0.42,
    )

    assert claim.content == "flag{seam}"
    assert state.claims_by_id[claim.id] is claim
    assert state.claim_index_by_kind[ClaimKind.FLAG_FOUND.value] == [claim.id]

    source = inspect.getsource(ctf_state_module.CTFState)
    tree = ast.parse(source)
    methods = {
        node.name: node
        for node in tree.body[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert _single_return_call_name(methods["create_claim"]) == "_create_claim"


def test_ctf_state_can_append_verification_record(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content="flag{runtime}",
        producer_type="solver",
        producer_id="unit-test",
        primary_trace_id="trace-claim",
    )

    record = state.append_verification_record(
        claim.id,
        verifier_type="ctf_verifier",
        verifier_id="unit-verifier",
        method="runtime_http",
        decision="runtime_supported",
        passed=True,
        sufficient_for_upgrade=False,
        trace_id="trace-verification",
        rationale="observed in HTTP response",
    )

    assert record.claim_id == claim.id
    assert record.passed is True
    assert record.sufficient_for_upgrade is False
    assert state.verification_records_by_id[record.id] is record
    assert state.verification_index_by_claim[claim.id] == [record.id]
    assert claim.verification_record_ids == [record.id]
    assert claim.level == ClaimLevel.CONJECTURE


def test_ctf_state_can_upgrade_claim_to_verified(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content="flag{verified}",
        producer_type="solver",
        producer_id="unit-test",
        primary_trace_id="trace-claim",
    )
    record = state.append_verification_record(
        claim.id,
        verifier_type="ctf_verifier",
        verifier_id="unit-verifier",
        method="platform_submit",
        decision="verified",
        passed=True,
        sufficient_for_upgrade=True,
        trace_id="trace-platform",
        rationale="platform accepted it",
    )

    upgraded = state.upgrade_claim_to_verified(
        claim.id,
        verification_record_id=record.id,
        verifier_id="unit-verifier",
    )

    assert upgraded is claim
    assert claim.level == ClaimLevel.VERIFIED
    assert claim.status == ClaimStatus.ACTIVE
    assert state.strongest_claim(ClaimKind.FLAG_FOUND) is claim


def test_ctf_state_can_retract_claim_without_deleting_it(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content="flag{wrong}",
        producer_type="solver",
        producer_id="unit-test",
        primary_trace_id="trace-claim",
    )

    retracted = state.retract_claim(
        claim.id,
        reason="platform rejected it",
        trace_id="trace-reject",
        actor_id="unit-verifier",
    )

    assert retracted is claim
    assert claim.level == ClaimLevel.RETRACTED
    assert claim.status == ClaimStatus.RETRACTED
    assert claim.retracted_at is not None
    assert claim.metadata["retraction_reason"] == "platform rejected it"
    assert state.get_claim(claim.id) is claim
    assert state.active_claims() == []


def test_ctf_state_canonical_claims_survive_snapshot_round_trip(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content="flag{persisted}",
        producer_type="solver",
        producer_id="unit-test",
        primary_trace_id="trace-claim",
    )
    record = state.append_verification_record(
        claim.id,
        verifier_type="ctf_verifier",
        verifier_id="unit-verifier",
        method="platform_submit",
        decision="verified",
        passed=True,
        sufficient_for_upgrade=True,
        trace_id="trace-platform",
        rationale="platform accepted it",
    )
    state.upgrade_claim_to_verified(claim.id, verification_record_id=record.id)

    snapshot = state.to_snapshot()
    json.dumps(snapshot)
    restored = CTFState.from_snapshot(snapshot)
    restored_claim = restored.get_claim(claim.id)
    restored_record = restored.verification_records_by_id[record.id]

    assert restored_claim is not None
    assert restored_claim.level == ClaimLevel.VERIFIED
    assert restored_claim.verification_record_ids == [record.id]
    assert restored_record.claim_id == claim.id
    assert restored_record.passed is True
    assert restored_record.sufficient_for_upgrade is True
    assert restored_record.decision == VerificationDecision.VERIFIED
    assert restored.find_claims_by_kind(ClaimKind.FLAG_FOUND) == [restored_claim]
    assert restored.verification_index_by_claim[claim.id] == [record.id]


def test_ctf_state_from_snapshot_enforces_retracted_claim_invariant(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content="flag{wrong_after_resume}",
        producer_type="verifier",
        producer_id="ctf_verifier",
        primary_trace_id="trace-claim",
    )
    record = state.append_verification_record(
        claim.id,
        verifier_type="verifier",
        verifier_id="ctf_verifier",
        method=VerificationMethod.PLATFORM_SUBMIT,
        decision=VerificationDecision.REJECTED,
        passed=False,
        sufficient_for_upgrade=False,
        trace_id="trace-reject",
    )
    state.retract_claim(
        claim.id,
        reason="platform rejected it",
        trace_id=record.trace_id,
        actor_id="ctf_verifier",
    )
    snapshot = state.to_snapshot()
    snapshot["claims_by_id"][claim.id]["status"] = "active"
    snapshot["claims_by_id"][claim.id]["retracted_at"] = None

    restored = CTFState.from_snapshot(snapshot)
    restored_claim = restored.get_claim(claim.id)

    assert restored_claim is not None
    assert restored_claim.level == ClaimLevel.RETRACTED
    assert restored_claim.status == ClaimStatus.RETRACTED
    assert restored_claim.retracted_at is not None
    assert restored.find_claims_by_kind(ClaimKind.FLAG_FOUND) == []
    assert restored.verification_index_by_claim[claim.id] == [record.id]


def test_ctf_state_from_snapshot_demotes_verified_claim_missing_record(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content="flag{forged_verified_missing_record}",
        producer_type="solver",
        producer_id="unit-test",
        primary_trace_id="trace-claim",
        confidence=0.9,
    )

    snapshot = state.to_snapshot()
    snapshot["claims_by_id"][claim.id]["level"] = "verified"
    snapshot["claims_by_id"][claim.id]["confidence"] = 1.0
    snapshot["claims_by_id"][claim.id]["verification_record_ids"] = ["missing-record"]
    snapshot["verification_records_by_id"] = {}

    restored = CTFState.from_snapshot(snapshot)
    restored_claim = restored.get_claim(claim.id)
    strongest = restored.strongest_claim(ClaimKind.FLAG_FOUND)
    summary = preferred_flag_summary(restored)

    assert restored_claim is not None
    assert restored_claim.level == ClaimLevel.CONJECTURE
    assert restored_claim.status == ClaimStatus.ACTIVE
    assert restored_claim.confidence <= 0.5
    assert restored_claim.verification_record_ids == []
    assert (
        restored_claim.metadata["restore_integrity_warning"]
        == "verified_claim_missing_sufficient_record"
    )
    assert summary["verifiedFlags"] == []
    assert "flag{forged_verified_missing_record}" not in summary["verifiedFlags"]
    assert strongest is restored_claim
    assert strongest.level != ClaimLevel.VERIFIED


@pytest.mark.parametrize(
    ("decision", "passed", "sufficient_for_upgrade"),
    [
        (VerificationDecision.VERIFIED, False, True),
        (VerificationDecision.VERIFIED, True, False),
        (VerificationDecision.RUNTIME_SUPPORTED, True, True),
    ],
)
def test_ctf_state_from_snapshot_demotes_verified_claim_with_insufficient_record(
    monkeypatch,
    decision,
    passed,
    sufficient_for_upgrade,
):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content="flag{forged_verified_insufficient_record}",
        producer_type="solver",
        producer_id="unit-test",
        primary_trace_id="trace-claim",
        confidence=0.9,
    )
    record = state.append_verification_record(
        claim.id,
        verifier_type="ctf_verifier",
        verifier_id="unit-verifier",
        method=VerificationMethod.PLATFORM_SUBMIT,
        decision=VerificationDecision.VERIFIED,
        passed=True,
        sufficient_for_upgrade=True,
        trace_id="trace-platform",
        rationale="platform accepted it",
    )
    state.upgrade_claim_to_verified(claim.id, verification_record_id=record.id)

    snapshot = state.to_snapshot()
    snapshot["verification_records_by_id"][record.id]["decision"] = decision.value
    snapshot["verification_records_by_id"][record.id]["passed"] = passed
    snapshot["verification_records_by_id"][record.id][
        "sufficient_for_upgrade"
    ] = sufficient_for_upgrade

    restored = CTFState.from_snapshot(snapshot)
    restored_claim = restored.get_claim(claim.id)
    summary = preferred_flag_summary(restored)

    assert restored_claim is not None
    assert restored_claim.level == ClaimLevel.CONJECTURE
    assert restored_claim.status == ClaimStatus.ACTIVE
    assert restored_claim.confidence <= 0.5
    assert (
        restored_claim.metadata["restore_integrity_warning"]
        == "verified_claim_missing_sufficient_record"
    )
    assert summary["verifiedFlags"] == []
    assert restored.strongest_claim(ClaimKind.FLAG_FOUND).level != ClaimLevel.VERIFIED


def test_ctf_claims_feature_flag_off_preserves_legacy_flag_behavior(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "0")
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    state.add_flag(
        "flag{legacy}",
        level="candidate",
        evidence_source="source-leak",
        rationale="legacy bucket path",
    )

    assert state.ctf_claims_v1_enabled is False
    assert [record.value for record in state.candidate_flags] == ["flag{legacy}"]
    assert state.runtime_flags == []
    assert state.verified_flags == []
    assert state.rejected_flags == []
    assert state.claims_by_id == {}


def test_ctf_claims_feature_flag_off_rejects_canonical_writes(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "0")
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    with pytest.raises(RuntimeError, match="FLAGHUNTER_CTF_CLAIMS_V1"):
        state.create_claim(
            kind=ClaimKind.FLAG_FOUND,
            content="flag{blocked}",
            producer_type="solver",
            producer_id="unit-test",
            primary_trace_id="trace-claim",
        )

    assert state.claims_by_id == {}


def test_ctf_state_task_dag_plan_snapshot_round_trip_and_redaction() -> None:
    state = CTFState(target="http://ctf.local", goal="get flag")
    plan = TaskDAGPlan(
        id="plan-state",
        metadata={"source": "unit", "token": "plan-token"},
    )
    plan.add_node(
        TaskDAGNode(
            id="task-a",
            title="PING 127.0.0.1\n64 bytes from 127.0.0.1",
            goal="collect facts password=goal-password",
            status=TaskDAGStatus.SUCCEEDED,
            metadata={"safe": "kept", "secret": "node-secret"},
        )
    )
    plan.add_node(
        TaskDAGNode(
            id="task-b",
            status=TaskDAGStatus.INSUFFICIENT,
            depends_on=["task-a"],
            task_brief_id="brief-b",
            solve_node_id="node-b",
            receipt_ids=["receipt-b"],
            claim_ids=["claim-b"],
            trace_ids=["trace-b"],
            verification_record_ids=["verification-b"],
        )
    )

    state.set_task_dag_plan(plan)
    snapshot = state.to_snapshot()
    restored = CTFState.from_snapshot(snapshot)
    restored_plan = restored.get_task_dag_plan()
    snapshot_text = repr(snapshot)

    assert snapshot["task_dag_plan"]["schemaVersion"] == "p4.task_dag_plan.v1"
    assert restored_plan.id == "plan-state"
    assert sorted(restored_plan.nodes_by_id) == ["task-a", "task-b"]
    assert restored_plan.get_node("task-a").status is TaskDAGStatus.SUCCEEDED
    assert restored_plan.get_node("task-b").status is TaskDAGStatus.INSUFFICIENT
    assert restored_plan.get_node("task-b").depends_on == ["task-a"]
    assert [(edge.source_id, edge.target_id) for edge in restored_plan.edges] == [
        ("task-a", "task-b")
    ]
    assert restored_plan.get_node("task-b").task_brief_id == "brief-b"
    assert restored_plan.get_node("task-b").solve_node_id == "node-b"
    assert restored_plan.get_node("task-b").receipt_ids == ["receipt-b"]
    assert restored_plan.get_node("task-b").claim_ids == ["claim-b"]
    assert restored_plan.get_node("task-b").trace_ids == ["trace-b"]
    assert restored_plan.get_node("task-b").verification_record_ids == [
        "verification-b"
    ]
    assert restored_plan.metadata["source"] == "unit"
    assert restored_plan.get_node("task-a").metadata["safe"] == "kept"
    assert "<redacted raw body>" in snapshot_text
    assert "<redacted>" in snapshot_text
    for leaked in (
        "PING 127.0.0.1",
        "64 bytes from",
        "goal-password",
        "plan-token",
        "node-secret",
    ):
        assert leaked not in snapshot_text


def test_ctf_state_task_dag_plan_legacy_and_malformed_restore_are_stable() -> None:
    legacy = CTFState.from_snapshot({"target": "http://ctf.local", "goal": "get flag"})
    malformed = CTFState.from_snapshot(
        {
            "target": "http://ctf.local",
            "goal": "get flag",
            "task_dag_plan": "not-a-dict token=legacy-token",
        }
    )

    assert legacy.get_task_dag_plan().to_dict()["summary"]["nodeCount"] == 0
    malformed_readback = build_task_dag_plan_readback(malformed.get_task_dag_plan())
    malformed_text = repr(malformed_readback)

    assert malformed_readback["summary"]["nodeCount"] == 0
    assert malformed_readback["summary"]["restoreWarningCount"] == 1
    assert "legacy-token" not in malformed_text


def test_ctf_state_rejects_untraceable_claims(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    for field_name, kwargs in [
        ("kind", {"kind": "   "}),
        ("content", {"content": "   "}),
        ("primary_trace_id", {"primary_trace_id": "   "}),
        ("producer_type", {"producer_type": "   "}),
        ("producer_id", {"producer_id": "   "}),
    ]:
        payload = {
            "kind": ClaimKind.FLAG_FOUND,
            "content": "flag{traceable}",
            "producer_type": "solver",
            "producer_id": "unit-test",
            "primary_trace_id": "trace-claim",
        }
        payload.update(kwargs)
        with pytest.raises(ValueError, match=field_name):
            state.create_claim(**payload)


def test_ctf_state_rejects_untraceable_verification_records(monkeypatch):
    _enable_claims_v1(monkeypatch)
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content="flag{traceable}",
        producer_type="solver",
        producer_id="unit-test",
        primary_trace_id="trace-claim",
    )

    for field_name, kwargs in [
        ("method", {"method": "   "}),
        ("decision", {"decision": "   "}),
        ("trace_id", {"trace_id": "   "}),
        ("verifier_type", {"verifier_type": "   "}),
        ("verifier_id", {"verifier_id": "   "}),
    ]:
        payload = {
            "claim_id": claim.id,
            "verifier_type": "ctf_verifier",
            "verifier_id": "unit-verifier",
            "method": "runtime_http",
            "decision": "runtime_supported",
            "trace_id": "trace-verification",
        }
        payload.update(kwargs)
        with pytest.raises(ValueError, match=field_name):
            state.append_verification_record(**payload)


@pytest.mark.asyncio
async def test_ctf_state_write_lock_serializes_100_concurrent_writes():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    async def _writer(idx: int) -> None:
        async with state.write_lock():
            state.add_observation(
                "concurrent_write",
                f"value-{idx}",
                source="test",
                metadata={"idx": idx},
            )

    await asyncio.gather(*[_writer(idx) for idx in range(100)])

    assert len(state.observations) == 100
    assert {item.value for item in state.observations} == {
        f"value-{idx}" for idx in range(100)
    }
