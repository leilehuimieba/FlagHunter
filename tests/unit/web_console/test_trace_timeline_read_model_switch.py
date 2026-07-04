"""Characterization tests for the trace timeline read-model switch candidate."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from flaghunter.interface.web_trace_timeline import (
    _build_control_observation_timeline_events,
    _build_trace_timeline,
)


def _task_with_observations(observations: list[Any]) -> dict[str, Any]:
    return {
        "id": "task-1",
        "createdAt": "2026-07-04T12:00:00+00:00",
        "startedAt": "2026-07-04T12:01:00+00:00",
        "target": "example.test",
        "ctfStateSnapshot": {
            "observations": observations,
        },
    }


def test_control_observation_timeline_projects_supported_rows() -> None:
    task = _task_with_observations([
        {
            "kind": "initial_fact_collection_requested",
            "value": "collect initial task facts",
            "source": "control",
            "metadata": {
                "driver": "control.initial_fact_collection",
                "reason": "missing starting facts",
                "next_action": "collect_initial_facts",
            },
        },
        {
            "kind": "resume_bootstrap_hint",
            "value": "resume from saved checkpoint",
            "source": "blackboard",
            "metadata": {},
        },
        {"kind": "ignored_kind", "value": "not displayed"},
        {"kind": "resume_bootstrap_hint", "value": ""},
        "not-a-row",
    ])

    assert _build_control_observation_timeline_events(task) == [
        {
            "id": "task-1:observation:1",
            "t": "2026-07-04T12:01:00+00:00",
            "type": "observation",
            "kind": "observation.initial_fact_collection_requested",
            "title": "initial fact collection requested",
            "summary": "collect initial task facts",
            "status": "done",
            "durationMs": None,
            "tokens": 0,
            "tool": None,
            "driver": "control.initial_fact_collection",
            "input": {
                "source": "control",
                "reason": "missing starting facts",
                "nextAction": "collect_initial_facts",
            },
        },
        {
            "id": "task-1:observation:2",
            "t": "2026-07-04T12:01:00+00:00",
            "type": "observation",
            "kind": "observation.resume_bootstrap_hint",
            "title": "resume bootstrap hint",
            "summary": "resume from saved checkpoint",
            "status": "done",
            "durationMs": None,
            "tokens": 0,
            "tool": None,
            "driver": "blackboard.resume_bootstrap_hint",
            "input": {
                "source": "blackboard",
                "reason": "resume bootstrap hint present in blackboard",
                "nextAction": "resume_from_checkpoint",
            },
        },
    ]


def test_control_observation_timeline_handles_empty_or_malformed_input() -> None:
    assert _build_control_observation_timeline_events({"id": "task-empty"}) == []
    assert _build_control_observation_timeline_events({
        "id": "task-bad-snapshot",
        "ctfStateSnapshot": "not-a-snapshot",
    }) == []
    assert _build_control_observation_timeline_events({
        "id": "task-bad-observations",
        "ctfStateSnapshot": {"observations": "not-a-list"},
    }) == []


def test_trace_timeline_includes_observations_without_mutating_task() -> None:
    task = _task_with_observations([
        {
            "kind": "resume_bootstrap_hint",
            "value": "resume from saved checkpoint",
            "source": "blackboard",
            "metadata": {},
        },
    ])
    before = deepcopy(task)

    timeline = _build_trace_timeline(task, metrics=None)

    assert task == before
    assert [event["kind"] for event in timeline] == [
        "task.started",
        "observation.resume_bootstrap_hint",
    ]
    assert timeline[1]["input"] == {
        "source": "blackboard",
        "reason": "resume bootstrap hint present in blackboard",
        "nextAction": "resume_from_checkpoint",
    }
