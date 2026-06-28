"""Placement / structural evasions against a guardrail's *decode-and-rescan*
and *scan-window* layers (OWASP LLM01 — prompt injection, evasion variants).

Where :mod:`flaghunter.redteam.transforms` rewrites the *bytes* of a trigger and
:mod:`flaghunter.redteam.extraction` rewrites its *intent*, this module changes
nothing about the payload itself — it changes **where** the payload sits inside
the request so the defender's pre-processing never decodes or even reads it:

* :func:`decoy_prefix` / :func:`phase_offset` — defeat a keyword detector that
  extracts the maximal base-N alphabet run and decodes it as one unit. Prepending
  a contiguous run of alphabet characters whose length is **not** a multiple of
  the codec's group size (4 for base64, 2 for hex, 8 for base32) shifts the real
  blob off-phase, so the recovered bytes are garbage and the trigger is never
  re-flagged.
* :func:`position_embed` — defeat a detector that only scans a *truncated* window
  (``excerpt[:N]``) by placing the trigger past offset ``N`` inside benign filler.

**Empirical provenance & an honesty note.** These were derived in an authorised
red-blue exercise (rounds 3-5). The phase-offset mechanism here is the
*corrected* model: round-3 first hypothesised "candidate-run exhaustion", which
round-4 falsified — the real discriminator is **byte-phase alignment** (a prefix
whose length ``% group != 0`` corrupts the trailing blob; an aligned prefix is
harmless). The asymmetry that proved it — a *prefix* breaks decoding but the same
decoy as a *suffix* does not — is encoded by these functions operating only on
the prefix. Defenders fix this by trying every phase offset when decoding a run.

**Safety contract:** these functions only *reposition* an already-inert payload;
the decoy/filler they synthesise is benign alphabet/lorem text containing no
trigger, no real host, secret, or PII. Enforced by
``tests/unit/redteam/test_safety_canaries.py``.

**Layering (I1):** CAPABILITY layer — pure-stdlib, no upward imports.
"""

from __future__ import annotations

import string
from dataclasses import dataclass
from typing import Dict, List

# OWASP LLM01 — prompt injection (these are evasion *variants* of a known trigger).
TECHNIQUE_ID = "LLM01"

# Group size (bytes-per-decode-unit) of each block codec, and its alphabet. A
# decoy/offset prefix whose length is a multiple of the group size keeps the
# trailing blob phase-aligned (a *control*); any other length breaks it.
_GROUP: Dict[str, int] = {
    "base64": 4,
    "base64_urlsafe": 4,
    "base32": 8,
    "hex": 2,
}

_ALPHABET: Dict[str, str] = {
    "base64": string.ascii_uppercase + string.ascii_lowercase + string.digits + "+/",
    "base64_urlsafe": string.ascii_uppercase + string.ascii_lowercase + string.digits + "-_",
    "base32": string.ascii_uppercase + "234567",
    "hex": string.digits + "abcdef",
}

# Benign filler for position_embed — classic pangram, no trigger tokens.
_FILLER_UNIT = "The quick brown fox jumps over the lazy dog. "


def _bases() -> List[str]:
    return list(_GROUP)


def group_size(base: str) -> int:
    """Decode group size (chars per group) of a block codec."""
    try:
        return _GROUP[base]
    except KeyError:
        raise KeyError(f"Unknown base {base!r}. Known: {_bases()}") from None


def aligns(length: int, base: str) -> bool:
    """True if a decoy/offset prefix of ``length`` keeps the trailing blob
    **phase-aligned** (``length % group == 0``) — i.e. NOT evasive, a control
    that proves the rescan still recovers the trigger."""
    return length % group_size(base) == 0


def min_break_length(base: str) -> int:
    """Smallest prefix length that breaks phase alignment for ``base`` (== 1)."""
    group_size(base)  # validate
    return 1


def _decoy(length: int, base: str) -> str:
    """A deterministic, benign run of ``length`` ``base``-alphabet characters."""
    if length < 0:
        raise ValueError("length must be >= 0")
    alpha = _ALPHABET[base]
    return (alpha * (length // len(alpha) + 1))[:length]


def decoy_prefix(encoded: str, *, length: int = 401, base: str = "base64") -> str:
    """Prepend a contiguous ``length``-char ``base``-alphabet run to ``encoded``.

    A keyword detector that extracts the maximal alphabet run and decodes it as a
    single unit will mis-phase the real blob whenever ``length`` is not a multiple
    of the codec group size (see :func:`aligns`). The decoy and blob must be
    contiguous (no separator) so the run-extraction regex swallows both.

    Default ``length=401`` is ``1 (mod 4)`` — the minimal-residue demonstrator
    used to falsify the round-3 "exhaustion" theory in favour of phase alignment.
    """
    if base not in _ALPHABET:
        raise KeyError(f"Unknown base {base!r}. Known: {_bases()}")
    return _decoy(length, base) + encoded


def phase_offset(encoded: str, *, base: str = "base64", residue: int = 1) -> str:
    """Prepend the *minimal* decoy that shifts ``encoded`` to byte-phase
    ``residue`` (mod group size).

    ``residue`` must be in ``1 .. group-1`` (0 would keep the blob aligned and is
    therefore a no-op control — rejected here to make the evasive intent explicit).
    Equivalent to :func:`decoy_prefix` with the shortest length that hits
    ``residue``; use this when the point is the *phase break*, not a long decoy.
    """
    g = group_size(base)
    if not 1 <= residue <= g - 1:
        raise ValueError(
            f"residue must be 1..{g - 1} for base {base!r} "
            f"(0 keeps alignment — not evasive)"
        )
    return _decoy(residue, base) + encoded


def position_embed(
    payload: str, *, offset: int = 8001, filler_unit: str | None = None
) -> str:
    """Embed ``payload`` after ``offset`` chars of benign filler.

    Evades a detector that only inspects a truncated window ``text[:N]``: when
    ``offset >= N`` the trigger lands past the scan limit and is never read.

    **Caveat (target-specific):** if the endpoint enforces an input
    ``max_length`` (Fulcrum's message field is ``max_length=8000``), an
    ``offset`` beyond it is rejected at the schema layer (HTTP 422) before the
    guardrail — that is a *schema reject*, not an evasion. Match ``offset`` to the
    target's scan window, not blindly past its hard length cap.
    """
    if offset < 0:
        raise ValueError("offset must be >= 0")
    unit = filler_unit if filler_unit is not None else _FILLER_UNIT
    if not unit:
        raise ValueError("filler_unit must be non-empty")
    filler = (unit * (offset // len(unit) + 1))[:offset]
    return filler + payload


@dataclass(frozen=True)
class PlacementTechnique:
    """A documented placement evasion, for discoverability / coverage parity."""

    name: str
    target: str   # the defender mechanism it evades
    note: str


_TECHNIQUES: List[PlacementTechnique] = [
    PlacementTechnique(
        "decoy_prefix",
        "keyword decode-and-rescan (maximal alphabet run)",
        "Long contiguous alphabet decoy whose length % group != 0 mis-phases "
        "the trailing real blob; suffix decoys are harmless (asymmetry = proof).",
    ),
    PlacementTechnique(
        "phase_offset",
        "keyword decode-and-rescan (byte alignment)",
        "Minimal residue prefix (1..group-1) to shift the blob off-phase; the "
        "defender fix is to try every phase when decoding a run.",
    ),
    PlacementTechnique(
        "position_embed",
        "truncated scan window (text[:N])",
        "Place the trigger past the scan limit inside benign filler; mind the "
        "schema max_length (HTTP 422) vs the scan window N.",
    ),
]


def list_placements() -> List[PlacementTechnique]:
    """All documented placement techniques, in declaration order."""
    return list(_TECHNIQUES)
