"""Canonical blackboard board-element schema (P2 / 2A — 投影收敛).

A single typed vocabulary for the elements that the various "blackboard"
projections render, so the field shapes are defined ONCE instead of as three
divergent ad-hoc ``dict[str, Any]`` shapes (see
``docs/dev/FlagHunter_运行方式愿景与上线问题清单_2026-06-28_V1.md`` P2).

Scope of this first slice (2A-1): the **read-model** vocabulary used by
``agents/pa_agent/blackboard.py:project_blackboard`` (the LLM/solve-loop facing
``{facts, intents, hints}`` view) and its wrapper in ``session_context``. The
richer Web/decision snapshot in ``interface/blackboard_lite.py`` migrates onto
these element types incrementally in 2A-2, behind its existing
``normalize_blackboard_snapshot`` compat shim.

Design rules:
  * **snake_case** internally (Python-idiomatic; the LLM-facing read-model
    already uses it). The Web/JSON boundary is where camelCase belongs and is
    where casing conversion stays — not here.
  * ``to_dict()`` is **byte-identical** to the current ad-hoc dicts so existing
    consumers and the ``test_blackboard.py`` assertions pass unchanged (the
    house "字节级一致" refactor discipline).
  * Layer note (I1): this lives in the CAPABILITY layer (``knowledge/``) and
    imports only stdlib, so ORCHESTRATION (agents) and ENTRY (interface) may
    both import it. It must never import ``agents/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BoardFact:
    """A confirmed world-state element on the board.

    Different fact kinds historically emit different key sets (an observation
    carries ``subkind``; an artifact carries ``location``; a flag carries
    ``confidence``). ``_emit`` records exactly which keys this fact serialises,
    preserving the byte-identical per-kind shape. Use the classmethods rather
    than the bare constructor.
    """

    kind: str
    value: str = ""
    # ``source`` defaults to None (absent) so the Web emitter omits it for facts
    # that carry no source (e.g. control_decision). Read-model constructors below
    # always set it explicitly. ``confidence`` is float in the read-model but a
    # bucket string ("high"/"medium") in the Web snapshot — both shapes share this
    # one field.
    source: str | None = None
    subkind: str | None = None
    location: str | None = None
    confidence: float | str | None = None
    # Web snapshot (Layer 2) fields, emitted only by ``to_web_dict`` when set.
    rationale: str | None = None
    artifact_url: str | None = None
    exploit_type: str | None = None
    _emit: tuple[str, ...] = field(default=(), repr=False, compare=False)

    @classmethod
    def observation(cls, *, subkind: str, value: str, source: str) -> "BoardFact":
        return cls(
            kind="observation",
            subkind=subkind,
            value=value,
            source=source,
            _emit=("kind", "subkind", "value", "source"),
        )

    @classmethod
    def artifact(cls, *, value: str, location: str | None, source: str) -> "BoardFact":
        return cls(
            kind="artifact",
            value=value,
            location=location,
            source=source,
            _emit=("kind", "value", "location", "source"),
        )

    @classmethod
    def flag(cls, *, kind: str, value: str, source: str, confidence: float) -> "BoardFact":
        return cls(
            kind=kind,
            value=value,
            source=source,
            confidence=confidence,
            _emit=("kind", "value", "source", "confidence"),
        )

    @classmethod
    def web_fact(
        cls,
        kind: str,
        value: str,
        *,
        source: str | None = None,
        confidence: float | str | None = None,
        rationale: str | None = None,
        artifact_url: str | None = None,
        exploit_type: str | None = None,
    ) -> "BoardFact":
        """Construct a Web-snapshot fact (Layer 2). Serialise with ``to_web_dict``.

        The Web layer decides the semantic ``kind`` and which optional fields a
        fact carries; this type defines the shape so Layer 1 and Layer 2 cannot
        silently drift on what a "fact" is.
        """
        return cls(
            kind=kind,
            value=value,
            source=source,
            confidence=confidence,
            rationale=rationale,
            artifact_url=artifact_url,
            exploit_type=exploit_type,
        )

    def to_dict(self) -> dict[str, Any]:
        """Read-model (Layer 1) serialisation: snake_case, per-kind key set."""
        return {key: getattr(self, key) for key in self._emit}

    def to_web_dict(self) -> dict[str, Any]:
        """Web-snapshot (Layer 2) serialisation: camelCase, emit-if-present.

        ``kind`` and ``value`` are always emitted; the optional fields appear
        only when set (not None) — reproducing the historical heterogeneous Web
        fact shapes byte-identically.
        """
        out: dict[str, Any] = {"kind": self.kind, "value": self.value}
        if self.source is not None:
            out["source"] = self.source
        if self.confidence is not None:
            out["confidence"] = self.confidence
        if self.rationale is not None:
            out["rationale"] = self.rationale
        if self.artifact_url is not None:
            out["artifactUrl"] = self.artifact_url
        if self.exploit_type is not None:
            out["exploitType"] = self.exploit_type
        return out


@dataclass
class BoardIntent:
    """A pending/proposed direction with confidence and directness.

    Uniform shape across origins (hypothesis / exploration agenda item /
    candidate flag). ``refuted`` intents stay visible (sorted last) so the model
    sees what was already tried.
    """

    id: str
    kind: str
    description: str
    confidence: float
    value_score: float
    status: str
    refuted: bool
    next_experiments: list[Any]
    directness: int
    origin: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "description": self.description,
            "confidence": self.confidence,
            "value_score": self.value_score,
            "status": self.status,
            "refuted": self.refuted,
            "next_experiments": list(self.next_experiments),
            "directness": self.directness,
            "origin": self.origin,
        }


# Sort key for intents: active first; among active highest value, then most
# direct (shortest remaining path — 走最短链), then highest confidence; refuted
# last but visible. Single source for the ordering both the typed and dict
# builders share.
def intent_sort_key(intent: BoardIntent) -> tuple[Any, ...]:
    return (intent.refuted, -intent.value_score, -intent.directness, -intent.confidence)


@dataclass
class BoardView:
    """The canonical ``{facts, intents, hints}`` read-model board."""

    facts: list[BoardFact] = field(default_factory=list)
    intents: list[BoardIntent] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": [f.to_dict() for f in self.facts],
            "intents": [i.to_dict() for i in self.intents],
            "hints": list(self.hints),
        }
