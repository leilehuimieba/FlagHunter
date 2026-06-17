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
    """

    progress: bool = False
    flag: str | None = None
    reason: str = ""
