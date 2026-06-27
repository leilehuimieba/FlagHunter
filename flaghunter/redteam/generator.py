"""Combine seeds × transforms into labelled red-team payload batches.

:func:`generate` is the entry point: it takes seed categories and a list of
transform *chains* (each chain is itself a list of transform names, enabling
multi-layer nesting) and emits one :class:`Payload` per (seed, chain). Each
payload carries everything the blue team needs to score it: the obfuscated
text, the target detector, a bypass hypothesis, and the expected outcome.

Output is plain JSONL (:func:`payloads_to_jsonl` / :func:`write_batch`) so a
batch drops straight into the red-blue mailbox's ``payloads/`` directory.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from .seeds import AttackSeed, list_seeds, seed_categories
from .transforms import apply_chain, get_transform

# A curated default set of evasive chains (used when caller passes none). The
# raw (no-transform) chain is always included as the keyword-layer baseline.
_DEFAULT_CHAINS: List[List[str]] = [
    [],                              # baseline: keyword rule should fire directly
    ["base64"],                      # control: rescan should decode + re-flag
    ["base32"],                      # evasive: rescan-blind encoding
    ["homoglyph"],                   # evasive: visual confusables
    ["zero_width"],                  # evasive: zero-width insertion
    ["morse"],                       # evasive: exotic encoding
    ["base64", "base64"],            # evasive: nested encoding
    ["leetspeak", "zero_width"],     # evasive: combined unicode tricks
]


@dataclass(frozen=True)
class Payload:
    """One generated, labelled test payload."""

    pid: str
    category: str
    transform_chain: List[str]
    seed: str
    text: str
    target_detector: str
    bypass_hypothesis: str
    expected_block: bool


def _bypass_hypothesis(seed: AttackSeed, chain: Sequence[str]) -> str:
    if not seed.expected_block:
        return "Benign control: should pass cleanly (any block here is a false positive)."
    if not chain:
        return "Baseline: deterministic keyword rule should fire on the plain text."
    transforms = [get_transform(n) for n in chain]
    if all(not t.evades_rescan for t in transforms):
        return (
            "Rescan control: encoding is covered by the base64/hex de-obfuscation "
            "rescan, so the keyword layer should still re-flag it."
        )
    evasive = [t.name for t in transforms if t.evades_rescan]
    return (
        f"Evasion: {', '.join(evasive)} is not covered by the base64/hex rescan; "
        "tests whether ml_classifier / llm_judge catch the semantic intent."
    )


def generate(
    categories: Optional[List[str]] = None,
    chains: Optional[List[List[str]]] = None,
    max_per_seed: Optional[int] = None,
) -> List[Payload]:
    """Produce labelled payloads for ``categories`` across transform ``chains``.

    Args:
        categories: seed categories to include (None/empty = all known).
        chains: transform chains to apply per seed (None = curated default set).
            Each chain is a list of transform names; ``[]`` means "raw".
        max_per_seed: cap on chains applied to each seed (None = no cap).

    Returns:
        Deterministically-ordered list of :class:`Payload`.
    """
    seeds = list_seeds(categories)
    use_chains = chains if chains is not None else _DEFAULT_CHAINS
    if max_per_seed is not None:
        use_chains = use_chains[:max_per_seed]

    payloads: List[Payload] = []
    for s_idx, seed in enumerate(seeds):
        for c_idx, chain in enumerate(use_chains):
            chain_tag = "raw" if not chain else "+".join(chain)
            payloads.append(
                Payload(
                    pid=f"{seed.category}-{s_idx:02d}-{c_idx:02d}-{chain_tag}",
                    category=seed.category,
                    transform_chain=list(chain),
                    seed=seed.text,
                    text=apply_chain(seed.text, list(chain)),
                    target_detector=seed.target_detector,
                    bypass_hypothesis=_bypass_hypothesis(seed, chain),
                    expected_block=seed.expected_block,
                )
            )
    return payloads


def payloads_to_jsonl(payloads: Sequence[Payload]) -> str:
    """Serialise payloads to JSONL (one JSON object per line)."""
    return "\n".join(
        json.dumps(asdict(p), ensure_ascii=False) for p in payloads
    )


def write_batch(payloads: Sequence[Payload], path: str | Path) -> Path:
    """Write a JSONL batch to ``path`` (creating parent dirs); return the Path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payloads_to_jsonl(payloads) + "\n", encoding="utf-8")
    return out


__all__ = [
    "Payload",
    "generate",
    "payloads_to_jsonl",
    "write_batch",
    "seed_categories",
]
