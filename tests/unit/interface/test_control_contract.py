from __future__ import annotations

from pentestagent.interface.control_contract import resolve_control_decision


def test_resume_context_prefers_resume_execute() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "sessionContext": {
            "resumeContext": {
                "runId": "run-123",
                "checkpointId": "cp-1",
            }
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "resume_execute"
    assert decision["nextAction"] == "resume_from_checkpoint"


def test_ctf_local_assets_prefers_direct_execute() -> None:
    payload = {
        "mode": "ctf",
        "goal": "solve local challenge",
        "challengePath": r"D:\webstudy\CTF\2026\sample.zip",
        "artifactPaths": [r"D:\webstudy\CTF\2026\hint.txt"],
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "direct_execute"
    assert decision["nextAction"] == "bootstrap_local_assets"


def test_missing_target_and_local_assets_blocks_run() -> None:
    payload = {
        "mode": "pentest",
        "goal": "assess target",
        "target": "",
        "challengePath": None,
        "artifactPaths": [],
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is False
    assert decision["decisionKind"] == "blocked"
    assert decision["nextAction"] == "await_input"


def test_target_without_local_assets_defaults_to_explore_first() -> None:
    payload = {
        "mode": "pentest",
        "goal": "assess target",
        "target": "http://corp.test",
        "challengePath": None,
        "artifactPaths": [],
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "explore_first"
    assert decision["nextAction"] == "collect_initial_facts"



def test_verified_flag_in_blackboard_prefers_verify_or_submit_flag() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "verified_flag",
                    "value": "flag{done}",
                    "source": "admin_page",
                    "confidence": "high",
                }
            ],
            "pendingVerifications": [],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "direct_execute"
    assert decision["nextAction"] == "verify_or_submit_flag"



def test_runtime_flag_in_blackboard_prefers_verify_runtime_signal() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "blackboardSnapshot": {
            "facts": [],
            "pendingVerifications": [
                {
                    "kind": "runtime_flag",
                    "value": "flag{runtime_candidate}",
                    "source": "collector",
                    "rationale": "runtime hit",
                }
            ],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "direct_execute"
    assert decision["nextAction"] == "verify_runtime_signal"



def test_verified_flag_blackboard_decision_sets_driver() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "verified_flag",
                    "value": "flag{done}",
                    "source": "admin_page",
                    "confidence": "high",
                }
            ],
            "pendingVerifications": [],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["driver"] == "blackboard.verified_flag"



def test_runtime_flag_blackboard_decision_sets_driver() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "blackboardSnapshot": {
            "facts": [],
            "pendingVerifications": [
                {
                    "kind": "runtime_flag",
                    "value": "flag{runtime_candidate}",
                    "source": "collector",
                    "rationale": "runtime hit",
                }
            ],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["driver"] == "blackboard.runtime_flag"


def test_resume_bootstrap_hint_in_blackboard_prefers_resume_execute() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "resume_bootstrap_hint",
                    "value": "runId=run-prev-1 checkpointId=cp-prev-1",
                    "source": "ingress_handoff",
                    "confidence": "high",
                }
            ],
            "pendingVerifications": [],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "resume_execute"
    assert decision["nextAction"] == "resume_from_checkpoint"
    assert decision["driver"] == "blackboard.resume_bootstrap_hint"


def test_identified_engine_in_blackboard_prefers_engine_direct_execute() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "identified_engine",
                    "value": "tornado",
                    "source": "ssti_identify",
                    "confidence": "high",
                }
            ],
            "pendingVerifications": [],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "direct_execute"
    assert decision["nextAction"] == "exploit_identified_engine"
    assert decision["driver"] == "blackboard.identified_engine"


def test_discovered_endpoint_in_blackboard_prefers_endpoint_probe() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "discovered_endpoint",
                    "value": "http://challenge.test/admin",
                    "source": "recon",
                    "confidence": "high",
                }
            ],
            "pendingVerifications": [],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "direct_execute"
    assert decision["nextAction"] == "probe_discovered_endpoint"
    assert decision["driver"] == "blackboard.discovered_endpoint"
