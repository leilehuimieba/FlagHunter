"""Unified attack-surface registry + reachability panel (P12).

A read-only projection. The heterogeneous *potential attack points* a run turns
up today live scattered across :class:`CTFState`: discovered endpoints (recon
observations + the exploration agenda), parameter/engine attack vectors
(hypotheses), source-audit suspicious points (``source_audit`` observations),
leaked secrets, etc. Every chain probes its own surface and judges真假 ad-hoc;
nothing gathers them into one comparable place. This module does exactly that —
it collects them into a single ranked registry, tags each with a status
(``confirmed`` / ``suspected`` / ``refuted``) and a **reachability score**, so an
operator (or panel) can compare入手点 across surface kinds at a glance.

Honest v1 boundary (written into the design, mirroring the P6/P7 read-only-first
discipline): **descriptive only**. It does NOT feed the planner prompt and does
NOT reorder anything — it never changes the solve path. The panel is rendered
into the Web/TUI blackboard snapshot purely for visibility ("要可见"). Reinjecting
the ranking to bias which surface the agent attacks next ("找入手点") is a
deliberate follow-up, exactly as P6 mining preceded P8 reinjection.

What it reflects is only what a run has *recorded* in structured state: recon
tool JSON that the LLM consumed but never wrote back as a structured observation
is not auto-ingested (that — tools emitting structured surface records — is a
separate follow-up).

Layer (I1): CAPABILITY (``knowledge/``), stdlib only, **duck-typed** over the
state object — it reads ``observations`` / ``exploration_agenda`` / ``hypotheses``
via ``getattr`` and never imports ``agents`` (the same trick
``CTFState.apply_profile`` uses to read a Profile without importing it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class SurfaceKind:
    """Vocabulary of attack-surface kinds (single source for the strings)."""

    ENDPOINT = "endpoint"
    PARAM = "param"
    SERVICE = "service"
    SOURCE = "source"
    ENGINE = "engine"
    SECRET = "secret"
    VECTOR = "vector"
    GENERIC = "generic"


# Status, strongest first. Used both to render and to pick the winner when the
# same surface is discovered by more than one origin (a recon endpoint that was
# later probed alive merges to the stronger ``confirmed``).
CONFIRMED = "confirmed"
SUSPECTED = "suspected"
REFUTED = "refuted"

_STATUS_RANK = {CONFIRMED: 2, SUSPECTED: 1, REFUTED: 0}
_STATUS_BASE = {CONFIRMED: 1.0, SUSPECTED: 0.5, REFUTED: 0.0}

# Curated observation-kind → (surface kind, status). Kept small and explicit so
# the registry stays low-noise — generic chatter observations are not surfaces.
_OBS_SURFACE: dict[str, tuple[str, str]] = {
    "recon_url": (SurfaceKind.ENDPOINT, SUSPECTED),
    "discovered_endpoint": (SurfaceKind.ENDPOINT, SUSPECTED),
    "agenda_exploration": (SurfaceKind.ENDPOINT, CONFIRMED),  # it responded
    "ssti_engine_identified": (SurfaceKind.ENGINE, CONFIRMED),
    "framework_detected": (SurfaceKind.ENGINE, SUSPECTED),
    "cookie_secret_leaked": (SurfaceKind.SECRET, CONFIRMED),
    "leaked_secret": (SurfaceKind.SECRET, CONFIRMED),
    "source_audit": (SurfaceKind.SOURCE, SUSPECTED),
    "source_leak_exploit_candidate": (SurfaceKind.SOURCE, SUSPECTED),
}

# Hypothesis kind → surface kind. Unknown kinds fall back to a generic VECTOR.
_HYP_SURFACE: dict[str, str] = {
    "sqli": SurfaceKind.PARAM,
    "generic_param_sqli": SurfaceKind.PARAM,
    "nosql": SurfaceKind.PARAM,
    "graphql": SurfaceKind.PARAM,
    "idor": SurfaceKind.PARAM,
    "xss": SurfaceKind.PARAM,
    "open_redirect": SurfaceKind.PARAM,
    "ssti": SurfaceKind.ENGINE,
    "upload": SurfaceKind.ENDPOINT,
    "xxe": SurfaceKind.ENDPOINT,
    "lfi": SurfaceKind.ENDPOINT,
    "rce": SurfaceKind.ENDPOINT,
    "deserialization": SurfaceKind.SOURCE,
}

_REFUTED_HYP_STATUSES = {"rejected", "exhausted"}
# Tokens in an exploration result that mean the endpoint did not respond usefully.
_DEAD_RESULT_TOKENS = ("error", "unavailable", "status=404", "status=403", "status=500")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass
class AttackSurface:
    """A single potential attack point with a真假 status and reachability score."""

    kind: str
    value: str
    status: str = SUSPECTED
    origin: str = ""
    confidence: float = 0.0
    directness: int = 0
    reachability: float = 0.0
    evidence: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.value}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "status": self.status,
            "origin": self.origin,
            "confidence": round(float(self.confidence), 3),
            "directness": int(self.directness),
            "reachability": round(float(self.reachability), 3),
            "evidence": list(self.evidence),
        }

    def to_web_dict(self) -> dict[str, Any]:
        """camelCase serialisation for the Web/TUI snapshot boundary."""
        return {
            "kind": self.kind,
            "value": self.value,
            "status": self.status,
            "origin": self.origin,
            "confidence": round(float(self.confidence), 3),
            "directness": int(self.directness),
            "reachability": round(float(self.reachability), 3),
        }


def reachability_score(status: str, confidence: float, directness: int) -> float:
    """Reachability in [0, 1].

    ``refuted`` is always 0. Otherwise the status sets the band (confirmed=1.0,
    suspected=0.5) and ``confidence`` lifts within it; ``directness`` (走最短链 —
    closer to the flag) adds a small bounded nudge so the shortest viable path
    ranks first.
    """
    if status == REFUTED:
        return 0.0
    base = _STATUS_BASE.get(status, _STATUS_BASE[SUSPECTED])
    score = base * (0.5 + 0.5 * _clamp01(confidence))
    score += 0.05 * max(0, min(int(directness), 4))
    return round(_clamp01(score), 3)


def _add(
    registry: dict[str, AttackSurface],
    *,
    kind: str,
    value: str,
    status: str,
    origin: str,
    confidence: float,
    directness: int,
    evidence: str,
) -> None:
    value = str(value or "").strip()
    if not value:
        return
    existing = registry.get(f"{kind}:{value}")
    if existing is None:
        existing = AttackSurface(kind=kind, value=value, status=status, origin=origin)
        registry[existing.id] = existing
    elif _STATUS_RANK.get(status, 0) > _STATUS_RANK.get(existing.status, 0):
        # Merge: keep the strongest status when a surface is discovered more than
        # once (a recon endpoint later probed alive collapses to ``confirmed``).
        existing.status = status
    existing.confidence = max(existing.confidence, _clamp01(confidence))
    existing.directness = max(existing.directness, int(directness))
    if origin and origin not in existing.origin.split("+"):
        existing.origin = f"{existing.origin}+{origin}" if existing.origin else origin
    note = str(evidence or "").strip()
    if note and note not in existing.evidence:
        existing.evidence.append(note)


def _collect_observations(state: Any, registry: dict[str, AttackSurface]) -> None:
    for obs in list(getattr(state, "observations", []) or []):
        kind = str(getattr(obs, "kind", "") or "").strip()
        mapped = _OBS_SURFACE.get(kind)
        if not mapped:
            continue
        surface_kind, status = mapped
        value = str(getattr(obs, "value", "") or "").strip()
        meta = getattr(obs, "metadata", {}) or {}
        confidence = 0.9 if status == CONFIRMED else 0.5
        try:
            confidence = float(meta.get("confidence", confidence))
        except (TypeError, ValueError):
            pass
        _add(
            registry,
            kind=surface_kind,
            value=value,
            status=status,
            origin="observation",
            confidence=confidence,
            directness=0,
            evidence=kind,
        )


def _collect_agenda(state: Any, registry: dict[str, AttackSurface]) -> None:
    for item in list(getattr(state, "exploration_agenda", []) or []):
        value = str(getattr(item, "url_or_path", "") or "").strip()
        if not value:
            continue
        explored = bool(getattr(item, "explored", False))
        result = str(getattr(item, "exploration_result", "") or "").strip()
        hint_strength = int(getattr(item, "hint_strength", 2) or 2)
        # Stronger hint (1) → higher confidence the surface matters.
        confidence = _clamp01((4 - max(1, min(3, hint_strength))) / 3.0)
        if explored:
            lowered = result.lower()
            dead = (not result) or any(tok in lowered for tok in _DEAD_RESULT_TOKENS)
            status = REFUTED if dead else CONFIRMED
        else:
            status = SUSPECTED
        _add(
            registry,
            kind=SurfaceKind.ENDPOINT,
            value=value,
            status=status,
            origin="exploration_agenda",
            confidence=confidence,
            directness=0,
            evidence=result or str(getattr(item, "discovery_source", "") or ""),
        )


def _collect_hypotheses(state: Any, registry: dict[str, AttackSurface]) -> None:
    for hyp in list(getattr(state, "hypotheses", []) or []):
        kind = str(getattr(hyp, "kind", "") or "").strip()
        description = str(getattr(hyp, "description", "") or "").strip()
        value = description or kind
        if not value:
            continue
        hyp_status = str(getattr(hyp, "status", "active") or "active").strip()
        status = REFUTED if hyp_status in _REFUTED_HYP_STATUSES else SUSPECTED
        confidence = float(getattr(hyp, "confidence", 0.0) or 0.0)
        supporting = list(getattr(hyp, "supporting_observations", []) or [])
        next_experiments = list(getattr(hyp, "next_experiments", []) or [])
        directness = max(0, len(supporting) - len(next_experiments))
        _add(
            registry,
            kind=_HYP_SURFACE.get(kind, SurfaceKind.VECTOR),
            value=value,
            status=status,
            origin="hypothesis",
            confidence=confidence,
            directness=directness,
            evidence=f"hypothesis:{kind}" if kind else "hypothesis",
        )


def collect_attack_surfaces(state: Any, *, top_n: int = 0) -> dict[str, Any]:
    """Project ``state`` into a ranked attack-surface registry.

    ``state`` is duck-typed: any object exposing ``observations`` /
    ``exploration_agenda`` / ``hypotheses`` (a :class:`CTFState` or a snapshot
    reconstruction). ``top_n`` > 0 caps the returned ``surfaces`` list after
    sorting (the summary counts always reflect the full set).

    Returns ``{"summary": {...}, "surfaces": [...]}``. Surfaces are sorted by
    descending reachability, then by value for a stable order.
    """
    registry: dict[str, AttackSurface] = {}
    _collect_observations(state, registry)
    _collect_agenda(state, registry)
    _collect_hypotheses(state, registry)

    surfaces = list(registry.values())
    for surface in surfaces:
        surface.reachability = reachability_score(
            surface.status, surface.confidence, surface.directness
        )
    surfaces.sort(key=lambda s: (-s.reachability, s.kind, s.value))

    by_kind: dict[str, int] = {}
    by_status = {CONFIRMED: 0, SUSPECTED: 0, REFUTED: 0}
    for surface in surfaces:
        by_kind[surface.kind] = by_kind.get(surface.kind, 0) + 1
        if surface.status in by_status:
            by_status[surface.status] += 1

    capped = surfaces[:top_n] if top_n and top_n > 0 else surfaces
    return {
        "summary": {
            "total": len(surfaces),
            "confirmed": by_status[CONFIRMED],
            "suspected": by_status[SUSPECTED],
            "refuted": by_status[REFUTED],
            "by_kind": by_kind,
        },
        "surfaces": [s.to_dict() for s in capped],
    }


def format_attack_surface_panel(report: dict[str, Any]) -> str:
    """Render a :func:`collect_attack_surfaces` report as a text panel."""
    summary = dict(report.get("summary") or {})
    surfaces = [s for s in list(report.get("surfaces") or []) if isinstance(s, dict)]
    lines: list[str] = []
    lines.append(
        "Attack surfaces: "
        f"{int(summary.get('total', 0))} total — "
        f"{int(summary.get('confirmed', 0))} confirmed, "
        f"{int(summary.get('suspected', 0))} suspected, "
        f"{int(summary.get('refuted', 0))} refuted"
    )
    by_kind = dict(summary.get("by_kind") or {})
    if by_kind:
        kinds = ", ".join(f"{k}={by_kind[k]}" for k in sorted(by_kind))
        lines.append(f"  by kind: {kinds}")
    if not surfaces:
        lines.append("  (no attack surfaces registered yet)")
        return "\n".join(lines)
    for surface in surfaces:
        reach = surface.get("reachability", 0.0)
        status = str(surface.get("status") or "").strip()
        kind = str(surface.get("kind") or "").strip()
        value = str(surface.get("value") or "").strip()
        origin = str(surface.get("origin") or "").strip()
        lines.append(f"  [{reach:.2f} {status:<9} {kind:<8}] {value}  ({origin})")
    return "\n".join(lines)
