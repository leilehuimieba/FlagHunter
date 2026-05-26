from __future__ import annotations

import asyncio

import pytest

from pentestagent.agents.pa_agent.ctf_state import CTFState, FlagProof, LLMStepLog


def test_ctf_state_exploration_agenda_defaults_to_empty():
    state = CTFState(target="http://ctf.local", goal="拿到flag")

    assert state.schema_version == "1.3"
    assert state.exploration_agenda == []


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
