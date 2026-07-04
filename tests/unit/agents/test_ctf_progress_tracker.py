from types import SimpleNamespace

from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.ctf_state import (
    CTFState,
    ClaimKind,
    ClaimLevel,
    VerificationDecision,
    VerificationMethod,
)
from flaghunter.agents.pa_agent.progress_tracker import ProgressTracker

_PROGRESS_TRACKER_MODULE = "flaghunter.agents.pa_agent.progress_tracker"


def test_progress_delta_methods_live_in_progress_tracker_mixin():
    for name in ("_snapshot_flag_counts", "_derive_progress_delta"):
        assert getattr(CTFTaskDispatcher, name).__module__ == _PROGRESS_TRACKER_MODULE


def _make_state(
    *,
    candidate=0,
    runtime=0,
    verified=0,
    rejected=0,
    uniform_failures=0,
):
    observations = [
        SimpleNamespace(kind="uniform_failure_surface")
        for _ in range(uniform_failures)
    ]
    # add an unrelated observation to prove the filter is by kind
    observations.append(SimpleNamespace(kind="something_else"))
    return SimpleNamespace(
        candidate_flags=list(range(candidate)),
        runtime_flags=list(range(runtime)),
        verified_flags=list(range(verified)),
        rejected_flags=list(range(rejected)),
        observations=observations,
    )


# --- ProgressTracker runs fully detached from CTFTaskDispatcher ---


def test_snapshot_flag_counts_none_guard():
    assert ProgressTracker().snapshot_flag_counts(None) == {}


def test_snapshot_flag_counts_increments():
    tracker = ProgressTracker()
    state = _make_state(
        candidate=2, runtime=3, verified=1, rejected=4, uniform_failures=5
    )
    assert tracker.snapshot_flag_counts(state) == {
        "candidate": 2,
        "runtime": 3,
        "verified": 1,
        "rejected": 4,
        "uniform_failure_surface": 5,
    }


def test_derive_progress_delta_none_guard():
    assert ProgressTracker().derive_progress_delta(None, {}) == "none"


def test_derive_progress_delta_grades():
    tracker = ProgressTracker()
    before = {
        "candidate": 0,
        "runtime": 0,
        "verified": 0,
        "rejected": 0,
        "uniform_failure_surface": 0,
    }
    assert tracker.derive_progress_delta(_make_state(verified=1), before) == "terminal"
    assert tracker.derive_progress_delta(_make_state(runtime=1), before) == "strong"
    assert (
        tracker.derive_progress_delta(_make_state(uniform_failures=1), before)
        == "rejected"
    )
    assert tracker.derive_progress_delta(_make_state(candidate=1), before) == "weak"
    assert tracker.derive_progress_delta(_make_state(), before) == "none"


def test_derive_progress_delta_chain_outcome_progress_short_circuits_to_none():
    tracker = ProgressTracker()
    before = {"uniform_failure_surface": 0}
    state = _make_state(uniform_failures=1)
    progressing_outcome = SimpleNamespace(progress=True)
    # uniform-failure delta would normally grade "rejected", but a progressing
    # chain outcome must keep the hypothesis alive -> "none".
    assert (
        tracker.derive_progress_delta(state, before, chain_outcome=progressing_outcome)
        == "none"
    )
    # no/false progress falls through to "rejected".
    assert (
        tracker.derive_progress_delta(
            state, before, chain_outcome=SimpleNamespace(progress=False)
        )
        == "rejected"
    )


def _runtime_flag_claim(state: CTFState, value: str):
    claim = state.create_claim(
        kind=ClaimKind.FLAG_FOUND,
        content=value,
        level=ClaimLevel.CONJECTURE,
        producer_type="test",
        producer_id="progress",
        primary_trace_id=f"trace:{value}",
    )
    state.append_verification_record(
        claim.id,
        verifier_type="verifier",
        verifier_id="ctf_verifier",
        method=VerificationMethod.RUNTIME_HTTP,
        decision=VerificationDecision.RUNTIME_SUPPORTED,
        trace_id=f"verify:{value}",
        passed=True,
    )
    return claim


def test_snapshot_flag_counts_includes_canonical_flag_claims_when_enabled(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="get flag")
    _runtime_flag_claim(state, "flag{claim_runtime}")

    counts = ProgressTracker().snapshot_flag_counts(state)

    assert counts["claim_flag_found_total"] == 1
    assert counts["claim_flag_found_runtime"] == 1
    assert counts["claim_flag_found_verified"] == 0
    assert counts["claim_flag_found_retracted"] == 0


def test_derive_progress_delta_reads_canonical_runtime_claim_when_enabled(monkeypatch):
    monkeypatch.setenv("FLAGHUNTER_CTF_CLAIMS_V1", "1")
    state = CTFState(target="http://ctf.local", goal="get flag")
    before = ProgressTracker().snapshot_flag_counts(state)
    _runtime_flag_claim(state, "flag{claim_runtime}")

    assert ProgressTracker().derive_progress_delta(state, before) == "strong"
