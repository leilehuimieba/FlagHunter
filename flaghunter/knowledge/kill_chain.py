"""Canonical kill-chain phase vocabulary (P1 — 装配线工序一等公民).

A single source of truth for the kill-chain *stages* a solve moves through, so
the "assembly line" the dispatcher already runs implicitly (see
``agents/pa_agent/coordinator.py:execute`` — a sequential pipeline of
``_apply_*_contract`` gates) becomes a **named, observable** thing instead of a
structure that only leaks out via ``source="phase_recon"`` magic strings.

This is vocabulary only — it does NOT gate control flow. ``CTFState.enter_phase``
stamps the current stage as the existing sequencer crosses each boundary; the
stamps are additive observability that downstream consumers read:
  * P4 stopping rule — "how long have we dwelt in EXPLOIT with no progress".
  * the blackboard / TUI — surface "what stage is this solve in".
  * provenance — tag tool calls with the phase they ran under.

Design rules (mirrors ``knowledge/blackboard_schema.py``):
  * stdlib only; lives in the CAPABILITY layer (``knowledge/``) so both
    ORCHESTRATION (agents) and ENTRY (interface) may import it. Must never
    import ``agents/``.
  * the ordered tuple is for "how far along" reasoning, NOT a hard state
    machine — real solves skip phases (early-exit shortcuts when a flag is
    already known) and revisit them (per-chain recovery re-ranks and loops).
"""

from __future__ import annotations


class Phase:
    """Kill-chain stage names. String constants (not StrEnum — keep 3.10 support)."""

    INIT = "init"            # pre-solve sentinel; before any contract runs
    SETUP = "setup"          # bootstrap / resume / asset ingestion
    RECON = "recon"          # layered info gathering (_phase_recon)
    DIAGNOSE = "diagnose"    # type detection from recon signals (detect_type)
    HYPOTHESIS = "hypothesis"  # hypothesis generation + chain ordering
    EXPLOIT = "exploit"      # the chain/exploit solve loop
    VERIFY = "verify"        # flag verification (回显 vs black-box)
    RECOVER = "recover"      # post-chain recovery / re-rank / switch
    DONE = "done"            # solve finished (success or exhausted)


# Canonical ordering of the kill-chain工序. Index = "how far along"; used for
# progress reasoning, NOT enforcement. VERIFY/RECOVER sit after EXPLOIT because
# they happen per-chain inside the solve loop.
PHASE_ORDER: tuple[str, ...] = (
    Phase.INIT,
    Phase.SETUP,
    Phase.RECON,
    Phase.DIAGNOSE,
    Phase.HYPOTHESIS,
    Phase.EXPLOIT,
    Phase.VERIFY,
    Phase.RECOVER,
    Phase.DONE,
)

ALL_PHASES: frozenset[str] = frozenset(PHASE_ORDER)

# The recon phase tags its observations with this source so downstream code can
# tell recon-derived facts apart (framework_detected, recon_url, …). Single home
# for the literal that was historically scattered as the bare "phase_recon"
# string, so the magic value and the Phase vocabulary can never drift apart.
RECON_SOURCE_TAG: str = "phase_recon"


def phase_index(phase: str) -> int:
    """Position of ``phase`` in the canonical order, or -1 if unknown."""
    try:
        return PHASE_ORDER.index(phase)
    except ValueError:
        return -1


def is_phase(value: str) -> bool:
    """True when ``value`` is a recognised canonical phase name."""
    return value in ALL_PHASES
