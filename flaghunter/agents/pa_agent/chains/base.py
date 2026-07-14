"""Shared, dependency-free types for the CTF chain mixins.

Kept free of any ``ctf_dispatcher`` import so both the dispatcher and the
per-chain mixin modules can import these without a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _ChainOutcome:
    """Result of running a chain or a single strategy.

    ``flag`` set ⇒ the sequence short-circuits and returns immediately;
    ``progress`` alone does not short-circuit (see _run_strategy_sequence).

    ``verified`` distinguishes a genuine TERMINAL win from a runtime near-solve:
    a chain that proves extraction (e.g. an upload webshell reading the flag off
    disk) returns ``flag`` with ``verified=True`` (the default) and is an
    unconditional solve. A live-exploit value the verifier could only rate
    "runtime" on a remote instance (e.g. a SQLi auth-bypass / UNION dump whose
    flag literally appeared in the response but was not platform-confirmed)
    returns ``flag`` with ``verified=False`` — it still short-circuits the
    sequence (and the blackboard loop still sees it in ``state.runtime_flags``),
    but the terminal-success contract routes it to wait_for_verification instead
    of fabricating a verified win (P1: runtime stays runtime).
    """

    progress: bool = False
    flag: str | None = None
    reason: str = ""
    verified: bool = True
