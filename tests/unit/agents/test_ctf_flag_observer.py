from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.flag_observer import FlagObserver

_FLAG_OBSERVER_MODULE = "flaghunter.agents.pa_agent.flag_observer"


def test_observe_flag_lives_in_flag_observer_mixin():
    assert CTFTaskDispatcher._observe_flag.__module__ == _FLAG_OBSERVER_MODULE


# --- FlagObserver runs fully detached from CTFTaskDispatcher ---


def _make_verification(
    *,
    decision,
    flag="FLAG{x}",
    rationale="because",
    confidence=0.9,
    proof=None,
    metadata=None,
):
    return SimpleNamespace(
        decision=decision,
        flag=flag,
        rationale=rationale,
        confidence=confidence,
        proof=proof,
        metadata=metadata if metadata is not None else {"verification_path": "vp"},
    )


def _make_collaborators(verification):
    verifier = SimpleNamespace(verify_flag=AsyncMock(return_value=verification))
    return {
        "verifier": verifier,
        "store_note": AsyncMock(),
        "record_session_event": MagicMock(),
        "hydrate_flag_proof": MagicMock(),
        "record_wrong_flag_feedback": AsyncMock(),
    }


async def _observe(observer, *, state, collaborators, hyp_ctx=None, strat_ctx=None, **biz):
    biz.setdefault("flag", "FLAG{x}")
    biz.setdefault("target", "http://host/path")
    biz.setdefault("evidence_source", "browser")
    return await observer.observe_flag(
        state,
        verifier=collaborators["verifier"],
        store_note=collaborators["store_note"],
        record_session_event=collaborators["record_session_event"],
        hydrate_flag_proof=collaborators["hydrate_flag_proof"],
        record_wrong_flag_feedback=collaborators["record_wrong_flag_feedback"],
        active_hypothesis_context=hyp_ctx,
        active_strategy_context=strat_ctx,
        **biz,
    )


@pytest.mark.asyncio
async def test_observe_flag_none_state_short_circuits():
    observer = FlagObserver()
    collab = _make_collaborators(_make_verification(decision="verified"))
    result = await _observe(observer, state=None, collaborators=collab)
    assert result is None
    collab["verifier"].verify_flag.assert_not_called()
    collab["store_note"].assert_not_called()
    collab["record_session_event"].assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "decision,expected_key",
    [
        ("candidate", "ctf_flag_candidate"),
        ("runtime", "ctf_flag_runtime"),
        ("verified", "ctf_flag"),
        ("rejected", "ctf_flag_rejected"),
    ],
)
async def test_observe_flag_decision_store_note_keys(decision, expected_key):
    observer = FlagObserver()
    collab = _make_collaborators(_make_verification(decision=decision))
    state = SimpleNamespace()
    await _observe(observer, state=state, collaborators=collab)
    collab["store_note"].assert_awaited_once()
    assert collab["store_note"].await_args.kwargs["key"] == expected_key
    # session event always recorded once
    collab["record_session_event"].assert_called_once()


@pytest.mark.asyncio
async def test_observe_flag_rejected_with_flag_records_wrong_feedback():
    observer = FlagObserver()
    collab = _make_collaborators(
        _make_verification(decision="rejected", flag="FLAG{bad}")
    )
    await _observe(observer, state=SimpleNamespace(), collaborators=collab)
    collab["record_wrong_flag_feedback"].assert_awaited_once()


@pytest.mark.asyncio
async def test_observe_flag_rejected_without_flag_skips_wrong_feedback():
    observer = FlagObserver()
    collab = _make_collaborators(
        _make_verification(decision="rejected", flag="")
    )
    await _observe(observer, state=SimpleNamespace(), collaborators=collab)
    collab["record_wrong_flag_feedback"].assert_not_called()


@pytest.mark.asyncio
async def test_observe_flag_hydrates_proof_when_present():
    observer = FlagObserver()
    proof = SimpleNamespace()
    collab = _make_collaborators(
        _make_verification(decision="verified", proof=proof)
    )
    await _observe(observer, state=SimpleNamespace(), collaborators=collab)
    collab["hydrate_flag_proof"].assert_called_once()


@pytest.mark.asyncio
async def test_observe_flag_no_proof_skips_hydrate():
    observer = FlagObserver()
    collab = _make_collaborators(
        _make_verification(decision="verified", proof=None)
    )
    await _observe(observer, state=SimpleNamespace(), collaborators=collab)
    collab["hydrate_flag_proof"].assert_not_called()


@pytest.mark.asyncio
async def test_observe_flag_does_not_eager_hold_state_or_context():
    """Two successive calls with distinct state/context objects must each be
    forwarded by value (no eager-held reference)."""
    observer = FlagObserver()

    state1 = SimpleNamespace(tag="s1")
    state2 = SimpleNamespace(tag="s2")
    hyp1 = SimpleNamespace(id="h1", kind="k1")
    hyp2 = SimpleNamespace(id="h2", kind="k2")

    collab1 = _make_collaborators(_make_verification(decision="candidate"))
    await _observe(observer, state=state1, collaborators=collab1, hyp_ctx=hyp1)
    assert collab1["verifier"].verify_flag.await_args.args[0] is state1
    assert collab1["verifier"].verify_flag.await_args.kwargs["hypothesis_id"] == "h1"

    collab2 = _make_collaborators(_make_verification(decision="candidate"))
    await _observe(observer, state=state2, collaborators=collab2, hyp_ctx=hyp2)
    assert collab2["verifier"].verify_flag.await_args.args[0] is state2
    assert collab2["verifier"].verify_flag.await_args.kwargs["hypothesis_id"] == "h2"
