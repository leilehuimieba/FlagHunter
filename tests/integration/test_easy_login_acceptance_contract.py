from __future__ import annotations

from tests.integration.easy_login_acceptance import (
    EasyLoginEvidence,
    EasyLoginLevel,
    evaluate_easy_login_run,
)


def _sid_note(sid: str) -> dict:
    return {
        "content": f"Captured sid={sid} from receiver output.",
        "category": "credential",
        "confidence": "high",
        "metadata": {
            "username": "sid",
            "password": sid,
            "target": "127.0.0.1:3000",
        },
    }


def test_direction_judgement_success_only_when_routes_are_grounded():
    assessment = evaluate_easy_login_run(
        EasyLoginEvidence(
            observed_routes=("/login", "/visit", "/admin"),
            payload_submitted=False,
        )
    )

    assert assessment.direction_judgement_success is True
    assert assessment.exploit_chain_success is False
    assert assessment.minimum_independent_success is False
    assert assessment.stable_independent_success is False
    assert assessment.highest_level is EasyLoginLevel.DIRECTION


def test_exploit_chain_success_requires_full_closed_loop():
    sid = "abc123sid"
    assessment = evaluate_easy_login_run(
        EasyLoginEvidence(
            observed_routes=("/login", "/visit", "/admin"),
            payload_submitted=True,
            visit_triggered=True,
            extracted_sid=sid,
            sid_note=_sid_note(sid),
            admin_sid_used=sid,
            observed_flag="flag{easy_login_pwned}",
            flag_source="/admin",
            stopped_immediately=True,
            post_flag_tool_calls=0,
            clean_baseline=True,
            manual_intervention=False,
            successful_clean_runs=1,
        )
    )

    assert assessment.direction_judgement_success is True
    assert assessment.exploit_chain_success is True
    assert assessment.minimum_independent_success is True
    assert assessment.stable_independent_success is False
    assert assessment.highest_level is EasyLoginLevel.EXPLOIT


def test_stable_independent_success_requires_three_clean_runs():
    sid = "stable-sid-1"
    assessment = evaluate_easy_login_run(
        EasyLoginEvidence(
            observed_routes=("/login", "/visit", "/admin"),
            payload_submitted=True,
            visit_triggered=True,
            extracted_sid=sid,
            sid_note=_sid_note(sid),
            admin_sid_used=sid,
            observed_flag="flag{easy_login_stable}",
            flag_source="/admin",
            stopped_immediately=True,
            post_flag_tool_calls=0,
            clean_baseline=True,
            manual_intervention=False,
            successful_clean_runs=3,
        )
    )

    assert assessment.direction_judgement_success is True
    assert assessment.exploit_chain_success is True
    assert assessment.minimum_independent_success is True
    assert assessment.stable_independent_success is True
    assert assessment.highest_level is EasyLoginLevel.STABLE

