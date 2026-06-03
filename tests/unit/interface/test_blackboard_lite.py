from __future__ import annotations

from types import SimpleNamespace

from pentestagent.agents.pa_agent.ctf_state import CTFState
from pentestagent.interface.blackboard_lite import (
    build_entry_blackboard_snapshot,
    build_task_blackboard_snapshot,
)
from pentestagent.mcp.server.mcp_tools import TaskEntry


def test_build_task_blackboard_snapshot_aggregates_ingress_decision_and_resume_facts() -> None:
    state = CTFState(target="http://challenge.test", goal="拿到flag")
    state.add_observation(
        "resume_bootstrap_hint",
        "continue from saved recon state",
        source="ingress_handoff",
        metadata={
            "decision_kind": "resume_execute",
            "next_action": "resume_from_checkpoint",
            "run_id": "run-prev-1",
            "checkpoint_id": "checkpoint-prev-1",
        },
    )
    state.add_flag(
        "flag{runtime_pending}",
        level="runtime",
        evidence_source="collector",
        rationale="runtime hit",
    )
    state.add_flag(
        "flag{verified_done}",
        level="verified",
        evidence_source="admin_page",
        rationale="verified hit",
    )
    state.add_artifact(
        "docker-compose.yml",
        location=r"D:\webstudy\CTF6\CTF比赛题\easy_login\docker-compose.yml",
        source="local_challenge_context",
    )

    task = {
        "id": "task-1",
        "controlDecision": {
            "shouldRun": True,
            "decisionKind": "resume_execute",
            "reason": "resume context available",
            "nextAction": "resume_from_checkpoint",
            "facts": ["mode=ctf", "challengePath=D:/sample"],
        },
        "decisionRecords": [
            {
                "kind": "resume_execute",
                "source": "web_ingress",
                "nextAction": "resume_from_checkpoint",
                "reason": "resume context available",
            }
        ],
        "ingressHandoff": {
            "decisionKind": "resume_execute",
            "nextAction": "resume_from_checkpoint",
            "challengeContext": {
                "challengePath": r"D:\webstudy\CTF6\CTF比赛题\easy_login",
                "artifactPaths": [
                    r"D:\webstudy\CTF6\CTF比赛题\easy_login\docker-compose.yml"
                ],
            },
            "resumeBootstrap": {
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "summary": "continue from saved recon state",
            },
        },
        "ctfStateSnapshot": state.to_snapshot(),
    }

    snapshot = build_task_blackboard_snapshot(task)

    assert snapshot["facts"]
    assert snapshot["decisions"]
    assert snapshot["pending_verifications"]
    assert snapshot["hypotheses"] == []

    fact_kinds = {(item["kind"], item.get("value")) for item in snapshot["facts"]}
    assert ("control_decision", "resume_execute") in fact_kinds
    assert ("next_action", "resume_from_checkpoint") in fact_kinds
    assert ("challenge_path", r"D:\webstudy\CTF6\CTF比赛题\easy_login") in fact_kinds
    assert ("resume_run_id", "run-prev-1") in fact_kinds
    assert ("resume_checkpoint_id", "checkpoint-prev-1") in fact_kinds
    assert ("resume_bootstrap_hint", "continue from saved recon state") in fact_kinds
    assert ("verified_flag", "flag{verified_done}") in fact_kinds
    assert ("artifact", r"D:\webstudy\CTF6\CTF比赛题\easy_login\docker-compose.yml") in fact_kinds

    pending = snapshot["pending_verifications"]
    assert pending == [
        {
            "kind": "runtime_flag",
            "value": "flag{runtime_pending}",
            "source": "collector",
            "rationale": "runtime hit",
        }
    ]

    assert snapshot["decisions"] == [
        {
            "kind": "resume_execute",
            "source": "web_ingress",
            "nextAction": "resume_from_checkpoint",
            "reason": "resume context available",
        }
    ]
    assert snapshot["active_decision"] == {
        "decisionKind": "resume_execute",
        "nextAction": "resume_from_checkpoint",
        "driver": "",
        "reason": "resume context available",
    }
    resume_candidates = [item for item in snapshot["candidates"] if item["action"] == "resume_from_checkpoint"]
    assert resume_candidates
    assert resume_candidates[0]["selected"] is True
    assert resume_candidates[0]["priority"] == 0


def test_build_entry_blackboard_snapshot_matches_web_contract() -> None:
    state = CTFState(target="http://challenge.test", goal="拿到flag")
    state.add_observation(
        "resume_bootstrap_hint",
        "continue from saved recon state",
        source="ingress_handoff",
        metadata={
            "decision_kind": "resume_execute",
            "next_action": "resume_from_checkpoint",
            "run_id": "run-prev-1",
            "checkpoint_id": "checkpoint-prev-1",
        },
    )
    state.add_flag(
        "flag{runtime_pending}",
        level="runtime",
        evidence_source="collector",
        rationale="runtime hit",
    )
    state.add_flag(
        "flag{verified_done}",
        level="verified",
        evidence_source="admin_page",
        rationale="verified hit",
    )

    entry = TaskEntry(
        id="entry-1",
        task="solve challenge",
        status="done",
        created_at="2026-06-02T00:00:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        controlDecision={
            "shouldRun": True,
            "decisionKind": "resume_execute",
            "reason": "resume context available",
            "nextAction": "resume_from_checkpoint",
            "facts": ["mode=ctf"],
        },
        decisionRecords=[
            {
                "kind": "resume_execute",
                "source": "mcp_ingress",
                "nextAction": "resume_from_checkpoint",
                "reason": "resume context available",
            }
        ],
        ingressHandoff={
            "decisionKind": "resume_execute",
            "nextAction": "resume_from_checkpoint",
            "challengeContext": {
                "challengePath": r"D:\webstudy\CTF6\CTF比赛题\easy_login",
                "artifactPaths": [
                    r"D:\webstudy\CTF6\CTF比赛题\easy_login\docker-compose.yml"
                ],
            },
            "resumeBootstrap": {
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "summary": "continue from saved recon state",
            },
        },
    )
    entry.ctfStateSnapshot = state.to_snapshot()

    snapshot = build_entry_blackboard_snapshot(entry)

    assert snapshot["hypotheses"] == []
    fact_kinds = {(item["kind"], item.get("value")) for item in snapshot["facts"]}
    assert ("control_decision", "resume_execute") in fact_kinds
    assert ("challenge_path", r"D:\webstudy\CTF6\CTF比赛题\easy_login") in fact_kinds
    assert ("resume_run_id", "run-prev-1") in fact_kinds
    assert ("resume_bootstrap_hint", "continue from saved recon state") in fact_kinds
    assert ("verified_flag", "flag{verified_done}") in fact_kinds
    assert snapshot["pending_verifications"][0]["value"] == "flag{runtime_pending}"
    assert snapshot["decisions"][0]["source"] == "mcp_ingress"



def test_build_task_blackboard_snapshot_maps_high_value_observations_into_facts() -> None:
    state = CTFState(target="http://challenge.test", goal="拿到flag")
    state.add_observation(
        "initial_fact_collection_requested",
        "http://challenge.test",
        source="control_decision",
        metadata={
            "driver": "blackboard.derived_target.runtime_derived",
            "reason": "derived target available for initial fact collection",
            "next_action": "collect_initial_facts",
        },
    )
    state.add_observation(
        "recon_url",
        "http://challenge.test/admin",
        source="recon",
        metadata={"confidence": "high"},
    )
    state.add_observation(
        "ssti_engine_identified",
        "tornado",
        source="ssti_identify",
        metadata={"engine": "tornado"},
    )
    state.add_observation(
        "cookie_secret_leaked",
        "SECRET-123",
        source="ssti_identify",
        metadata={"method": "handler_settings_probe"},
    )
    state.add_observation(
        "http_response",
        "200:/admin page reachable",
        source="http_request",
        metadata={"status_code": 200},
    )
    state.add_observation(
        "derived_target",
        "http://127.0.0.1:3000",
        source="challenge_context",
        metadata={"compose_path": r"D:\webstudy\CTF\easy_login\docker-compose.yml"},
    )

    snapshot = build_task_blackboard_snapshot(
        {
            "ctfStateSnapshot": state.to_snapshot(),
        }
    )

    facts = {(item["kind"], item.get("value")) for item in snapshot["facts"]}
    assert ("initial_fact_collection_requested", "http://challenge.test") in facts
    assert ("discovered_endpoint", "http://challenge.test/admin") in facts
    assert ("identified_engine", "tornado") in facts
    assert ("leaked_secret", "SECRET-123") in facts
    assert ("recent_http_response", "200:/admin page reachable") in facts
    assert ("derived_target", "http://127.0.0.1:3000") in facts
    candidate_actions = {item["action"] for item in snapshot["candidates"]}
    assert "collect_initial_facts" in candidate_actions
    assert "probe_discovered_endpoint" in candidate_actions
    assert "exploit_identified_engine" in candidate_actions
    assert "validate_leaked_secret" in candidate_actions



def test_build_task_blackboard_snapshot_fact_includes_source_and_confidence() -> None:
    state = CTFState(target="http://challenge.test", goal="拿到flag")
    state.add_observation(
        "recon_url",
        "http://challenge.test/admin",
        source="recon",
        metadata={"confidence": "high"},
    )
    state.add_observation(
        "cookie_secret_leaked",
        "SECRET-123",
        source="ssti_identify",
        metadata={"method": "handler_settings_probe"},
    )
    state.add_flag(
        "flag{verified_done}",
        level="verified",
        evidence_source="admin_page",
        rationale="verified hit",
    )

    snapshot = build_task_blackboard_snapshot({"ctfStateSnapshot": state.to_snapshot()})

    fact_map = {item["kind"]: item for item in snapshot["facts"]}
    assert fact_map["discovered_endpoint"]["source"] == "recon"
    assert fact_map["discovered_endpoint"]["confidence"] == "high"
    assert fact_map["leaked_secret"]["source"] == "ssti_identify"
    assert fact_map["leaked_secret"]["confidence"] == "medium"
    assert fact_map["verified_flag"]["source"] == "admin_page"
    assert fact_map["verified_flag"]["confidence"] == "high"


def test_build_task_blackboard_snapshot_tolerates_missing_state_snapshot() -> None:
    task = {
        "controlDecision": {
            "shouldRun": False,
            "decisionKind": "blocked",
            "reason": "target required",
            "nextAction": "await_input",
            "facts": [],
        },
        "decisionRecords": [],
        "ingressHandoff": {
            "decisionKind": "blocked",
            "nextAction": "await_input",
            "challengeContext": {},
            "resumeBootstrap": None,
        },
    }

    snapshot = build_task_blackboard_snapshot(task)

    assert snapshot == {
        "facts": [
            {"kind": "control_decision", "value": "blocked"},
            {"kind": "next_action", "value": "await_input"},
        ],
        "hypotheses": [],
        "pending_verifications": [],
        "decisions": [],
        "candidates": [],
        "active_decision": {
            "decisionKind": "blocked",
            "nextAction": "await_input",
            "driver": "",
            "reason": "target required",
        },
    }


def test_build_task_blackboard_snapshot_projects_selected_and_backup_candidates() -> None:
    state = CTFState(target="http://challenge.test", goal="拿到flag")
    state.add_observation(
        "derived_target",
        "http://127.0.0.1:3000",
        source="challenge_context",
        metadata={"compose_path": r"D:\webstudy\CTF\easy_login\docker-compose.yml"},
    )
    state.add_observation(
        "recon_url",
        "http://challenge.test/admin",
        source="recon",
        metadata={"confidence": "high"},
    )

    snapshot = build_task_blackboard_snapshot(
        {
            "controlDecision": {
                "shouldRun": True,
                "decisionKind": "explore_first",
                "reason": "derived target available for initial fact collection",
                "nextAction": "collect_initial_facts",
                "driver": "blackboard.derived_target.runtime_derived",
                "facts": ["mode=ctf"],
            },
            "ctfStateSnapshot": state.to_snapshot(),
        }
    )

    assert snapshot["active_decision"] == {
        "decisionKind": "explore_first",
        "nextAction": "collect_initial_facts",
        "driver": "blackboard.derived_target.runtime_derived",
        "reason": "derived target available for initial fact collection",
    }
    candidates = snapshot["candidates"]
    selected = [item for item in candidates if item["selected"] is True]
    assert selected
    assert selected[0]["action"] == "collect_initial_facts"
    backup = [item for item in candidates if item["action"] == "probe_discovered_endpoint"]
    assert backup
    assert backup[0]["selected"] is False
