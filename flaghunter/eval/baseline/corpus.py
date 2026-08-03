"""Tiered challenge corpus for the solve-rate baseline.

The manifest (``corpus.json``) holds **stable metadata only** — never a live
target URL, because instances are ephemeral (a fresh URL per launch). At run time
the operator supplies a target map (challenge id → URL) via ``--targets``; a
challenge with no resolved target is SKIPPED and reported as such, so the
scorecard never silently pretends an unrun challenge passed.

Tiers encode *expectation*, which is the whole point of a baseline — a result is
only meaningful against what you predicted:

    T0  smoke anchor   — already known-solvable; regression guard.
    T1  in-repertoire  — a chain exists in the playbook; expected SOLVED.
    T2  repertoire edge — needs chaining / light reasoning; expected NEAR.
    T3  out-of-repertoire — new chain or non-web; expected FAIL (measures the
        honest ceiling: "off-catalog challenges are structurally unreachable").
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

_CORPUS_PATH = Path(__file__).parent / "corpus.json"

# Corpus manifest schema version. Bump this (and add the old value to
# _SUPPORTED_VERSIONS with a migration) whenever the on-disk shape of
# corpus.json changes in a way readers must be aware of — a new required
# field, a renamed field, or changed semantics. A dict-form manifest that
# omits ``schema_version`` is rejected loudly rather than loaded with
# silently-defaulted fields (D-01, §13.5).
SCHEMA_VERSION = "1"
_SUPPORTED_VERSIONS = frozenset({"1"})


class Tier(str, Enum):
    T0 = "T0"  # smoke anchor (known-solvable)
    T1 = "T1"  # in-repertoire (expected solved)
    T2 = "T2"  # repertoire edge (expected near)
    T3 = "T3"  # out-of-repertoire (expected fail — the ceiling)


@dataclass
class Challenge:
    """One challenge's stable metadata. Target URL is resolved at run time."""

    id: str
    title: str
    tier: Tier
    type: str  # web | crypto | reverse | pwn | misc
    task: str  # the natural-language instruction fed to `flaghunter run`
    flag_pattern: str  # regex the captured flag must match
    expected_verdict: str  # solved | near | fail — what this tier predicts
    platform: str = "dasctf"
    ctf_type: str | None = None  # --ctf-type hint; defaults to `type`
    known_flag: str | None = None  # optional exact flag for offline judging
    max_loops: int = 12
    timeout_s: int = 900
    auth_source: str = ""  # provenance of the authorized instance
    notes: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.tier, str):
            self.tier = Tier(self.tier)
        if not self.ctf_type:
            self.ctf_type = self.type

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Challenge":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "tier": self.tier.value,
            "type": self.type,
            "task": self.task,
            "flag_pattern": self.flag_pattern,
            "expected_verdict": self.expected_verdict,
            "platform": self.platform,
            "ctf_type": self.ctf_type,
            "known_flag": self.known_flag,
            "max_loops": self.max_loops,
            "timeout_s": self.timeout_s,
            "auth_source": self.auth_source,
            "notes": self.notes,
            "tags": self.tags,
        }


def load_corpus(
    path: Path | None = None,
    *,
    tiers: list[str] | None = None,
    types: list[str] | None = None,
) -> list[Challenge]:
    """Load the manifest, optionally filtered by tier and/or challenge type.

    Raises on duplicate ids so a copy-paste slip in the manifest fails loudly
    instead of silently shadowing a challenge in the scorecard.
    """
    src = path or _CORPUS_PATH
    raw = json.loads(src.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        version = raw.get("schema_version")
        if version is None:
            raise ValueError(
                f"corpus {src.name} is missing the required 'schema_version' "
                f"field (expected one of {sorted(_SUPPORTED_VERSIONS)}); add "
                f'`"schema_version": "{SCHEMA_VERSION}"` to the top of the file'
            )
        if version not in _SUPPORTED_VERSIONS:
            raise ValueError(
                f"corpus {src.name} has unsupported schema_version={version!r}; "
                f"this build supports {sorted(_SUPPORTED_VERSIONS)} — regenerate "
                f"or migrate the manifest"
            )
    entries = raw["challenges"] if isinstance(raw, dict) else raw
    challenges = [Challenge.from_dict(e) for e in entries]

    seen: set[str] = set()
    for c in challenges:
        if c.id in seen:
            raise ValueError(f"duplicate challenge id in corpus: {c.id!r}")
        seen.add(c.id)

    if tiers:
        want_tiers = {t.upper() for t in tiers}
        challenges = [c for c in challenges if c.tier.value in want_tiers]
    if types:
        want_types = {t.lower() for t in types}
        challenges = [c for c in challenges if c.type.lower() in want_types]
    return challenges
