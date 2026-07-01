"""Pluggable LLM ``Brain`` for the Shape-A blackboard loop (黑板 pivot slice 4).

Slice 1 made the loop ask a ``Brain.propose(view, tools) -> Action`` for one next step;
slices 2/3 bound the deterministic seams and the chains-as-tools. This slice supplies the
brain itself: render the board + tool list into a prompt, make **one** model call, and
parse the reply into a single structured :class:`Action`. The model is the driver; this
adapter is just the Observe→Decide boundary around it.

Pluggability + testability:
  * The model call is injected as a minimal ``(system, user) -> text`` async callable, so
    a unit test fakes it with canned JSON and no live provider. :meth:`LLMBrain.from_llm`
    adapts a real :class:`flaghunter.llm.llm.LLM` into that callable.
  * Prompt rendering (:func:`render_user_prompt`) and reply parsing (:func:`parse_action`)
    are pure functions, tested independently of any model.

Robustness: a reply that is not valid action-JSON does not crash or end the run — it is
recorded as a ``declare_intent`` so the board reflects it and the loop re-projects next
round (the Budget bounds any runaway). The code constrains the *shape* of a decision; the
model chooses *which* decision (see [[feedback_less_is_more_dont_cage_llm]]).

Note: 曲库 Hints are NOT brain code — they reach the brain through ``BoardView.hints`` via
``blackboard_adapter.make_view(hints=…)``; wiring that thunk is slice 5. Still strangler-fig:
additive, wired to nothing live. See [[project_flaghunter_blackboard_pivot]].
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from ...knowledge.blackboard_schema import BoardView
from .blackboard_loop import Action, ToolSpec

# (system_prompt, user_prompt) -> raw model text.
LLMCall = Callable[[str, str], Awaitable[str]]

_VALID_KINDS = {"call_tool", "write_fact", "declare_intent", "stop"}

_SYSTEM_PROMPT = (
    "You are the decision brain of a CTF solving loop driving a shared blackboard.\n"
    "Each turn you see the board (confirmed FACTS, ranked INTENTS with already-refuted "
    "ones marked, and HINTS) and the TOOLS you may call. Choose exactly ONE next action "
    "that makes the most direct progress toward the flag — prefer the shortest remaining "
    "path (high value, high directness) and never re-try a REFUTED intent.\n"
    "Read ATTEMPTS as negative feedback: a tool already run several times with NO progress "
    "is a dead end — switch to a DIFFERENT tool or tactic (especially one the task points at "
    "but you have not tried yet) instead of repeating it.\n\n"
    "Reply with ONLY a single JSON object, no prose, of this shape:\n"
    '{"kind": "call_tool|write_fact|declare_intent|stop", "tool": "<tool name if '
    'call_tool>", "input": {<tool args>}, "expected_signal": "<string proving success '
    'if it appears in the tool output>", "content": "<text for write_fact/declare_intent>", '
    '"rationale": "<one short sentence>"}\n'
    "- call_tool: run one tool. Set tool + input, and expected_signal when you can name "
    "the proof string.\n"
    "- write_fact: assert a confirmed world-state fact (content).\n"
    "- declare_intent: state a direction to pursue next (content).\n"
    "- stop: only when solved or no action can help."
)


def _fmt_fact(fact: Any) -> str:
    d = fact.to_dict() if hasattr(fact, "to_dict") else dict(fact)
    kind = d.get("subkind") or d.get("kind") or "fact"
    value = str(d.get("value") or "")[:160]
    source = d.get("source")
    tail = f" (source={source})" if source else ""
    return f"- [{kind}] {value}{tail}"


def _fmt_intent(intent: Any) -> str:
    d = intent.to_dict() if hasattr(intent, "to_dict") else dict(intent)
    description = str(d.get("description") or "")[:120]
    if d.get("refuted"):
        tag = "REFUTED-already-tried"
    else:
        tag = (
            f"value={float(d.get('value_score') or 0.0):.2f}"
            f",direct={int(d.get('directness') or 0)}"
            f",conf={float(d.get('confidence') or 0.0):.2f}"
        )
    return f"- [{tag}] {d.get('kind')}: {description}"


def _fmt_attempt(attempt: Any) -> str:
    tool = str(getattr(attempt, "tool", "") or "?")
    count = int(getattr(attempt, "count", 0) or 0)
    progress = int(getattr(attempt, "progress_count", 0) or 0)
    if progress == 0:
        status = f"{count}x, NO progress -> dead end"
    else:
        status = f"{count}x ({progress} made progress)"
    last = str(getattr(attempt, "last_result", "") or "").strip()
    tail = f" (last: {last})" if last else ""
    return f"- {tool}: {status}{tail}"


def render_user_prompt(view: BoardView, tools: list[ToolSpec]) -> str:
    """Render the board + tools into the brain's user prompt (pure)."""
    facts = list(getattr(view, "facts", []) or [])
    intents = list(getattr(view, "intents", []) or [])
    hints = [str(h) for h in (getattr(view, "hints", []) or [])]
    attempts = list(getattr(view, "attempts", []) or [])

    sections: list[str] = []
    sections.append(
        "FACTS (confirmed):\n" + ("\n".join(_fmt_fact(f) for f in facts) if facts else "- (none)")
    )
    # Surfaced between FACTS and INTENTS so the "already tried, no progress" trail is
    # salient (the fixation the smoke test exposed). Omitted entirely when nothing has
    # run yet, to keep the cold-start prompt low-noise.
    if attempts:
        sections.append(
            "ATTEMPTS SO FAR (tools already run; a repeated NO-progress tool is a dead "
            "end — switch, don't repeat):\n" + "\n".join(_fmt_attempt(a) for a in attempts)
        )
    sections.append(
        "INTENTS (ranked; do not re-try REFUTED):\n"
        + ("\n".join(_fmt_intent(i) for i in intents) if intents else "- (none)")
    )
    if hints:
        sections.append("HINTS:\n" + "\n".join(f"- {h}" for h in hints))
    sections.append(
        "TOOLS:\n"
        + (
            "\n".join(f"- {t.name}: {t.description}" for t in tools)
            if tools
            else "- (none)"
        )
    )
    sections.append("Respond with one JSON action object now.")
    return "\n\n".join(sections)


def _loads(text: str) -> Optional[dict]:
    """Best-effort extraction of a single JSON object from model text."""
    raw = str(text or "").strip()
    if not raw:
        return None
    # Strip a leading ```json / ``` fence pair if present.
    if raw.startswith("```"):
        fence = raw.split("```")
        if len(fence) >= 2:
            body = fence[1]
            if body.lstrip().lower().startswith("json"):
                body = body.lstrip()[4:]
            raw = body.strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except (ValueError, TypeError):
        pass
    # Fall back to the first balanced-looking {...} slice.
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except (ValueError, TypeError):
            return None
    return None


def parse_action(text: str) -> Action:
    """Parse model text into one :class:`Action`, never raising.

    Unparseable / wrong-kind replies degrade to a ``declare_intent`` carrying the raw
    text, so the loop keeps going (the Budget bounds it) instead of crashing or stopping.
    """
    obj = _loads(text)
    raw_preview = str(text or "").strip()[:400]
    if not isinstance(obj, dict):
        return Action(kind="declare_intent", content=raw_preview, rationale="unparsed-brain-response")

    kind = str(obj.get("kind") or "").strip()
    if kind not in _VALID_KINDS:
        return Action(kind="declare_intent", content=raw_preview, rationale="invalid-action-kind")

    raw_input = obj.get("input")
    return Action(
        kind=kind,  # type: ignore[arg-type]
        tool=(str(obj["tool"]) if obj.get("tool") else None),
        input=dict(raw_input) if isinstance(raw_input, dict) else {},
        rationale=str(obj.get("rationale") or ""),
        expected_signal=(str(obj["expected_signal"]) if obj.get("expected_signal") else None),
        content=str(obj.get("content") or ""),
    )


@dataclass
class LLMBrain:
    """A :class:`blackboard_loop.Brain` backed by one injected model call."""

    call: LLMCall
    system_prompt: str = _SYSTEM_PROMPT

    async def propose(self, view: BoardView, tools: list[ToolSpec]) -> Action:
        user = render_user_prompt(view, list(tools or []))
        text = await self.call(self.system_prompt, user)
        return parse_action(text)

    @classmethod
    def from_llm(
        cls,
        llm: Any,
        *,
        task_hint: str = "ctf_blackboard",
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> "LLMBrain":
        """Adapt a real :class:`flaghunter.llm.llm.LLM` into a brain.

        One ``generate`` call per ``propose``; the reply ``content`` is parsed. The LLM
        instance stays swappable (any provider) — that is the pluggable-model knob.
        """

        async def _call(system: str, user: str) -> str:
            response = await llm.generate(
                system,
                [{"role": "user", "content": user}],
                max_tokens=max_tokens,
                task_hint=task_hint,
            )
            return str(getattr(response, "content", "") or "")

        return cls(call=_call, system_prompt=system_prompt or _SYSTEM_PROMPT)


__all__ = [
    "LLMBrain",
    "LLMCall",
    "render_user_prompt",
    "parse_action",
]
