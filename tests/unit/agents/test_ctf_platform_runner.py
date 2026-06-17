from __future__ import annotations

import time
from types import SimpleNamespace

from flaghunter.agents.pa_agent.platform_runner import (
    PlatformAutonomyRunner,
    PlatformRunConfig,
)


def _result(
    *,
    success: bool = False,
    reason: str = "",
    chain_used: list[str] | None = None,
    missing_tools: list[str] | None = None,
):
    return SimpleNamespace(
        success=success,
        reason=reason,
        chain_used=list(chain_used or []),
        missing_tools=list(missing_tools or []),
    )


def test_platform_runner_record_result_classifies_lifecycle_outcomes():
    runner = PlatformAutonomyRunner()
    state = runner.start(PlatformRunConfig())
    started_at = time.time() - 1

    solved = runner.record_result(
        state,
        challenge_id="1",
        challenge_name="Solved",
        url="https://ctf.example.com/1",
        result=_result(success=True, chain_used=["sqli"]),
        stop_reason="flag_verified",
        started_at=started_at,
        ended_at=started_at + 0.5,
    )
    skipped = runner.record_result(
        state,
        challenge_id="2",
        challenge_name="Skipped",
        url="https://ctf.example.com/2",
        result=_result(),
        stop_reason="challenge_already_solved",
        started_at=started_at,
        ended_at=started_at + 0.5,
    )
    blocked = runner.record_result(
        state,
        challenge_id="3",
        challenge_name="Blocked",
        url="https://ctf.example.com/3",
        result=_result(reason="wrong flag feedback: flag{bad}"),
        stop_reason="wrong_flag_feedback",
        started_at=started_at,
        ended_at=started_at + 0.5,
    )
    stopped = runner.record_result(
        state,
        challenge_id="4",
        challenge_name="Stopped",
        url="https://ctf.example.com/4",
        result=_result(reason="未命中 flag，继续回溯"),
        stop_reason="all_hypotheses_exhausted",
        started_at=started_at,
        ended_at=started_at + 0.5,
    )

    assert solved.outcome == "solved"
    assert solved.chain_used == ["sqli"]
    assert skipped.outcome == "skipped"
    assert skipped.skip_reason == "challenge_already_solved"
    assert blocked.outcome == "blocked"
    assert blocked.blocked_reason == "wrong_flag_feedback"
    assert blocked.failure_taxonomy == "wrong_answer"
    assert stopped.outcome == "stopped"
    assert stopped.failure_taxonomy == "give_up"
    assert solved.failure_taxonomy == ""
    assert state.consecutive_stops == 2


def test_platform_runner_failure_taxonomy_maps_connection_round_and_token_reasons():
    runner = PlatformAutonomyRunner()
    state = runner.start(PlatformRunConfig())
    started_at = time.time() - 1

    connection = runner.record_result(
        state,
        challenge_id="5",
        challenge_name="Conn",
        url="https://ctf.example.com/5",
        result=_result(reason="network timeout"),
        stop_reason="connection_failure",
        started_at=started_at,
        ended_at=started_at + 0.5,
    )
    round_exceeded = runner.record_result(
        state,
        challenge_id="6",
        challenge_name="Rounds",
        url="https://ctf.example.com/6",
        result=_result(reason="budget exhausted"),
        stop_reason="round_exceeded",
        started_at=started_at,
        ended_at=started_at + 0.5,
    )
    token = runner.record_result(
        state,
        challenge_id="7",
        challenge_name="Tokens",
        url="https://ctf.example.com/7",
        result=_result(reason="context window exceeded"),
        stop_reason="token_exceeded",
        started_at=started_at,
        ended_at=started_at + 0.5,
    )

    assert connection.failure_taxonomy == "connection_failure"
    assert round_exceeded.failure_taxonomy == "round_exceeded"
    assert token.failure_taxonomy == "token_exceeded"


def test_platform_runner_should_continue_respects_single_mode_and_budgets():
    runner = PlatformAutonomyRunner()

    single_state = runner.start(PlatformRunConfig(mode="single"))
    runner.record_result(
        single_state,
        challenge_id="1",
        challenge_name="OnlyOne",
        url="https://ctf.example.com/1",
        result=_result(success=True),
        stop_reason="flag_verified",
        started_at=time.time() - 1,
        ended_at=time.time(),
    )
    assert runner.should_continue(
        single_state, operator_stop=False, queue_snapshot=None
    ) == (False, "single_mode")

    budget_state = runner.start(PlatformRunConfig(mode="switch", max_challenges=1))
    runner.record_result(
        budget_state,
        challenge_id="1",
        challenge_name="Budgeted",
        url="https://ctf.example.com/1",
        result=_result(success=True),
        stop_reason="flag_verified",
        started_at=time.time() - 1,
        ended_at=time.time(),
    )
    assert runner.should_continue(
        budget_state, operator_stop=False, queue_snapshot=None
    ) == (False, "challenge_budget_exhausted")

    timebox_state = runner.start(
        PlatformRunConfig(mode="switch", max_challenges=5, timebox_seconds=1)
    )
    timebox_state.started_at = time.time() - 5
    assert runner.should_continue(
        timebox_state, operator_stop=False, queue_snapshot=None
    ) == (False, "timebox_exhausted")

    stop_state = runner.start(
        PlatformRunConfig(mode="switch", max_consecutive_stops=2)
    )
    stop_state.consecutive_stops = 2
    assert runner.should_continue(
        stop_state, operator_stop=False, queue_snapshot=None
    ) == (False, "consecutive_stops_exhausted")


def test_platform_runner_should_continue_respects_queue_and_rate_limit():
    runner = PlatformAutonomyRunner()
    state = runner.start(PlatformRunConfig(mode="drain", max_challenges=5))

    throttled, throttled_reason = runner.should_continue(
        state,
        operator_stop=False,
        queue_snapshot={
            "unsolved_count": 3,
            "rate_limited_until": time.time() + 60,
        },
    )
    assert throttled is False
    assert throttled_reason == "submit_rate_limited"

    exhausted, exhausted_reason = runner.should_continue(
        state,
        operator_stop=False,
        queue_snapshot={
            "unsolved_count": 0,
            "rate_limited_until": 0.0,
        },
    )
    assert exhausted is False
    assert exhausted_reason == "queue_exhausted"

    proceed, proceed_reason = runner.should_continue(
        state,
        operator_stop=False,
        queue_snapshot={
            "unsolved_count": 2,
            "rate_limited_until": 0.0,
        },
    )
    assert proceed is True
    assert proceed_reason == "continue"


def test_platform_runner_mark_switch_tracks_visited_keys():
    runner = PlatformAutonomyRunner()
    state = runner.start(
        PlatformRunConfig(mode="switch"),
        initial_visit_key="42|https://ctf.example.com/challenges/42",
    )

    runner.mark_switch(
        state,
        "43|https://ctf.example.com/challenges/43",
        reason="next_unsolved_highest_priority",
        source="platform_queue",
    )

    assert state.switched_count == 1
    assert state.visited_keys == {
        "42|https://ctf.example.com/challenges/42",
        "43|https://ctf.example.com/challenges/43",
    }
    assert state.last_switch_reason == "next_unsolved_highest_priority"
    assert state.last_switch_source == "platform_queue"
    summary = state.to_dict()
    assert summary["last_switch_reason"] == "next_unsolved_highest_priority"
    assert summary["switch_events"][0]["source"] == "platform_queue"


def test_platform_runner_restore_preserves_progress_and_marks_resume_context():
    runner = PlatformAutonomyRunner()
    state = runner.start(
        PlatformRunConfig(mode="drain", max_challenges=6, timebox_seconds=1200),
        initial_visit_key="42|https://ctf.example.com/challenges/42",
    )
    started_at = time.time() - 2
    runner.record_result(
        state,
        challenge_id="42",
        challenge_name="EasySQL",
        url="https://ctf.example.com/challenges/42",
        result=_result(success=True, chain_used=["sqli"]),
        stop_reason="flag_verified",
        started_at=started_at,
        ended_at=started_at + 0.5,
    )
    runner.mark_switch(
        state,
        "43|https://ctf.example.com/challenges/43",
        reason="next_unsolved_highest_priority",
        source="platform_queue",
    )

    restored = runner.restore(
        state.to_dict(),
        config=PlatformRunConfig(mode="switch", max_challenges=3, timebox_seconds=600),
        initial_visit_key="44|https://ctf.example.com/challenges/44",
        resume_reason="operator_hint_restart",
    )

    assert restored.config.mode == "switch"
    assert restored.config.max_challenges == 3
    assert restored.resume_count == 1
    assert restored.resumed_from_record_count == 1
    assert restored.resume_reason == "operator_hint_restart"
    assert restored.last_resumed_at > 0
    assert restored.visited_keys == {
        "42|https://ctf.example.com/challenges/42",
        "43|https://ctf.example.com/challenges/43",
        "44|https://ctf.example.com/challenges/44",
    }
    assert restored.records[0].challenge_id == "42"
    assert restored.records[0].outcome == "solved"
    summary = restored.to_dict()
    assert summary["resume_count"] == 1
    assert summary["resume_reason"] == "operator_hint_restart"
