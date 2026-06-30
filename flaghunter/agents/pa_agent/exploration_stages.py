"""Detect → Identify → Exploit staged exploration (设计 §3.3).

The out-of-repertoire mechanism. When the deterministic 曲库 misses, the LLM-driven
exploration (``llm_executor``) used to flail as a single-step ReAct loop with no
overarching plan — it would fire scattered payloads with no notion of *what phase
of an investigation it is in*. This module gives that loop a **domain skeleton**:

    DETECT   — elicit ANY anomalous behaviour with generic probes (arithmetic /
               template / error-eliciting / census payloads). No vuln-class
               assumed yet. Anti-pattern: blind dictionary brute force.
    IDENTIFY — an anomaly surfaced; now *fingerprint the exact engine / format /
               primitive* behind it (differential payloads, version/error strings).
    EXPLOIT  — the primitive is pinned; build the *targeted* exploit and capture
               the flag.

``classify_stage`` is **deterministic** (a pure function of the accumulated
exploration evidence on ``CTFState`` — no randomness, no LLM call), so the staged
guidance injected into the exploration prompt is reproducible. The module is
*additive*: it only shapes the miss-path exploration, never the byte-identical
曲库-hit path. Evidence basis: reference KB ``05-security-techniques`` SSTI
Detect/Identify/Exploit + SignSaboteur census→identify→tamper→verify
(BB-2026-05-01-312/313/315). See [[project_ctf_autonomy_ceiling]].
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ExplorationStage(str, Enum):
    DETECT = "detect"
    IDENTIFY = "identify"
    EXPLOIT = "exploit"


# Concrete engine / format / primitive names — their presence in the evidence
# means identification has succeeded and we can move to a targeted exploit.
_ENGINE_TOKENS = (
    "jinja2", "jinja", "twig", "mako", "freemarker", "velocity", "smarty",
    "tornado", "erb", "handlebars", "ejs", "pug", "thymeleaf", "razor",
    "spel", "ognl", "groovy",
    # serialization / format primitives
    "soapclient", "phar", "pickle", "ysoserial", "fastjson", "snakeyaml",
)

# Generic anomaly markers — a probe elicited *something* worth fingerprinting.
_ANOMALY_TOKENS = (
    "traceback", "stack trace", "syntax error", "fatal error", "warning:",
    "exception", "undefined", "deprecated", "uncaught", "internal server error",
    "reflected", "evaluated",
)


def _exploration_blob(state: Any) -> str:
    """Lowercased text of the exploration evidence accumulated on the state.

    Reads observation kind/value/metadata — the same surface the LLM exploration
    records its steps onto — so the stage tracks the run's own findings.
    """
    parts: list[str] = []
    for obs in getattr(state, "observations", []) or []:
        for item in (getattr(obs, "kind", ""), getattr(obs, "value", ""), getattr(obs, "metadata", "")):
            if item:
                parts.append(str(item))
    return "\n".join(parts).lower()


def _confirmed_signal_count(state: Any) -> int:
    """How many exploration steps confirmed their expected signal.

    These are the agent's own ``expected_signal_met=True`` confirmations — strong,
    self-reported evidence that a probe provoked a real, anticipated response.
    """
    count = 0
    for obs in getattr(state, "observations", []) or []:
        meta = getattr(obs, "metadata", None)
        if isinstance(meta, dict) and meta.get("expected_signal_met") is True:
            count += 1
    return count


def classify_stage(state: Any) -> ExplorationStage:
    """Deterministic Detect→Identify→Exploit stage from accumulated evidence.

    - a concrete engine/format/primitive is named → ``EXPLOIT`` (we know the target)
    - else an anomaly was provoked (confirmed signal or anomaly marker) → ``IDENTIFY``
    - else → ``DETECT`` (probe broadly)
    """
    blob = _exploration_blob(state)
    if any(token in blob for token in _ENGINE_TOKENS):
        return ExplorationStage.EXPLOIT
    if _confirmed_signal_count(state) >= 1 or any(token in blob for token in _ANOMALY_TOKENS):
        return ExplorationStage.IDENTIFY
    return ExplorationStage.DETECT


_STAGE_PLANS: dict[ExplorationStage, dict[str, Any]] = {
    ExplorationStage.DETECT: {
        "goal": "Elicit ANY anomalous behaviour — do not assume a vuln class yet.",
        "action_families": [
            "arithmetic / template probes (e.g. {{7*7}}, ${7*7}, #{7*7})",
            "error-eliciting malformed input (unbalanced quotes/braces, type confusion)",
            "parameter, header, and cookie census (what inputs influence the response?)",
            "polyglot payloads that are safe but observable",
        ],
        "advance_when": "a probe provokes reflection, evaluation, an error/stack trace, or an otherwise unexpected response",
        "anti_pattern": "blind wordlist/dictionary brute force",
    },
    ExplorationStage.IDENTIFY: {
        "goal": "Pin the EXACT engine / format / primitive behind the anomaly.",
        "action_families": [
            "differential payloads that distinguish template engines (Jinja2 vs Twig vs Mako …)",
            "format-specific markers (XML entity, serialized-object header, JSON operator)",
            "version / error-string harvesting to fingerprint the stack",
        ],
        "advance_when": "the engine/format/primitive is named with supporting evidence",
        "anti_pattern": "jumping to an exploit payload before the primitive is confirmed",
    },
    ExplorationStage.EXPLOIT: {
        "goal": "Build the TARGETED exploit for the identified primitive and capture the flag.",
        "action_families": [
            "engine-specific RCE / file-read gadget for the confirmed primitive",
            "targeted payload tuned to the fingerprinted version/config",
            "flag exfiltration and runtime verification",
        ],
        "advance_when": "the flag is captured, or the primitive is proven unusable (then revert to IDENTIFY)",
        "anti_pattern": "firing generic payloads instead of the primitive-specific one",
    },
}


def stage_plan(stage: ExplorationStage) -> dict[str, Any]:
    """The goal / action families / advance criterion for a stage."""
    return dict(_STAGE_PLANS[stage])


def stage_guidance(state: Any) -> str:
    """A compact, deterministic guidance block to inject into the exploration prompt.

    Tells the LLM which investigation phase it is in and what kind of action is
    appropriate now — turning the single-step loop into a staged investigation.
    """
    stage = classify_stage(state)
    plan = _STAGE_PLANS[stage]
    families = "\n".join(f"  - {fam}" for fam in plan["action_families"])
    return (
        f"[exploration_stage={stage.value}]\n"
        f"goal: {plan['goal']}\n"
        f"appropriate actions now:\n{families}\n"
        f"advance to the next stage when: {plan['advance_when']}\n"
        f"avoid: {plan['anti_pattern']}"
    )


__all__ = ["ExplorationStage", "classify_stage", "stage_plan", "stage_guidance"]
