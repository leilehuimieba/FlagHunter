"""I5 reachability invariant guard (N4).

The CTF solve loop derives its `chain_order` dynamically from ranked hypotheses
via `_CHAIN_BY_KIND` (hypothesis_engine), then dispatches each chain name through
`_chain_handler_map` (ctf_dispatcher). Two latent reachability landmines exist:

  1. A kind mapped to a chain *name* that has no entry in `_chain_handler_map`
     falls through to the robots.txt default handler — the documented top
     false-positive trap (see the graphql/nosql comment in `_CHAIN_BY_KIND`).
  2. A kind listed in `WEB_STRATEGY_ORDER` with no registered StrategyDefinition
     is silently skipped (`strategy_registry.get → None → continue`) — a
     "strong capability that can't be reached", the class of bug that once left
     generic_param_sqli unreachable.

These tests pin both invariants so a future edit that adds a kind→chain mapping,
renames a chain, or drops/renames a strategy can never silently regress
reachability. This converts a by-hand audit into an enforced contract, the same
way `test_import_layers.py` enforces the I1 dependency-direction invariant.
"""

from __future__ import annotations

from flaghunter.agents.pa_agent.chains.web import WEB_STRATEGY_ORDER
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.hypothesis_engine import _CHAIN_BY_KIND
from flaghunter.agents.pa_agent.strategy_registry import StrategyRegistry


def _handler_chain_names() -> set[str]:
    """Keys of `_chain_handler_map` without standing up a full dispatcher.

    `_chain_handler_map` only builds a dict of lambda closures over `self`'s
    bound methods — it neither invokes them nor touches any `__init__`-set
    attribute — so a bare instance is sufficient and avoids constructing a
    runtime/registry stack just to read the routing table.
    """
    dispatcher = object.__new__(CTFTaskDispatcher)
    handlers = dispatcher._chain_handler_map(
        target="http://ctf.local/",
        page_features={},
        hint="",
    )
    return set(handlers)


def test_every_chain_by_kind_value_has_a_handler():
    """Invariant 1: every chain name a hypothesis can emit is dispatchable.

    Any chain value in `_CHAIN_BY_KIND` missing from `_chain_handler_map` would
    silently fall through to the robots.txt default handler.
    """
    emitted_chains = set(_CHAIN_BY_KIND.values())
    handler_chains = _handler_chain_names()
    unreachable = emitted_chains - handler_chains
    assert not unreachable, (
        f"_CHAIN_BY_KIND emits chain name(s) {sorted(unreachable)} with no handler in "
        f"_chain_handler_map — these fall through to the robots.txt default handler. "
        f"Register a handler or remap the kind."
    )


def test_web_strategy_order_kinds_all_resolve_in_registry():
    """Invariant 2: the ordered web sequence references no phantom strategy.

    A kind in `WEB_STRATEGY_ORDER` that `StrategyRegistry` does not register is
    silently skipped at runtime, so the capability is unreachable.
    """
    registry = StrategyRegistry.build_default()
    phantom = [kind for kind in WEB_STRATEGY_ORDER if registry.get(kind) is None]
    assert not phantom, (
        f"WEB_STRATEGY_ORDER lists kind(s) {phantom} with no registered "
        f"StrategyDefinition — they are silently skipped (get → None → continue). "
        f"Register a strategy or drop the kind from the order."
    )


def test_web_strategy_order_has_no_duplicate_kinds():
    """The ordered sequence is a clean priority list, not an accidental multiset."""
    assert len(WEB_STRATEGY_ORDER) == len(set(WEB_STRATEGY_ORDER)), (
        f"WEB_STRATEGY_ORDER has duplicate kinds: {WEB_STRATEGY_ORDER}"
    )


def test_path_traversal_stays_out_of_web_strategy_order():
    """Regression-lock the N4 cleanup.

    `path_traversal` is generated as a hypothesis kind but has no distinct
    strategy (its `_has_file_endpoint` trigger is exploited by
    `file_read_endpoint`). It must not creep back into the ordered sequence as a
    silently-skipped no-op. Its `_CHAIN_BY_KIND` → "web" mapping stays valid
    because the web chain itself is dispatchable (covered by invariant 1).
    """
    assert "path_traversal" not in WEB_STRATEGY_ORDER
    assert _CHAIN_BY_KIND.get("path_traversal") == "web"
