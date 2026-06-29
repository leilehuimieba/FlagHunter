"""Canonical kill-chain phase vocabulary (P1)."""

from __future__ import annotations

from flaghunter.knowledge.kill_chain import (
    ALL_PHASES,
    PHASE_ORDER,
    RECON_SOURCE_TAG,
    Phase,
    is_phase,
    phase_index,
    phase_round_budget,
)


def test_phase_order_is_the_kill_chain_spine():
    assert PHASE_ORDER == (
        "init",
        "setup",
        "recon",
        "diagnose",
        "hypothesis",
        "exploit",
        "verify",
        "recover",
        "done",
    )
    assert ALL_PHASES == set(PHASE_ORDER)


def test_phase_index_orders_recon_before_exploit():
    assert phase_index(Phase.RECON) < phase_index(Phase.EXPLOIT)
    assert phase_index("nonsense") == -1


def test_is_phase():
    assert is_phase(Phase.HYPOTHESIS)
    assert not is_phase("phase_recon")  # the source tag is not a phase name


def test_recon_source_tag_is_the_historical_literal():
    # Downstream code matches observations on this exact string; it must not drift.
    assert RECON_SOURCE_TAG == "phase_recon"


def test_only_exploit_phase_has_a_round_budget():
    # EXPLOIT is the only looping phase, so it's the only one with a backstop.
    assert phase_round_budget(Phase.EXPLOIT) == 24
    assert phase_round_budget(Phase.RECON) is None
    assert phase_round_budget(Phase.SETUP) is None
    assert phase_round_budget("nonsense") is None
