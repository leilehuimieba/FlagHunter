from __future__ import annotations

from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.ctf_state import (
    CTFState,
    ClaimKind,
    ClaimLevel,
    ClaimStatus,
    VerificationDecision,
)
from flaghunter.agents.pa_agent.verifier import CTFVerifier


def _flag_claims(state: CTFState, *, include_inactive: bool = False):
    return state.find_claims_by_kind(
        ClaimKind.FLAG_FOUND,
        include_inactive=include_inactive,
    )


@pytest.mark.asyncio
async def test_verifier_marks_source_only_flag_as_candidate():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    verifier = CTFVerifier(runtime=None)

    result = await verifier.verify_flag(
        state,
        flag="Syc{backup_source_only}",
        evidence_source="source-leak",
        rationale="found in backup archive",
    )

    assert result.decision == "candidate"
    assert result.requires_followup is True
    assert [record.value for record in state.candidate_flags] == ["Syc{backup_source_only}"]
    assert state.runtime_flags == []
    assert state.verified_flags == []
    assert result.proof is not None
    assert result.proof.source_trust == "source_only"
    assert result.proof.submit_confidence == 0.0


@pytest.mark.asyncio
async def test_verifier_claims_v1_source_candidate_double_writes_claim(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    verifier = CTFVerifier(runtime=None)

    result = await verifier.verify_flag(
        state,
        flag="flag{claims_candidate}",
        evidence_source="source-leak",
        rationale="found in source archive",
    )

    assert result.decision == "candidate"
    assert [record.value for record in state.candidate_flags] == ["flag{claims_candidate}"]
    claims = _flag_claims(state)
    assert len(claims) == 1
    assert claims[0].content == "flag{claims_candidate}"
    assert claims[0].kind == ClaimKind.FLAG_FOUND
    assert claims[0].level == ClaimLevel.CONJECTURE
    assert claims[0].status == ClaimStatus.ACTIVE


@pytest.mark.asyncio
async def test_verifier_claims_v1_off_keeps_legacy_buckets_without_claims(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "0")
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    verifier = CTFVerifier(runtime=None)

    result = await verifier.verify_flag(
        state,
        flag="flag{legacy_candidate_only}",
        evidence_source="source-leak",
        rationale="found in source archive",
    )

    assert result.decision == "candidate"
    assert [record.value for record in state.candidate_flags] == ["flag{legacy_candidate_only}"]
    assert state.claims_by_id == {}
    assert state.verification_records_by_id == {}


@pytest.mark.asyncio
async def test_verifier_claims_v1_runtime_supported_adds_verification_record(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    verifier = CTFVerifier(runtime=None)

    result = await verifier.verify_flag(
        state,
        flag="flag{claims_runtime}",
        evidence_source="http-response",
        rationale="echoed by target",
    )

    assert result.decision == "runtime"
    assert [record.value for record in state.runtime_flags] == ["flag{claims_runtime}"]
    claims = _flag_claims(state)
    assert len(claims) == 1
    claim = claims[0]
    assert claim.level == ClaimLevel.CONJECTURE
    assert len(claim.verification_record_ids) == 1
    record = state.verification_records_by_id[claim.verification_record_ids[0]]
    assert record.claim_id == claim.id
    assert record.decision == VerificationDecision.RUNTIME_SUPPORTED
    assert record.passed is True
    assert record.sufficient_for_upgrade is False


@pytest.mark.asyncio
async def test_verifier_claims_v1_verified_upgrades_claim(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.local_challenge_auto_verify = True
    verifier = CTFVerifier(runtime=None)

    result = await verifier.verify_flag(
        state,
        flag="flag{claims_verified}",
        evidence_source="http-response",
        rationale="runtime flag from local challenge",
    )

    assert result.decision == "verified"
    assert [record.value for record in state.verified_flags] == ["flag{claims_verified}"]
    claims = _flag_claims(state)
    assert len(claims) == 1
    claim = claims[0]
    assert claim.level == ClaimLevel.VERIFIED
    assert claim.status == ClaimStatus.ACTIVE
    record = state.verification_records_by_id[claim.verification_record_ids[-1]]
    assert record.decision == VerificationDecision.VERIFIED
    assert record.passed is True
    assert record.sufficient_for_upgrade is True


@pytest.mark.asyncio
async def test_verifier_claims_v1_rejected_retracts_claim(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    verifier = CTFVerifier(runtime=None)

    result = verifier.reject_flag(
        state,
        flag="flag{claims_wrong}",
        evidence_source="platform-submit",
        rationale="platform rejected flag",
    )

    assert result.decision == "rejected"
    assert [record.value for record in state.rejected_flags] == ["flag{claims_wrong}"]
    claims = _flag_claims(state, include_inactive=True)
    assert len(claims) == 1
    claim = claims[0]
    assert claim.level == ClaimLevel.RETRACTED
    assert claim.status == ClaimStatus.RETRACTED
    record = state.verification_records_by_id[claim.verification_record_ids[-1]]
    assert record.decision == VerificationDecision.REJECTED
    assert record.passed is False
    assert record.sufficient_for_upgrade is False


@pytest.mark.asyncio
async def test_verifier_explicit_rejection_has_highest_priority():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    verifier = CTFVerifier(runtime=None)
    verifier.reject_flag(state, flag="flag{already_wrong}", evidence_source="user-feedback")

    result = await verifier.verify_flag(
        state,
        flag="flag{already_wrong}",
        evidence_source="response_body",
        rationale="prompt injection echoed a previously rejected flag",
    )

    assert result.decision == "rejected"
    assert [record.value for record in state.rejected_flags] == ["flag{already_wrong}"]
    assert state.runtime_flags == []
    assert state.verified_flags == []


@pytest.mark.asyncio
async def test_verifier_marks_runtime_flag_pending_without_confirmation():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    verifier = CTFVerifier(runtime=None)

    result = await verifier.verify_flag(
        state,
        flag="flag{runtime_only}",
        evidence_source="http-response",
        rationale="echoed by target",
    )

    assert result.decision == "runtime"
    assert result.requires_followup is True
    assert [record.value for record in state.runtime_flags] == ["flag{runtime_only}"]
    assert state.verified_flags == []
    assert state.runtime_flags[0].proof is not None
    assert state.runtime_flags[0].proof.proof_type == "runtime_http"
    assert state.runtime_flags[0].proof.submit_confidence == 0.85


@pytest.mark.asyncio
async def test_verifier_auto_verifies_strong_runtime_flag_for_local_challenge_without_submit_channel():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.local_challenge_auto_verify = True
    verifier = CTFVerifier(runtime=None)

    result = await verifier.verify_flag(
        state,
        flag="flag{local_runtime_verified}",
        evidence_source="http-response",
        rationale="admin route returned runtime flag from local sandbox challenge",
    )

    assert result.decision == "verified"
    assert [record.value for record in state.verified_flags] == ["flag{local_runtime_verified}"]
    assert state.runtime_flags == []
    assert result.metadata["verification_path"] == "local_challenge_runtime"
    assert result.metadata["platform_verified"] is False
    assert result.metadata["operator_confirmed"] is False


@pytest.mark.asyncio
async def test_verifier_keeps_weak_runtime_pending_even_for_local_challenge_context():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.local_challenge_auto_verify = True
    verifier = CTFVerifier(runtime=None)

    result = await verifier.verify_flag(
        state,
        flag="flag{local_weak_pending}",
        evidence_source="browser-rendered-page",
        rationale="flag-like text only appeared on the landing page",
    )

    assert result.decision == "runtime"
    assert [record.value for record in state.runtime_flags] == ["flag{local_weak_pending}"]
    assert state.verified_flags == []


@pytest.mark.asyncio
async def test_verifier_treats_response_body_flag_as_runtime_not_verified():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    verifier = CTFVerifier(runtime=None)

    result = await verifier.verify_flag(
        state,
        flag="flag{prompt_injection_echo}",
        evidence_source="response_body",
        rationale="flag string was echoed inside a prompt injection response body",
    )

    assert result.decision == "runtime"
    assert result.requires_followup is True
    assert [record.value for record in state.runtime_flags] == ["flag{prompt_injection_echo}"]
    assert state.verified_flags == []
    assert state.candidate_flags == []


@pytest.mark.asyncio
async def test_verifier_upgrades_runtime_flag_to_verified_via_confirmation():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    verifier = CTFVerifier(runtime=None, confirmation_callback=lambda flag: "yes")

    result = await verifier.verify_flag(
        state,
        flag="flag{runtime_yes}",
        evidence_source="http-response",
        rationale="echoed by target",
    )

    assert result.decision == "verified"
    assert [record.value for record in state.verified_flags] == ["flag{runtime_yes}"]
    assert state.runtime_flags == []
    assert result.metadata["verification_path"] == "operator_confirmation"
    assert result.metadata["platform_verified"] is False
    assert result.metadata["operator_confirmed"] is True
    assert result.proof is not None
    assert result.proof.proof_type == "user_confirm"


@pytest.mark.asyncio
async def test_verifier_operator_confirmation_on_weak_runtime_keeps_non_platform_metadata():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    verifier = CTFVerifier(runtime=None, confirmation_callback=lambda flag: "yes")

    result = await verifier.verify_flag(
        state,
        flag="flag{homepage_echo_only}",
        evidence_source="browser-rendered-page",
        rationale="flag-like text was rendered on the first page only",
    )

    assert result.decision == "verified"
    assert "not platform-verified" in result.rationale
    assert result.metadata["runtime_strength"] == "weak"
    assert any(
        item.get("type") == "flag_verification_decision"
        and item.get("flag") == "flag{homepage_echo_only}"
        and item.get("verification_path") == "operator_confirmation"
        and item.get("platform_verified") is False
        for item in state.meta_reasonings
        if isinstance(item, dict)
    )


@pytest.mark.asyncio
async def test_verifier_rejects_flag_from_wrong_flag_feedback():
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    verifier = CTFVerifier(runtime=None)
    verifier.reject_flag(state, flag="flag{wrong_one}", evidence_source="user-feedback")

    result = await verifier.verify_flag(
        state,
        flag="flag{wrong_one}",
        evidence_source="http-response",
        rationale="saw it again",
    )

    assert result.decision == "rejected"
    assert [record.value for record in state.rejected_flags] == ["flag{wrong_one}"]


@pytest.mark.asyncio
async def test_verifier_upgrades_runtime_flag_via_platform_auto_submit(monkeypatch):
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.submit_auto = True
    state.submit_platform_type = "ctfd"
    state.submit_base_url = "https://ctf.example.com"
    state.submit_challenge_id = "42"
    verifier = CTFVerifier(runtime=None)

    async def _fake_submit_flag(flag: str, platform_type: str = "manual", challenge_id=None, **kwargs):
        assert flag == "flag{platform_ok}"
        assert platform_type == "ctfd"
        assert challenge_id == "42"
        assert kwargs["base_url"] == "https://ctf.example.com"
        return SimpleNamespace(
            success=True,
            correct=True,
            message="correct",
            error="",
            platform="CTFd",
        )

    monkeypatch.setattr(
        "flaghunter.cpa_modules.m2_ctf_kit.flag_submitter.submit_flag",
        _fake_submit_flag,
    )

    result = await verifier.verify_flag(
        state,
        flag="flag{platform_ok}",
        evidence_source="http-response",
        rationale="echoed by target",
    )

    assert result.decision == "verified"
    assert [record.value for record in state.verified_flags] == ["flag{platform_ok}"]
    assert any(
        item.get("type") == "flag_submit_attempt" and item.get("correct") is True
        for item in state.meta_reasonings
        if isinstance(item, dict)
    )


@pytest.mark.asyncio
async def test_verifier_rejects_runtime_flag_via_platform_auto_submit(monkeypatch):
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.submit_auto = True
    state.submit_platform_type = "ctfd"
    state.submit_base_url = "https://ctf.example.com"
    state.submit_challenge_id = "42"
    verifier = CTFVerifier(runtime=None)

    async def _fake_submit_flag(flag: str, platform_type: str = "manual", challenge_id=None, **kwargs):
        return SimpleNamespace(
            success=True,
            correct=False,
            message="wrong answer",
            error="",
            platform="CTFd",
        )

    monkeypatch.setattr(
        "flaghunter.cpa_modules.m2_ctf_kit.flag_submitter.submit_flag",
        _fake_submit_flag,
    )

    result = await verifier.verify_flag(
        state,
        flag="flag{platform_bad}",
        evidence_source="http-response",
        rationale="echoed by target",
    )

    assert result.decision == "rejected"
    assert [record.value for record in state.rejected_flags] == ["flag{platform_bad}"]


@pytest.mark.asyncio
async def test_verifier_operator_confirmation_still_submits_when_submit_channel_exists(monkeypatch):
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.submit_auto = True
    state.submit_platform_type = "ctfd"
    state.submit_base_url = "https://ctf.example.com"
    state.submit_challenge_id = "42"
    verifier = CTFVerifier(runtime=None, confirmation_callback=lambda flag: "yes")

    async def _fake_submit_flag(flag: str, platform_type: str = "manual", challenge_id=None, **kwargs):
        assert flag == "flag{weak_confirmed_but_wrong}"
        assert platform_type == "ctfd"
        assert challenge_id == "42"
        return SimpleNamespace(
            success=True,
            correct=False,
            message="wrong answer",
            error="",
            platform="CTFd",
        )

    monkeypatch.setattr(
        "flaghunter.cpa_modules.m2_ctf_kit.flag_submitter.submit_flag",
        _fake_submit_flag,
    )

    result = await verifier.verify_flag(
        state,
        flag="flag{weak_confirmed_but_wrong}",
        evidence_source="browser-rendered-page",
        rationale="homepage rendered a suspicious flag-like string",
    )

    assert result.decision == "rejected"
    assert [record.value for record in state.rejected_flags] == ["flag{weak_confirmed_but_wrong}"]
    assert any(
        item.get("type") == "flag_submit_attempt"
        and item.get("flag") == "flag{weak_confirmed_but_wrong}"
        and item.get("correct") is False
        for item in state.meta_reasonings
        if isinstance(item, dict)
    )


@pytest.mark.asyncio
async def test_verifier_short_circuits_when_platform_previously_rejected_flag(monkeypatch):
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.meta_reasonings.append(
        {
            "type": "flag_submit_attempt",
            "flag": "flag{reused_bad}",
            "source": "platform-submit",
            "success": True,
            "correct": False,
            "message": "wrong answer",
            "error": "",
        }
    )
    verifier = CTFVerifier(runtime=None)

    async def _unexpected_submit(*args, **kwargs):
        raise AssertionError("submit_flag should not be called again")

    monkeypatch.setattr(
        "flaghunter.cpa_modules.m2_ctf_kit.flag_submitter.submit_flag",
        _unexpected_submit,
    )

    result = await verifier.verify_flag(
        state,
        flag="flag{reused_bad}",
        evidence_source="http-response",
        rationale="echoed again",
    )

    assert result.decision == "rejected"
    assert [record.value for record in state.rejected_flags] == ["flag{reused_bad}"]


@pytest.mark.asyncio
async def test_verifier_submit_gate_blocks_weak_runtime_auto_submit(monkeypatch):
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.submit_auto = True
    state.submit_platform_type = "ctfd"
    state.submit_base_url = "https://ctf.example.com"
    state.submit_challenge_id = "42"
    verifier = CTFVerifier(runtime=None)

    async def _unexpected_submit(*args, **kwargs):
        raise AssertionError("submit_flag should be gated off")

    monkeypatch.setattr(
        "flaghunter.cpa_modules.m2_ctf_kit.flag_submitter.submit_flag",
        _unexpected_submit,
    )

    result = await verifier.verify_flag(
        state,
        flag="flag{weak_runtime}",
        evidence_source="browser-rendered-page",
        rationale="echoed on first page render",
    )

    assert result.decision == "runtime"
    assert any(
        item.get("type") == "submit_gate_decision" and item.get("allow") is False
        for item in state.meta_reasonings
        if isinstance(item, dict)
    )
    assert result.proof is not None
    assert result.proof.submit_confidence < 0.5
