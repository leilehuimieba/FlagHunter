from __future__ import annotations

import pytest

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
    assert decision["driver"] == "task.resume_context"


def test_verified_flag_outranks_resume_context() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "resumeContext": {
            "runId": "run-prev-1",
            "checkpointId": "checkpoint-prev-1",
        },
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
    assert decision["driver"] == "blackboard.verified_flag"


def test_runtime_flag_outranks_resume_context() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "resumeContext": {
            "runId": "run-prev-1",
            "checkpointId": "checkpoint-prev-1",
        },
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
    assert decision["driver"] == "blackboard.runtime_flag"


def test_verified_flag_outranks_resume_bootstrap_hint() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "resume_bootstrap_hint",
                    "value": "continue from saved recon state",
                    "source": "ingress_handoff",
                    "confidence": "high",
                },
                {
                    "kind": "verified_flag",
                    "value": "flag{done}",
                    "source": "admin_page",
                    "confidence": "high",
                },
            ],
            "pendingVerifications": [],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "direct_execute"
    assert decision["nextAction"] == "verify_or_submit_flag"
    assert decision["driver"] == "blackboard.verified_flag"


def test_runtime_flag_outranks_resume_bootstrap_hint() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "resume_bootstrap_hint",
                    "value": "continue from saved recon state",
                    "source": "ingress_handoff",
                    "confidence": "high",
                }
            ],
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
    assert decision["driver"] == "blackboard.runtime_flag"


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


def test_initial_fact_collection_in_blackboard_prevents_repeated_local_bootstrap() -> None:
    payload = {
        "mode": "ctf",
        "goal": "solve local challenge",
        "target": "http://127.0.0.1:3000",
        "challengePath": r"D:\webstudy\CTF\2026\sample",
        "artifactPaths": [r"D:\webstudy\CTF\2026\sample\docker-compose.yml"],
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "initial_fact_collection_requested",
                    "value": "http://127.0.0.1:3000",
                    "source": "control_decision",
                    "confidence": "high",
                }
            ],
            "pendingVerifications": [],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "explore_first"
    assert decision["nextAction"] == "collect_initial_facts"
    assert decision["driver"] == "blackboard.initial_fact_collection_requested"
    assert decision["reason"] == "initial fact collection already requested in blackboard"
    assert "blackboard.initial_fact_collection_requested=present" in decision["facts"]


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


def test_derived_target_in_blackboard_unblocks_missing_target_flow() -> None:
    payload = {
        "mode": "ctf",
        "goal": "solve challenge",
        "target": "",
        "challengePath": None,
        "artifactPaths": [],
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "derived_target",
                    "value": "http://127.0.0.1:3000",
                    "source": "challenge_context",
                    "confidence": "high",
                }
            ],
            "pendingVerifications": [],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "explore_first"
    assert decision["nextAction"] == "collect_initial_facts"
    assert "blackboard.derived_target=present" in decision["facts"]
    assert "target=http://127.0.0.1:3000" in decision["facts"]
    assert "derivedTargetOrigin=runtime_derived" in decision["facts"]
    assert decision["driver"] == "blackboard.derived_target.runtime_derived"
    assert decision["reason"] == "derived target available for initial fact collection"


def test_explicit_target_prevents_blackboard_derived_target_override() -> None:
    payload = {
        "mode": "ctf",
        "goal": "solve challenge",
        "target": "http://challenge.test",
        "challengePath": None,
        "artifactPaths": [],
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "derived_target",
                    "value": "http://127.0.0.1:3000",
                    "source": "challenge_context",
                    "confidence": "high",
                }
            ],
            "pendingVerifications": [],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "explore_first"
    assert "target=http://challenge.test" in decision["facts"]
    assert "target=http://127.0.0.1:3000" not in decision["facts"]


def test_direct_derived_target_fields_set_inherited_lineage_driver() -> None:
    payload = {
        "mode": "ctf",
        "goal": "solve challenge",
        "target": "",
        "challengePath": None,
        "artifactPaths": [],
        "sourceRunId": "run-prev-1",
        "derivedTarget": "http://127.0.0.1:3000",
        "derivedTargetSource": "docker_compose_port_mapping",
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "explore_first"
    assert decision["nextAction"] == "collect_initial_facts"
    assert decision["driver"] == "task.derived_target.inherited_lineage"
    assert "derivedTargetOrigin=inherited_lineage" in decision["facts"]
    assert "derivedTargetSource=docker_compose_port_mapping" in decision["facts"]



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


def test_resume_bootstrap_hint_outranks_initial_fact_collection_observation() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://127.0.0.1:3000",
        "challengePath": r"D:\webstudy\CTF\2026\sample",
        "artifactPaths": [r"D:\webstudy\CTF\2026\sample\docker-compose.yml"],
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "initial_fact_collection_requested",
                    "value": "http://127.0.0.1:3000",
                    "source": "control_decision",
                    "confidence": "high",
                },
                {
                    "kind": "resume_bootstrap_hint",
                    "value": "continue from saved recon state",
                    "source": "ingress_handoff",
                    "confidence": "high",
                },
            ],
            "pendingVerifications": [],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "resume_execute"
    assert decision["nextAction"] == "resume_from_checkpoint"
    assert decision["driver"] == "blackboard.resume_bootstrap_hint"
    assert "blackboard.resume_bootstrap_hint=present" in decision["facts"]


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


def test_leaked_secret_in_blackboard_prefers_secret_validation() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "leaked_secret",
                    "value": "SECRET-123",
                    "source": "ssti_identify",
                    "confidence": "medium",
                }
            ],
            "pendingVerifications": [],
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "direct_execute"
    assert decision["nextAction"] == "validate_leaked_secret"
    assert decision["driver"] == "blackboard.leaked_secret"


def test_recommended_action_in_blackboard_can_override_local_assets_fallback() -> None:
    payload = {
        "mode": "ctf",
        "target": "http://challenge.test",
        "challengePath": r"D:\webstudy\CTF\2026\sample",
        "artifactPaths": [r"D:\webstudy\CTF\2026\sample\docker-compose.yml"],
        "blackboardSnapshot": {
            "facts": [
                {
                    "kind": "derived_target",
                    "value": "http://127.0.0.1:3000",
                    "source": "challenge_context",
                    "confidence": "high",
                }
            ],
            "pendingVerifications": [],
            "recommendedAction": {
                "action": "collect_initial_facts",
                "driver": "blackboard.derived_target.runtime_derived",
                "reason": "selected action failed; switch to next best candidate",
            },
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "explore_first"
    assert decision["nextAction"] == "collect_initial_facts"
    assert decision["driver"] == "blackboard.derived_target.runtime_derived"
    assert decision["reason"] == "selected action failed; switch to next best candidate"
    assert "blackboard.recommended_action=present" in decision["facts"]


def test_verified_flag_still_outranks_recommended_action() -> None:
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
            "recommendedAction": {
                "action": "collect_initial_facts",
                "driver": "blackboard.derived_target.runtime_derived",
                "reason": "selected action failed; switch to next best candidate",
            },
        },
    }

    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True
    assert decision["decisionKind"] == "direct_execute"
    assert decision["nextAction"] == "verify_or_submit_flag"
    assert decision["driver"] == "blackboard.verified_flag"


@pytest.mark.parametrize(
    ("name", "payload", "expected_kind", "expected_action", "expected_driver"),
    [
        (
            "verified_over_everything",
            {
                "mode": "ctf",
                "target": "http://challenge.test",
                "resumeContext": {"runId": "run-prev-1", "checkpointId": "cp-prev-1"},
                "challengePath": r"D:\webstudy\CTF\2026\sample",
                "artifactPaths": [r"D:\webstudy\CTF\2026\sample\docker-compose.yml"],
                "blackboardSnapshot": {
                    "facts": [
                        {"kind": "resume_bootstrap_hint", "value": "continue from saved recon state"},
                        {"kind": "initial_fact_collection_requested", "value": "http://challenge.test"},
                        {"kind": "verified_flag", "value": "flag{done}", "source": "admin_page"},
                    ],
                    "pendingVerifications": [
                        {"kind": "runtime_flag", "value": "flag{runtime_candidate}", "source": "collector", "rationale": "runtime hit"}
                    ],
                },
            },
            "direct_execute",
            "verify_or_submit_flag",
            "blackboard.verified_flag",
        ),
        (
            "runtime_over_resume_and_bootstrap",
            {
                "mode": "ctf",
                "target": "http://challenge.test",
                "resumeContext": {"runId": "run-prev-1", "checkpointId": "cp-prev-1"},
                "challengePath": r"D:\webstudy\CTF\2026\sample",
                "artifactPaths": [r"D:\webstudy\CTF\2026\sample\docker-compose.yml"],
                "blackboardSnapshot": {
                    "facts": [
                        {"kind": "resume_bootstrap_hint", "value": "continue from saved recon state"},
                        {"kind": "initial_fact_collection_requested", "value": "http://challenge.test"},
                    ],
                    "pendingVerifications": [
                        {"kind": "runtime_flag", "value": "flag{runtime_candidate}", "source": "collector", "rationale": "runtime hit"}
                    ],
                },
            },
            "direct_execute",
            "verify_runtime_signal",
            "blackboard.runtime_flag",
        ),
        (
            "resume_context_over_resume_hint_and_initial_facts",
            {
                "mode": "ctf",
                "target": "http://challenge.test",
                "resumeContext": {"runId": "run-prev-1", "checkpointId": "cp-prev-1"},
                "challengePath": r"D:\webstudy\CTF\2026\sample",
                "artifactPaths": [r"D:\webstudy\CTF\2026\sample\docker-compose.yml"],
                "blackboardSnapshot": {
                    "facts": [
                        {"kind": "resume_bootstrap_hint", "value": "continue from saved recon state"},
                        {"kind": "initial_fact_collection_requested", "value": "http://challenge.test"},
                    ],
                    "pendingVerifications": [],
                },
            },
            "resume_execute",
            "resume_from_checkpoint",
            "task.resume_context",
        ),
        (
            "resume_hint_over_initial_facts",
            {
                "mode": "ctf",
                "target": "http://challenge.test",
                "challengePath": r"D:\webstudy\CTF\2026\sample",
                "artifactPaths": [r"D:\webstudy\CTF\2026\sample\docker-compose.yml"],
                "blackboardSnapshot": {
                    "facts": [
                        {"kind": "resume_bootstrap_hint", "value": "continue from saved recon state"},
                        {"kind": "initial_fact_collection_requested", "value": "http://challenge.test"},
                    ],
                    "pendingVerifications": [],
                },
            },
            "resume_execute",
            "resume_from_checkpoint",
            "blackboard.resume_bootstrap_hint",
        ),
        (
            "initial_facts_over_local_bootstrap",
            {
                "mode": "ctf",
                "target": "http://challenge.test",
                "challengePath": r"D:\webstudy\CTF\2026\sample",
                "artifactPaths": [r"D:\webstudy\CTF\2026\sample\docker-compose.yml"],
                "blackboardSnapshot": {
                    "facts": [
                        {"kind": "initial_fact_collection_requested", "value": "http://challenge.test"},
                    ],
                    "pendingVerifications": [],
                },
            },
            "explore_first",
            "collect_initial_facts",
            "blackboard.initial_fact_collection_requested",
        ),
        (
            "local_assets_fallback",
            {
                "mode": "ctf",
                "target": "http://challenge.test",
                "challengePath": r"D:\webstudy\CTF\2026\sample",
                "artifactPaths": [r"D:\webstudy\CTF\2026\sample\docker-compose.yml"],
            },
            "direct_execute",
            "bootstrap_local_assets",
            "",
        ),
    ],
)
def test_control_decision_priority_matrix(
    name: str,
    payload: dict,
    expected_kind: str,
    expected_action: str,
    expected_driver: str,
) -> None:
    decision = resolve_control_decision(payload)

    assert decision["shouldRun"] is True, name
    assert decision["decisionKind"] == expected_kind, name
    assert decision["nextAction"] == expected_action, name
    assert str(decision.get("driver") or "") == expected_driver, name
