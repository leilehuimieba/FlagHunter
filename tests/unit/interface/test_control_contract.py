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
