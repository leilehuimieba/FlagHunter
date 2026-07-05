"""Characterization tests for the trace timeline read-model switch candidate."""

from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path
from typing import Any

from flaghunter.interface.web_trace_timeline import (
    _build_control_observation_timeline_events,
    _build_trace_timeline,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
TRACE_TIMELINE_PATH = REPO_ROOT / "flaghunter" / "interface" / "web_trace_timeline.py"
PLAYBOOK_PATH = (
    REPO_ROOT
    / "docs"
    / "dev"
    / "FlagHunter_Clean_Architecture_Migration_Playbook_v0.1_2026-07-04.md"
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


def _parse_trace_timeline() -> ast.Module:
    return ast.parse(
        TRACE_TIMELINE_PATH.read_text(encoding="utf-8-sig"),
        filename=str(TRACE_TIMELINE_PATH),
    )


def _function_source(tree: ast.Module, name: str) -> str:
    text = TRACE_TIMELINE_PATH.read_text(encoding="utf-8-sig")
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(f"{name} was not found")


def _playbook_text() -> str:
    return PLAYBOOK_PATH.read_text(encoding="utf-8")


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


def test_control_observation_timeline_source_stays_read_only() -> None:
    tree = _parse_trace_timeline()
    helper_source = _function_source(tree, "_build_control_observation_timeline_events")
    forbidden_imports = {
        "flaghunter.tools",
        "flaghunter.runtime",
        "flaghunter.agents",
        "flaghunter.mcp",
        "flaghunter.session",
        "subprocess",
        "requests",
        "httpx",
        "socket",
        "playwright",
    }
    forbidden_names = {
        "ToolExecutor",
        "WorkerPool",
        "CrewOrchestrator",
        "CTFTaskDispatcher",
        "CTFState",
        "CTFVerifier",
    }
    forbidden_helper_tokens = {
        "open(",
        "write_text",
        "subprocess",
        "requests",
        "httpx",
        "socket",
        "playwright",
        "verification_decision",
        "upgrade_claim_to_verified",
        "append_verification_record",
        "append_proof_record",
        "confirm_claim",
        'level="verified"',
        "level='verified'",
        "verified_flags",
    }
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (
                    alias.name in forbidden_names
                    or any(
                        alias.name == module or alias.name.startswith(f"{module}.")
                        for module in forbidden_imports
                    )
                ):
                    offenders.append(f"import {alias.name}")
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if any(
                module == forbidden_module or module.startswith(f"{forbidden_module}.")
                for forbidden_module in forbidden_imports
            ):
                offenders.append(f"from {module}")
            for alias in node.names:
                if alias.name in forbidden_names:
                    offenders.append(f"from {module} import {alias.name}")

    offenders.extend(
        token for token in forbidden_helper_tokens if token in helper_source
    )

    assert offenders == []


def test_candidate_b_pre_approval_guard_blocks_neutral_projection_wiring() -> None:
    playbook = _playbook_text()
    assert "Candidate B pre-approval production switch guard" in playbook
    assert "Candidate B: ready for approval review, not approved" in playbook

    source = TRACE_TIMELINE_PATH.read_text(encoding="utf-8-sig")
    forbidden_wiring_tokens = {
        "flaghunter.application.challenge",
        "flaghunter.domain.challenge.contracts",
        "board_read_model_service",
        "build_task_board_projection",
        "BuildChallengeBoardReadModel",
        "ChallengeBoardReadModel",
    }

    assert sorted(token for token in forbidden_wiring_tokens if token in source) == []
