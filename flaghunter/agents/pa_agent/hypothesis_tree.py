"""§3.1 LATS hypothesis search tree — slice (a): structure + value init (shadow).

The :class:`HypothesisEngine` ranks candidate hypotheses as a flat list. The §3.1
goal is to give that ranking an explicit **search-tree** shape so later slices can
add value-guided expansion, backtracking, and pruning (LATS). This first slice is
deliberately *off the hot path*: it builds the tree and initialises node **value**
from the engine's existing score, but it does **not** change selection — nothing in
the live solve loop calls into here yet. ``choose_chain_order`` remains the sole
authority. Slice (b) flips selection onto the tree only after a byte-identical
shadow proof; slice (c) wires backtracking/pruning into recovery.

Design stance (see [[feedback_less_is_more_dont_cage_llm]]): the tree is a *search
structure*, a constraint boundary on exploration order — not a scripted decision
tree. Node ``value`` reuses the engine's own ``confidence + memory adjustment``
signal (single source of truth — we never re-rank, which would double-apply the
engine's memory write-back side effects). ``expansion_budget`` is a ceiling, not a
fixed step count. The model still decides *what* to do within a branch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .ctf_state import CTFState
    from .hypothesis_engine import HypothesisEngine

_ROOT_ID = "__root__"


@dataclass
class HypothesisNode:
    """One candidate hypothesis as a search-tree node.

    ``value`` is the engine's final score (higher = more promising). ``visits`` /
    ``status`` / ``expansion_budget`` are scaffolding for the later LATS slices
    (value-guided expansion, backtracking, pruning); slice (a) only populates
    ``value`` and the structural links.
    """

    hypothesis_id: str
    kind: str
    value: float
    parent: Optional["HypothesisNode"] = None
    children: list["HypothesisNode"] = field(default_factory=list)
    visits: int = 0
    status: str = "open"  # open | expanded | pruned | exhausted (slice c)

    def add_child(self, node: "HypothesisNode") -> "HypothesisNode":
        node.parent = self
        self.children.append(node)
        return node

    @property
    def is_root(self) -> bool:
        return self.parent is None and self.hypothesis_id == _ROOT_ID


@dataclass
class HypothesisTree:
    """A shallow search tree over the engine's ranked hypotheses (slice a).

    The root's children are the ranked candidate hypotheses, in rank order, each
    carrying its engine value. Order is preserved exactly, so deriving a chain
    order from the children reproduces ``choose_chain_order`` byte-for-byte.
    """

    root: HypothesisNode

    @property
    def candidates(self) -> list[HypothesisNode]:
        return list(self.root.children)

    def preferred_kind_order(self) -> list[str]:
        """Candidate hypothesis kinds in value/rank order (deduplicated)."""
        order: list[str] = []
        for child in self.root.children:
            if child.kind not in order:
                order.append(child.kind)
        return order

    def preferred_chain_order(self, engine: "HypothesisEngine", state: "CTFState") -> list[str]:
        """Chain execution order derived from the tree.

        Delegates to the engine's own ``_chains_from_ranked`` on the node sequence
        (nodes expose ``.kind``), so this is byte-identical to
        ``engine.choose_chain_order(state)`` for the same ranking — the invariant
        slice (b) will rely on before flipping selection onto the tree.
        """
        return engine._chains_from_ranked(state, self.root.children)


def build_hypothesis_tree(engine: "HypothesisEngine", state: "CTFState") -> HypothesisTree:
    """Build the slice-(a) shadow tree from the engine's current ranking.

    Mirrors ``choose_chain_order``'s source selection (``generate`` when no
    hypotheses exist yet, otherwise the scored rank) so the tree reflects exactly
    what the engine would act on — without performing any *extra* ranking pass on
    the live path (this is only called by slice-(a) shadow tests for now).
    """
    if getattr(state, "hypotheses", None):
        ranked, scores = engine.ranked_with_scores(state)
    else:
        ranked, scores = engine.generate(state), {}

    root = HypothesisNode(hypothesis_id=_ROOT_ID, kind=_ROOT_ID, value=0.0)
    for hypothesis in ranked:
        hid = str(getattr(hypothesis, "id", ""))
        root.add_child(
            HypothesisNode(
                hypothesis_id=hid,
                kind=str(getattr(hypothesis, "kind", "")),
                value=float(scores.get(hid, 0.0)),
            )
        )
    return HypothesisTree(root=root)


__all__ = ["HypothesisNode", "HypothesisTree", "build_hypothesis_tree"]
