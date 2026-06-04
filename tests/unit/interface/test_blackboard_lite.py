from __future__ import annotations

from types import SimpleNamespace

from pentestagent.agents.pa_agent.ctf_state import CTFState, Hypothesis
from pentestagent.interface.blackboard_lite import (
    build_entry_blackboard_snapshot,
    build_task_blackboard_snapshot,
    format_blackboard_snapshot_lines,
    normalize_blackboard_snapshot,
    serialize_blackboard_snapshot,
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


def test_build_task_blackboard_snapshot_projects_state_hypotheses_separately_from_facts() -> None:
    state = CTFState(target="http://challenge.test", goal="拿到flag")
    state.hypotheses = [
        Hypothesis(
            id="hyp-1",
            kind="auth_form_sqli",
            description="login form may be injectable",
            confidence=0.78,
            status="supported",
            supporting_observations=["recon_url:/login", "form:username,password"],
            next_experiments=["try auth bypass payloads"],
        ),
        Hypothesis(
            id="hyp-2",
            kind="generic_web_recon",
            description="continue low-cost endpoint mapping",
            confidence=0.42,
            status="active",
            supporting_observations=["root page lists admin and visit"],
            counter_evidence=["no obvious debug endpoint yet"],
            next_experiments=["fetch app.js"],
        ),
    ]
    state.add_observation(
        "recon_url",
        "http://challenge.test/admin",
        source="recon",
        metadata={"confidence": "high"},
    )

    snapshot = build_task_blackboard_snapshot({"ctfStateSnapshot": state.to_snapshot()})

    assert ("discovered_endpoint", "http://challenge.test/admin") in {
        (item["kind"], item.get("value")) for item in snapshot["facts"]
    }
    assert snapshot["hypotheses"] == [
        {
            "id": "hyp-1",
            "kind": "auth_form_sqli",
            "description": "login form may be injectable",
            "confidence": 0.78,
            "status": "supported",
            "supportingObservations": ["recon_url:/login", "form:username,password"],
            "counterEvidence": [],
            "nextExperiments": ["try auth bypass payloads"],
        },
        {
            "id": "hyp-2",
            "kind": "generic_web_recon",
            "description": "continue low-cost endpoint mapping",
            "confidence": 0.42,
            "status": "active",
            "supportingObservations": ["root page lists admin and visit"],
            "counterEvidence": ["no obvious debug endpoint yet"],
            "nextExperiments": ["fetch app.js"],
        },
    ]


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
        "action_results": [],
        "recommended_action": {},
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
                "facts": [
                    "mode=ctf",
                    "strongestHypothesisKind=generic_web_recon",
                    "strongestHypothesisStatus=active",
                    "strongestHypothesisConfidence=0.52",
                ],
            },
            "ctfStateSnapshot": state.to_snapshot(),
        }
    )

    assert snapshot["active_decision"] == {
        "decisionKind": "explore_first",
        "nextAction": "collect_initial_facts",
        "driver": "blackboard.derived_target.runtime_derived",
        "reason": "derived target available for initial fact collection",
        "strongestHypothesisKind": "generic_web_recon",
        "strongestHypothesisStatus": "active",
        "strongestHypothesisConfidence": 0.52,
    }
    candidates = snapshot["candidates"]
    selected = [item for item in candidates if item["selected"] is True]
    assert selected
    assert selected[0]["action"] == "collect_initial_facts"
    assert selected[0]["sourceType"] == "observation"
    assert selected[0]["strongestHypothesisKind"] == "generic_web_recon"
    assert selected[0]["strongestHypothesisStatus"] == "active"
    assert selected[0]["strongestHypothesisConfidence"] == 0.52
    backup = [item for item in candidates if item["action"] == "probe_discovered_endpoint"]
    assert backup
    assert backup[0]["selected"] is False
    assert backup[0]["sourceType"] == "observation"


def test_build_task_blackboard_snapshot_projects_action_results_and_candidate_last_result() -> None:
    state = CTFState(target="http://challenge.test", goal="拿到flag")
    state.add_observation(
        "derived_target",
        "http://127.0.0.1:3000",
        source="challenge_context",
        metadata={"compose_path": r"D:\webstudy\CTF\easy_login\docker-compose.yml"},
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
        },
        session_context={
            "recentEvents": [
                {
                    "type": "control_action_completed",
                    "t": "2026-06-03T10:00:02+00:00",
                    "payload": {
                        "action": "collect_initial_facts",
                        "driver": "blackboard.derived_target.runtime_derived",
                        "result": "ok",
                        "details": {"facts_collected": 3},
                    },
                }
            ]
        },
    )

    assert snapshot["action_results"] == [
        {
            "action": "collect_initial_facts",
            "driver": "blackboard.derived_target.runtime_derived",
            "result": "ok",
            "t": "2026-06-03T10:00:02+00:00",
            "details": {"facts_collected": 3},
        }
    ]
    selected = [item for item in snapshot["candidates"] if item["action"] == "collect_initial_facts"][0]
    assert selected["lastResult"] == "ok"
    assert snapshot["recommended_action"] == {}


def test_build_task_blackboard_snapshot_recommends_next_best_action_after_selected_failure() -> None:
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
        },
        session_context={
            "recentEvents": [
                {
                    "type": "control_action_completed",
                    "t": "2026-06-03T10:00:02+00:00",
                    "payload": {
                        "action": "collect_initial_facts",
                        "driver": "blackboard.derived_target.runtime_derived",
                        "result": "failed",
                        "strongest_hypothesis_kind": "generic_web_recon",
                        "strongest_hypothesis_status": "active",
                        "strongest_hypothesis_confidence": 0.52,
                        "details": {"reason": "no new facts"},
                    },
                }
            ]
        },
    )

    assert snapshot["active_decision"]["nextAction"] == "collect_initial_facts"
    assert snapshot["recommended_action"] == {
        "action": "probe_discovered_endpoint",
        "driver": "blackboard.discovered_endpoint",
        "sourceType": "observation",
        "reason": "selected action failed; switch to next best candidate",
        "switchedFrom": "collect_initial_facts",
        "triggerResult": "failed",
        "triggerReason": "no new facts",
        "triggerActionDriver": "blackboard.derived_target.runtime_derived",
        "triggerAt": "2026-06-03T10:00:02+00:00",
        "strongestHypothesisKind": "generic_web_recon",
        "strongestHypothesisStatus": "active",
        "strongestHypothesisConfidence": 0.52,
    }
    recommended = [item for item in snapshot["candidates"] if item["action"] == "probe_discovered_endpoint"][0]
    assert recommended["recommended"] is True
    assert recommended["sourceType"] == "observation"
    assert recommended["strongestHypothesisKind"] == "generic_web_recon"
    assert recommended["strongestHypothesisStatus"] == "active"
    assert recommended["strongestHypothesisConfidence"] == 0.52


def test_build_task_blackboard_snapshot_recommends_next_best_action_after_selected_skip() -> None:
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
        },
        session_context={
            "recentEvents": [
                {
                    "type": "control_action_completed",
                    "t": "2026-06-03T10:00:02+00:00",
                    "payload": {
                        "action": "collect_initial_facts",
                        "driver": "blackboard.derived_target.runtime_derived",
                        "result": "skipped",
                        "details": {"reason": "already explored from inherited trace"},
                    },
                }
            ]
        },
    )

    assert snapshot["active_decision"]["nextAction"] == "collect_initial_facts"
    assert snapshot["recommended_action"] == {
        "action": "probe_discovered_endpoint",
        "driver": "blackboard.discovered_endpoint",
        "sourceType": "observation",
        "reason": "selected action failed; switch to next best candidate",
        "switchedFrom": "collect_initial_facts",
        "triggerResult": "skipped",
        "triggerReason": "already explored from inherited trace",
        "triggerActionDriver": "blackboard.derived_target.runtime_derived",
        "triggerAt": "2026-06-03T10:00:02+00:00",
    }


def test_normalize_blackboard_snapshot_accepts_snake_and_camel_shape() -> None:
    normalized = normalize_blackboard_snapshot(
        {
            "facts": [{"kind": "derived_target", "value": "http://127.0.0.1:3000"}],
            "pending_verifications": [{"kind": "runtime_flag", "value": "flag{runtime}"}],
            "decisions": [{"kind": "direct_execute"}],
            "candidates": [{"action": "collect_initial_facts"}],
            "action_results": [{"action": "collect_initial_facts", "result": "ok"}],
            "recommended_action": {"action": "probe_discovered_endpoint"},
            "active_decision": {"nextAction": "collect_initial_facts"},
        }
    )

    assert normalized == {
        "facts": [{"kind": "derived_target", "value": "http://127.0.0.1:3000"}],
        "hypotheses": [],
        "pendingVerifications": [{"kind": "runtime_flag", "value": "flag{runtime}"}],
        "decisions": [{"kind": "direct_execute"}],
        "candidates": [{"action": "collect_initial_facts"}],
        "actionResults": [{"action": "collect_initial_facts", "result": "ok"}],
        "recommendedAction": {"action": "probe_discovered_endpoint"},
        "activeDecision": {"nextAction": "collect_initial_facts"},
    }


def test_serialize_blackboard_snapshot_projects_public_contract() -> None:
    serialized = serialize_blackboard_snapshot(
        {
            "facts": [{"kind": "verified_flag", "value": "flag{ok}"}],
            "hypotheses": [],
            "pending_verifications": [{"kind": "runtime_flag", "value": "flag{runtime}"}],
            "decisions": [{"kind": "direct_execute"}],
            "candidates": [{"action": "verify_or_submit_flag"}],
            "action_results": [{"action": "verify_runtime_signal", "result": "failed"}],
            "recommended_action": {"action": "verify_or_submit_flag"},
            "active_decision": {"nextAction": "verify_runtime_signal"},
        }
    )

    assert serialized == {
        "facts": [{"kind": "verified_flag", "value": "flag{ok}"}],
        "hypotheses": [],
        "pendingVerifications": [{"kind": "runtime_flag", "value": "flag{runtime}"}],
        "decisions": [{"kind": "direct_execute"}],
        "candidates": [{"action": "verify_or_submit_flag"}],
        "actionResults": [{"action": "verify_runtime_signal", "result": "failed"}],
        "recommendedAction": {"action": "verify_or_submit_flag"},
        "activeDecision": {"nextAction": "verify_runtime_signal"},
    }


def test_format_blackboard_snapshot_lines_projects_shared_sections() -> None:
    lines = format_blackboard_snapshot_lines(
        {
            "facts": [{"kind": "verified_flag", "value": "flag{ok}"}],
            "hypotheses": [
                {
                    "id": "hyp-1",
                    "kind": "auth_form_sqli",
                    "confidence": 0.78,
                    "status": "supported",
                }
            ],
            "pending_verifications": [{"kind": "runtime_flag", "value": "flag{runtime}"}],
            "active_decision": {
                "decisionKind": "direct_execute",
                "nextAction": "verify_runtime_signal",
                "driver": "blackboard.runtime_flag",
                "reason": "runtime flag pending verification in blackboard",
                "expectedAction": "verify_runtime_signal",
                "observedAction": "verify_runtime_signal",
                "alignment": "aligned",
                "alignmentReason": "coordinator followed ingress action",
                "suppressedRecommendation": {
                    "action": "resume_from_checkpoint",
                    "driver": "blackboard.resume_context",
                    "reason": "resume context available",
                    "suppressedBy": "blackboard.runtime_flag",
                },
            },
            "recommended_action": {
                "action": "verify_or_submit_flag",
                "driver": "blackboard.verified_flag",
                "sourceType": "verification",
                "reason": "selected action failed; switch to next best candidate",
                "switchedFrom": "verify_runtime_signal",
                "triggerResult": "failed",
                "triggerReason": "runtime verifier rejected candidate",
                "triggerActionDriver": "blackboard.runtime_flag",
                "triggerAt": "2026-06-03T10:00:02+00:00",
            },
            "action_results": [
                {
                    "action": "verify_runtime_signal",
                    "driver": "blackboard.runtime_flag",
                    "result": "failed",
                    "expectedAction": "verify_runtime_signal",
                    "alignment": "aligned",
                    "alignmentReason": "coordinator followed ingress action",
                }
            ],
        }
    )

    assert "[blackboard_facts]" in lines
    assert "verified_flag=flag{ok}" in lines
    assert "[blackboard_hypotheses]" in lines
    assert "hyp-1:auth_form_sqli [supported/0.78]" in lines
    assert "[blackboard_pending_verifications]" in lines
    assert "runtime_flag=flag{runtime}" in lines
    assert "[blackboard_active_decision]" in lines
    assert "decisionKind=direct_execute" in lines
    assert "suppressedRecommendation.suppressedBy=blackboard.runtime_flag" in lines
    assert "[blackboard_recommended_action]" in lines
    assert "action=verify_or_submit_flag" in lines
    assert "sourceType=verification" in lines
    assert "switchedFrom=verify_runtime_signal" in lines
    assert "triggerResult=failed" in lines
    assert "triggerReason=runtime verifier rejected candidate" in lines
    assert "triggerActionDriver=blackboard.runtime_flag" in lines
    assert "triggerAt=2026-06-03T10:00:02+00:00" in lines
    assert "[blackboard_action_results]" in lines
    assert "result=failed" in lines


def test_build_task_blackboard_snapshot_projects_first_action_alignment_into_active_decision_and_action_results() -> None:
    state = CTFState(target="http://challenge.test", goal="拿到flag")
    state.add_observation(
        "derived_target",
        "http://127.0.0.1:3000",
        source="challenge_context",
        metadata={"compose_path": r"D:\webstudy\CTF\easy_login\docker-compose.yml"},
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
        },
        session_context={
            "recentEvents": [
                {
                    "type": "control_action_started",
                    "t": "2026-06-03T10:00:01+00:00",
                    "payload": {
                        "action": "verify_runtime_signal",
                        "expected_action": "collect_initial_facts",
                        "alignment": "mismatched",
                        "alignment_reason": "runtime verification preempted planned first action",
                        "switched_from": "collect_initial_facts",
                        "trigger_reason": "runtime verifier rejected candidate",
                        "driver": "blackboard.runtime_flag",
                    },
                },
                {
                    "type": "control_action_completed",
                    "t": "2026-06-03T10:00:02+00:00",
                    "payload": {
                        "action": "verify_runtime_signal",
                        "driver": "blackboard.runtime_flag",
                        "result": "ok",
                        "details": {"verified": True},
                        "switched_from": "collect_initial_facts",
                        "trigger_reason": "runtime verifier rejected candidate",
                    },
                },
            ]
        },
    )

    assert snapshot["active_decision"] == {
        "decisionKind": "explore_first",
        "nextAction": "collect_initial_facts",
        "driver": "blackboard.derived_target.runtime_derived",
        "reason": "derived target available for initial fact collection",
        "expectedAction": "collect_initial_facts",
        "observedAction": "verify_runtime_signal",
        "alignment": "mismatched",
        "alignmentReason": "runtime verification preempted planned first action",
        "switchedFrom": "collect_initial_facts",
        "triggerReason": "runtime verifier rejected candidate",
    }
    assert snapshot["action_results"] == [
        {
            "action": "verify_runtime_signal",
            "driver": "blackboard.runtime_flag",
            "result": "ok",
            "t": "2026-06-03T10:00:02+00:00",
            "details": {"verified": True},
            "expectedAction": "collect_initial_facts",
            "alignment": "mismatched",
            "alignmentReason": "runtime verification preempted planned first action",
            "switchedFrom": "collect_initial_facts",
            "triggerReason": "runtime verifier rejected candidate",
        }
    ]


def test_build_task_blackboard_snapshot_projects_strongest_hypothesis_into_active_decision_and_action_results() -> None:
    state = CTFState(target="http://challenge.test", goal="拿到flag")
    state.add_observation(
        "derived_target",
        "http://127.0.0.1:3000",
        source="challenge_context",
        metadata={"compose_path": r"D:\webstudy\CTF\easy_login\docker-compose.yml"},
    )

    snapshot = build_task_blackboard_snapshot(
        {
            "controlDecision": {
                "shouldRun": True,
                "decisionKind": "explore_first",
                "reason": "derived target available for initial fact collection",
                "nextAction": "collect_initial_facts",
                "driver": "blackboard.derived_target.runtime_derived",
                "facts": [
                    "mode=ctf",
                    "blackboard.hypothesis=present",
                    "strongestHypothesisKind=generic_web_recon",
                    "strongestHypothesisStatus=active",
                ],
            },
            "ctfStateSnapshot": state.to_snapshot(),
        },
        session_context={
            "recentEvents": [
                {
                    "type": "control_action_started",
                    "t": "2026-06-03T10:00:01+00:00",
                    "payload": {
                        "action": "collect_initial_facts",
                        "expected_action": "collect_initial_facts",
                        "alignment": "matched",
                        "driver": "blackboard.derived_target.runtime_derived",
                        "strongest_hypothesis_kind": "generic_web_recon",
                        "strongest_hypothesis_status": "active",
                        "strongest_hypothesis_confidence": 0.52,
                    },
                },
                {
                    "type": "control_action_completed",
                    "t": "2026-06-03T10:00:02+00:00",
                    "payload": {
                        "action": "collect_initial_facts",
                        "driver": "blackboard.derived_target.runtime_derived",
                        "result": "ok",
                        "details": {"facts_collected": 3},
                        "strongest_hypothesis_kind": "generic_web_recon",
                        "strongest_hypothesis_status": "active",
                        "strongest_hypothesis_confidence": 0.52,
                    },
                },
            ]
        },
    )

    assert snapshot["active_decision"]["strongestHypothesisKind"] == "generic_web_recon"
    assert snapshot["active_decision"]["strongestHypothesisStatus"] == "active"
    assert snapshot["active_decision"]["strongestHypothesisConfidence"] == 0.52
    assert snapshot["action_results"][0]["strongestHypothesisKind"] == "generic_web_recon"
    assert snapshot["action_results"][0]["strongestHypothesisStatus"] == "active"
    assert snapshot["action_results"][0]["strongestHypothesisConfidence"] == 0.52


def test_build_task_blackboard_snapshot_projects_suppressed_recommendation_into_active_decision() -> None:
    snapshot = build_task_blackboard_snapshot(
        {
            "controlDecision": {
                "shouldRun": True,
                "decisionKind": "direct_execute",
                "reason": "verified flag already present in blackboard",
                "nextAction": "verify_or_submit_flag",
                "driver": "blackboard.verified_flag",
                "facts": [
                    "mode=ctf",
                    "blackboard.verified_flag=present",
                    "blackboard.recommended_action=suppressed",
                ],
                "suppressedRecommendation": {
                    "action": "collect_initial_facts",
                    "driver": "blackboard.derived_target.runtime_derived",
                    "reason": "selected action failed; switch to next best candidate",
                    "suppressedBy": "blackboard.verified_flag",
                },
            },
        }
    )

    assert snapshot["active_decision"]["nextAction"] == "verify_or_submit_flag"
    assert snapshot["active_decision"]["suppressedRecommendation"] == {
        "action": "collect_initial_facts",
        "driver": "blackboard.derived_target.runtime_derived",
        "reason": "selected action failed; switch to next best candidate",
        "suppressedBy": "blackboard.verified_flag",
    }
