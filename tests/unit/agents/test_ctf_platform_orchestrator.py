from __future__ import annotations

import time

from flaghunter.agents.pa_agent.platform_orchestrator import (
    PlatformTaskOrchestrator,
)


def test_platform_orchestrator_prioritizes_unsolved_and_current_challenge():
    orchestrator = PlatformTaskOrchestrator()

    snapshot = orchestrator.build_queue_snapshot(
        platform_type="ctfd",
        base_url="https://ctf.example.com",
        current_challenge_id="2",
        challenge_briefs=[
            {"id": "1", "name": "SolvedOne", "solved": True, "points": 500},
            {"id": "2", "name": "CurrentUnsolved", "solved": False, "points": 100},
            {"id": "3", "name": "HighPointUnsolved", "solved": False, "points": 300},
        ],
        submit_attempts=[],
    )

    assert snapshot.total == 3
    assert snapshot.unsolved_count == 2
    assert snapshot.tasks[0].challenge_id == "3"
    assert snapshot.tasks[1].challenge_id == "2"
    assert snapshot.next_challenge_id == "3"


def test_platform_orchestrator_rate_limits_recent_submit_burst():
    orchestrator = PlatformTaskOrchestrator()
    now = time.time()
    attempts = [
        {
            "type": "flag_submit_attempt",
            "flag": f"flag{{{idx}}}",
            "created_at": now - idx,
        }
        for idx in range(3)
    ]

    result = orchestrator.assess_submit_rate_limit(
        attempts,
        now=now,
        window_seconds=30,
        max_attempts=3,
    )

    assert result["throttled"] is True
    assert result["attempt_count"] == 3
    assert result["rate_limited_until"] > now


def test_platform_orchestrator_selects_next_task_and_explains_skips():
    orchestrator = PlatformTaskOrchestrator()
    snapshot = orchestrator.build_queue_snapshot(
        platform_type="ctfd",
        base_url="https://ctf.example.com",
        current_challenge_id="42",
        challenge_briefs=[
            {"id": "1", "name": "SolvedOne", "solved": True, "url": "/challenges/1"},
            {"id": "42", "name": "Current", "solved": False, "url": "/challenges/42"},
            {"id": "99", "name": "Visited", "solved": False, "url": "/challenges/99"},
            {"id": "100", "name": "NextOne", "solved": False, "url": "/challenges/100"},
        ],
        submit_attempts=[],
    )

    selection = orchestrator.select_next_task(
        snapshot,
        current_challenge_id="42",
        visited_keys={"99|/challenges/99"},
    )

    assert selection["task"]["challenge_id"] == "100"
    assert selection["switch_reason"] == "next_unsolved_highest_priority"
    assert selection["switch_source"] == "platform_queue"
    skip_reasons = {item["skip_reason"] for item in selection["skipped_candidates"]}
    assert "current_challenge" in skip_reasons
