"""A-05 — Web terminal success is proof-backed, never a flag-string heuristic.

``_resolve_terminal_outcome`` is the single policy the web task runner uses to
map a run result to a terminal status. Success must require a proof-backed
verified flag; a near-solve candidate (dispatcher ``SolveResult.flag`` while
``success is False``) or a regex-scanned flag from model output must surface as
``candidateFlag`` and stay ``stopped`` — driving the false-success rate to 0
(总纲 §4.3 / F-05 sibling on the web control plane).
"""

from __future__ import annotations

from flaghunter.interface.web_server import _resolve_terminal_outcome


def test_verified_flag_is_success():
    out = _resolve_terminal_outcome(
        verified=True,
        verified_flag="flag{real}",
        candidate_flag=None,
        stop_reason=None,
    )
    assert out["status"] == "success"
    assert out["finalFlag"] == "flag{real}"
    assert out["candidateFlag"] is None
    assert out["stopReason"] is None


def test_dispatcher_near_solve_candidate_is_not_success():
    # SolveResult.flag set (near-solve) but success False → candidate, not verified.
    out = _resolve_terminal_outcome(
        verified=False,
        verified_flag=None,
        candidate_flag="flag{near}",
        stop_reason="blackboard_loop:stop|wait_for_verification",
    )
    assert out["status"] == "stopped"
    assert out["finalFlag"] is None
    assert out["candidateFlag"] == "flag{near}"
    assert out["stopReason"] == "blackboard_loop:stop|wait_for_verification"


def test_regex_candidate_without_proof_is_not_success():
    # Generic agent loop: a flag scanned from model output, no verifier.
    out = _resolve_terminal_outcome(
        verified=False,
        verified_flag=None,
        candidate_flag="flag{scanned}",
        stop_reason=None,
    )
    assert out["status"] == "stopped"
    assert out["finalFlag"] is None
    assert out["candidateFlag"] == "flag{scanned}"
    # A candidate without an explicit stop reason gets a truthful default.
    assert out["stopReason"] == "candidate_flag_unverified"


def test_no_flag_at_all_is_stopped_no_flag_found():
    out = _resolve_terminal_outcome(
        verified=False,
        verified_flag=None,
        candidate_flag=None,
        stop_reason=None,
    )
    assert out["status"] == "stopped"
    assert out["finalFlag"] is None
    assert out["candidateFlag"] is None
    assert out["stopReason"] == "no_flag_found"


def test_verified_true_but_no_flag_is_not_success():
    # Defensive: verified must come with an actual verified flag to succeed.
    out = _resolve_terminal_outcome(
        verified=True,
        verified_flag=None,
        candidate_flag=None,
        stop_reason="odd_state",
    )
    assert out["status"] == "stopped"
    assert out["finalFlag"] is None
