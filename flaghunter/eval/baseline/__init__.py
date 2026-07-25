"""Real solve-rate baseline harness.

Unlike ``flaghunter.eval.replay`` (which re-drives a *recorded* solve
deterministically against scripted responses to prove read-side contracts hold),
this package measures the **live product outcome**: point FlagHunter at real
authorized targets and score how many flags it actually captures, at what cost.

The replay harness answers "did the code stay correct?"; the baseline harness
answers "can it solve more challenges, faster, cheaper?" — the product north star.

Design:
- ``corpus``  — a stable, tiered manifest of challenges (metadata only; ephemeral
  target URLs are supplied at run time via a target map).
- ``judge``   — extract the flag / verdict / cost signals from a completed run.
- ``runner``  — drive ``flaghunter run`` per challenge as an isolated subprocess.
- ``report``  — aggregate scorecard rows into a reviewable markdown scorecard.

Live runs need operator-supplied infrastructure (authorized instances, LLM
credentials, optional Kali SSH runtime). The harness itself is deterministic and
side-effect-free in ``--dry-run`` mode so its plumbing can be tested offline.
"""

from __future__ import annotations

from .corpus import Challenge, Tier, load_corpus
from .judge import Verdict, judge_run
from .runner import ScorecardRow, run_baseline

__all__ = [
    "Challenge",
    "Tier",
    "load_corpus",
    "Verdict",
    "judge_run",
    "ScorecardRow",
    "run_baseline",
]
