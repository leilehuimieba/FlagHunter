"""Chains-as-tools ``Hands`` for the Shape-A blackboard loop (黑板 pivot slice 3).

Slice 1 made the loop call its environment through a ``Hands.execute(name, input) -> str``
seam; slice 2 bound the deterministic ``CTFState`` seams. This slice turns the existing
attack **chains into the tools** the brain may call: it wraps the dispatcher's
``_chain_handler_map`` (the single source of truth on which chains exist) as a list of
:class:`ToolSpec`, and routes ``execute`` to ``_execute_chain``, summarising the chain's
``_ChainOutcome`` back into a short string the §3.5 detect seam records.

The pivot's thesis: the model-driven loop is the top-level driver and the chains are
*tools* (cattle), not a fixed pipeline. This is the wiring that demotes them.

Coupling is kept to a duck-typed protocol (:class:`SupportsChains`) — the adapter needs
only ``_chain_handler_map`` and ``_execute_chain``, so it unit-tests against a tiny fake
dispatcher with no live LLM / detect phase. The chain's own side effects (recording a
found flag into ``CTFState``) compose with slice 2: a chain that wins makes the next
``goal()`` projection report the flag.

Still strangler-fig: lands additively, wired to nothing live; Brain (slice 4) and the
live switch + ``choose_chain_order`` deletion (slice 5) follow. The code gives the
boundary (which tools exist, how a result is summarised); the model decides which to call
(see [[feedback_less_is_more_dont_cage_llm]] and [[project_flaghunter_blackboard_pivot]]).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Protocol, runtime_checkable

from ...tools.tool_guard import ToolMissingError
from .blackboard_loop import ToolSpec
from .chains.base import _ChainOutcome

# Human-curated one-line descriptions the brain sees in the tool list. Keyed by the
# chain names ``_chain_handler_map`` exposes; an unlisted name still becomes a tool
# (with a generic description) so the catalog can never silently drop a real chain.
_CHAIN_DESCRIPTIONS: dict[str, str] = {
    "web": "Generic web exploitation route: parameter probing and common web bugs.",
    "xss": "Cross-site scripting: reflected/stored probing and exploitation.",
    "sqli": "SQL injection across request parameters (union/boolean/error/time).",
    "jwt": "JWT attacks: alg-confusion, none-alg, weak/known-secret forgery.",
    "lfi": "Local file inclusion / path traversal to read files or source.",
    "cmdi": "OS command injection via parameters.",
    "ssrf": "Server-side request forgery via parameters.",
    "upload": "Malicious file upload / webshell drop.",
    "misc": "Miscellaneous CTF web tricks not covered by a dedicated chain.",
}


@runtime_checkable
class SupportsChains(Protocol):
    """The slice of the dispatcher the Hands adapter needs — nothing more."""

    def _chain_handler_map(
        self, *, target: str, page_features: dict[str, Any], hint: str
    ) -> dict[str, Callable[[], Awaitable[_ChainOutcome]]]: ...

    async def _execute_chain(
        self, *, chain_name: str, target: str, page_features: dict[str, Any], hint: str
    ) -> _ChainOutcome: ...


@dataclass
class ChainContext:
    """The detect-phase context a chain needs (target / page features / hint).

    Resolved once from the detect phase, or refreshed per call via a provider thunk.
    """

    target: str = ""
    page_features: dict[str, Any] = field(default_factory=dict)
    hint: str = ""


ContextProvider = ChainContext | Callable[[], ChainContext]


def _resolve_context(context: ContextProvider) -> ChainContext:
    return context() if callable(context) else context


def summarize_outcome(outcome: _ChainOutcome) -> str:
    """Flatten a ``_ChainOutcome`` into the short string the detect seam records.

    A found flag is reported plainly (the chain has already recorded it into state,
    so ``goal()`` will see it); otherwise progress + reason are surfaced so the model
    can orient on what moved (or did not).
    """
    flag = str(getattr(outcome, "flag", "") or "").strip()
    if flag:
        return f"flag={flag}"
    progress = bool(getattr(outcome, "progress", False))
    parts = [f"progress={'true' if progress else 'false'}"]
    reason = str(getattr(outcome, "reason", "") or "").strip()
    if reason:
        parts.append(f"reason={reason}")
    return " ".join(parts)


def chain_tools(dispatcher: SupportsChains, *, context: ContextProvider) -> list[ToolSpec]:
    """Build the brain's tool list from the dispatcher's live chain handler map.

    Names come from ``_chain_handler_map`` (single source of truth on availability);
    descriptions from the curated table, falling back to a generic line so a newly
    added chain still appears as a callable tool.
    """
    ctx = _resolve_context(context)
    names = dispatcher._chain_handler_map(
        target=ctx.target, page_features=ctx.page_features, hint=ctx.hint
    ).keys()
    return [
        ToolSpec(name=name, description=_CHAIN_DESCRIPTIONS.get(name, f"{name} chain"))
        for name in names
    ]


@dataclass
class ChainHands:
    """``Hands`` over the dispatcher's chains. ``execute(name, input) -> str``.

    ``input`` may carry ``hint`` / ``target`` to refine the bound context for one call
    (the brain narrowing the focus); page features always come from the context (they
    are a detect-phase artifact, not something the brain synthesises).

    ``on_outcome`` is an optional post-chain hook fired with the raw
    ``(name, _ChainOutcome)`` before the string summary is returned. It is the seam
    where the dispatcher's per-chain contracts (terminal-success flag promotion,
    progress evaluation, experiment feedback — slice 5b) re-attach to the new loop,
    because they all key off the structured outcome that the string summary discards.

    ``on_missing_tools`` is the 5b cut-4 seam for the missing-tool contract: a chain
    that needs an uninstalled binary raises :class:`ToolMissingError`, which on the
    chain-order path is caught and recorded. The blackboard loop calls ``execute``
    with no such guard, so an uncaught error would crash the whole solve. Here we catch
    it, report the missing names through this hook (the dispatcher populates
    ``result.missing_tools`` so the finished event surfaces the capability gap), and
    return a plain ``tool_unavailable`` string so the BRAIN — the driver — simply picks
    a different tool next turn. No code-forced chain reorder/stop: the model switches
    (see [[feedback_less_is_more_dont_cage_llm]]).
    """

    dispatcher: SupportsChains
    context: ContextProvider
    on_outcome: Optional[Callable[[str, _ChainOutcome], None]] = None
    on_missing_tools: Optional[Callable[[list[str]], None]] = None

    async def execute(self, name: str, input: dict[str, Any]) -> str:
        ctx = _resolve_context(self.context)
        params = dict(input or {})
        target = str(params.get("target") or ctx.target or "")
        hint = str(params.get("hint") or ctx.hint or "")
        try:
            outcome = await self.dispatcher._execute_chain(
                chain_name=str(name or ""),
                target=target,
                page_features=ctx.page_features,
                hint=hint,
            )
        except ToolMissingError as exc:
            missing = sorted(exc.missing)
            if self.on_missing_tools is not None:
                self.on_missing_tools(missing)
            names = ", ".join(missing) or "?"
            return (
                f"tool_unavailable: {names} — required tool(s) not installed here; "
                "this chain cannot run, pick a DIFFERENT tool/chain"
            )
        if self.on_outcome is not None:
            self.on_outcome(str(name or ""), outcome)
        return summarize_outcome(outcome)


__all__ = [
    "ChainContext",
    "ChainHands",
    "SupportsChains",
    "chain_tools",
    "summarize_outcome",
]
